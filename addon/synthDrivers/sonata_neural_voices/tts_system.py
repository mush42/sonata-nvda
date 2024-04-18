# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

import copy
import operator
import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Mapping, Optional, Sequence, Union

import globalVars
from languageHandler import normalizeLanguage

from . import aio
from . import grpc_client
from .const import *
from .helpers import import_bundled_library, LIB_DIRECTORY


class VoiceNotFoundError(LookupError):
    pass


class SpeakerNotFoundError(LookupError):
    pass


@dataclass
class Scales:
    length_scale: float
    noise_scale: float
    noise_w: float


class AudioProvider(ABC):
    @abstractmethod
    def generate_audio(self) -> bytes:
        """Generate audio."""


class SilenceProvider(AudioProvider):
    __slots__ = ["time_ms", "sample_rate"]

    def __init__(self, time_ms, sample_rate):
        self.time_ms = time_ms
        self.sample_rate = sample_rate

    def generate_audio(self):
        """Generate silence (16-bit mono at sample rate)."""
        num_samples = int((self.time_ms / 1000.0) * self.sample_rate)
        return bytes(num_samples * 2)


class SpeechProvider(AudioProvider):
    """A pending request to speak some text."""

    __slots__ = ["text", "speech_options"]

    def __init__(self, text, speech_options):
        self.text = text
        self.speech_options = speech_options

    async def generate_audio(self):
        return await self.speech_options.speak_text(self.text)


@dataclass
class SonataVoice:
    key: str
    name: str
    language: str
    description: str
    location: str
    properties: Optional[Mapping[str, int]] = field(default_factory=dict)
    remote_id: str = None
    supports_streaming_output: bool = False

    @classmethod
    def from_path(cls, path):
        path = Path(path)
        key = path.name
        try:
            lang, name, quality = key.split("-")
        except ValueError:
            raise ValueError(f"Invalid voice path: {path}")
        return cls(
            key=key,
            name=name,
            language=normalizeLanguage(lang),
            description="",
            location=path,
            properties={"quality": quality.lower()},
        )

    def load(self):
        if self.remote_id:
            return
        try:
            self.config_path = next(self.location.glob("*.json"))
        except StopIteration:
            raise RuntimeError(
                f"Could not load voice from `{os.fspath(self.location)}`"
            )
        voice_info = grpc_client.load_voice(
            os.fspath(self.config_path)
        ).result()
        self.remote_id = voice_info.voice_id
        self.supports_streaming_output = voice_info.supports_streaming_output
        default_synth_options = voice_info.synth_options
        self.default_scales = Scales(
            length_scale=default_synth_options.length_scale,
            noise_scale=default_synth_options.noise_scale,
            noise_w=default_synth_options.noise_w,
        )
        self.sample_rate = voice_info.audio.sample_rate
        self.speakers = voice_info.speakers
        self.speaker_names = list(self.speakers.values())
        self.is_multi_speaker = bool(self.speakers)
        if self.is_multi_speaker:
            self.default_speaker = default_synth_options.speaker
        else:
            self.default_speaker = None

    @property
    def speaker(self):
        if self.is_multi_speaker:
            return grpc_client.get_synth_options(self.remote_id).result().speaker
        return FALLBACK_SPEAKER_NAME

    @speaker.setter
    def speaker(self, value):
        if self.is_multi_speaker:
            grpc_client.set_synth_options(self.remote_id, speaker=value).result()

    @property
    def noise_scale(self):
        return grpc_client.get_synth_options(self.remote_id).result().noise_scale

    @noise_scale.setter
    def noise_scale(self, value):
        grpc_client.set_synth_options(self.remote_id, noise_scale=value).result()

    @property
    def length_scale(self):
        return grpc_client.get_synth_options(self.remote_id).result().length_scale

    @length_scale.setter
    def length_scale(self, value):
        grpc_client.set_synth_options(self.remote_id, length_scale=value).result()

    @property
    def noise_w(self):
        return grpc_client.get_synth_options(self.remote_id).result().noise_w

    @noise_w.setter
    def noise_w(self, value):
        grpc_client.set_synth_options(self.remote_id, noise_w=value).result()

    @property
    def is_fast(self):
        return "+RT" in self.key

    @property
    def variant(self):
        return "fast" if self.is_fast else "standard"

    @property
    def standard_variant_key(self):
        return self.key.replace("+RT", "")

    @property
    def fast_variant_key(self):
        key = self.key.replace("+RT", "")
        lang, name, quality = key.split("-")
        return "-".join([
            lang,
            f"{name}+RT",
            quality
        ])

    async def synthesize(self, text, rate, volume, pitch, sentence_silence_ms):
        if (len(text) < 10) and (set(text.strip()).issubset(IGNORED_PUNCS)):
            return
        stream = grpc_client.speak(
            voice_id=self.remote_id,
            text=text,
            rate=rate,
            volume=volume,
            pitch=pitch,
            appended_silence_ms=sentence_silence_ms,
            streaming=self.supports_streaming_output
        )
        async for ret in stream:
            yield ret.wav_samples


class SpeechOptions:
    __slots__ = ["voice", "rate", "volume", "pitch", "sentence_silence_ms"]

    def __init__(self, voice, speaker=None, rate=None, volume=None, pitch=None, sentence_silence_ms=None):
        self.set_voice(voice)
        self.rate = rate
        self.volume = volume
        self.pitch = pitch
        self.sentence_silence_ms = sentence_silence_ms

    def set_voice(self, voice: SonataVoice):
        voice.load()
        self.voice = voice

    @property
    def speaker(self):
        return self.voice.speaker

    @speaker.setter
    def speaker(self, value):
        self.voice.speaker = value

    def copy(self):
        return copy.copy(self)

    async def speak_text(self, text):
        return self.voice.synthesize(
            text,
            self.rate,
            self.volume,
            self.pitch,
            self.sentence_silence_ms
        )


class SonataTextToSpeechSystem:

    def __init__(
        self, voices: Sequence[SonataVoice], speech_options: SpeechOptions = None
    ):
        self.voices = voices
        if speech_options is not None:
            self.speech_options = speech_options
        else:
            try:
                voice = self.voices[0]
            except IndexError:
                raise VoiceNotFoundError("No Piper voices found")
            self.speech_options = SpeechOptions(voice=voice)

    @contextmanager
    def create_synthesis_context(self):
        """Reset speech params after each utterance."""
        old_speech_options = self.speech_options.copy()
        yield
        self.speech_options = old_speech_options

    def shutdown(self):
        pass

    @property
    def voice(self) -> str:
        """Get the current voice key"""
        return self.speech_options.voice.key

    @voice.setter
    def voice(self, new_voice: str):
        """Set the current voice key"""
        for voice in self.voices:
            if voice.key == new_voice:
                self.speech_options.set_voice(voice)
                return
        raise VoiceNotFoundError(
            f"A voice with the given key `{new_voice}` was not found"
        )

    @property
    def speaker(self) -> str:
        """Get the current speaker"""
        return self.speech_options.speaker or FALLBACK_SPEAKER_NAME

    @speaker.setter
    def speaker(self, new_speaker: str):
        if not self.speech_options.voice.is_multi_speaker:
            return
        if new_speaker == FALLBACK_SPEAKER_NAME:
            self.speech_options.speaker = self.speech_options.voice.speakers[0]
        elif new_speaker in self.speech_options.voice.speaker_names:
            self.speech_options.speaker = new_speaker
        else:
            raise SpeakerNotFoundError(f"Speaker `{new_speaker}` was not found")

    @property
    def language(self) -> str:
        """Get the current voice language"""
        return self.speech_options.voice.language

    @language.setter
    def language(self, new_language: str):
        """Set the current voice language"""
        lang = normalizeLanguage(new_language)
        if self.speech_options.voice.language == lang:
            return
        lang_code = lang.split("-")[0] + "-"
        possible_voices = []
        for voice in self.voices:
            if voice.language == lang:
                self.speech_options.set_voice(voice)
                return
            elif voice.language.startswith(lang_code):
                possible_voices.append(voice)
        if possible_voices:
            self.speech_options.set_voice(possible_voices[0])
            return
        raise VoiceNotFoundError(
            f"A voice with the given language `{new_language}` was not found"
        )

    @property
    def volume(self) -> float:
        """Get the current volume in [0, 100]"""
        if self.speech_options.volume is None:
            return DEFAULT_VOLUME
        return self.speech_options.volume

    @volume.setter
    def volume(self, new_volume: float):
        """Set the current volume in [0, 100]"""
        self.speech_options.volume = new_volume

    @property
    def rate(self) -> float:
        """Get the current speaking rate in [0, 100]"""
        if self.speech_options.rate is None:
            return DEFAULT_RATE
        return self.speech_options.rate

    @rate.setter
    def rate(self, new_rate: float):
        """Set the current speaking rate in [0, 100]"""
        self.speech_options.rate = new_rate

    @property
    def pitch(self) -> float:
        """Get the current speaking pitch in [0, 100]"""
        if self.speech_options.pitch is None:
            return DEFAULT_PITCH
        return self.speech_options.pitch

    @pitch.setter
    def pitch(self, new_pitch: float):
        """Set the current speaking pitch in [0, 100]"""
        self.speech_options.pitch = new_pitch

    def get_voices(self):
        return self.voices

    def get_speakers(self):
        if self.speech_options.voice.is_multi_speaker:
            return self.speech_options.voice.speaker_names
        else:
            return [
                FALLBACK_SPEAKER_NAME,
            ]

    def create_speech_provider(self, text):
        return SpeechProvider(text, self.speech_options.copy())

    def create_break_provider(self, time_ms):
        return SilenceProvider(time_ms, self.speech_options.voice.sample_rate)

    @classmethod
    def load_piper_voices_from_nvda_config_dir(cls):
        Path(SONATA_VOICES_DIR).mkdir(parents=True, exist_ok=True)
        return sorted(
            cls.load_voices_from_directory(SONATA_VOICES_DIR),
            key=operator.attrgetter("key"),
        )

    @classmethod
    def load_voices_from_directory(
        cls, voices_directory, *, directory_name_prefix="voice-"
    ):
        rv = []
        for directory in (d for d in Path(voices_directory).iterdir() if d.is_dir()):
            try:
                voice = SonataVoice.from_path(directory)
            except ValueError:
                continue
            rv.append(voice)
        return rv

