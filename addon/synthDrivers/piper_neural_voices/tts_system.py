# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

import copy
import io
import operator
import os
import re
import string
import sys
import tarfile
import typing
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence, Union

import globalVars
from languageHandler import normalizeLanguage

from . import aio
from . import grpc_client
from .helpers import import_bundled_library, LIB_DIRECTORY


with import_bundled_library():
    from pathlib import Path


PIPER_VOICE_SAMPLES_URL = "https://rhasspy.github.io/piper-samples/"
PIPER_VOICES_DIR = os.path.join(
    globalVars.appArgs.configPath, "piper", "voices", "v1.0"
)
BATCH_SIZE = max(os.cpu_count() // 2, 2)
FALLBACK_SPEAKER_NAME = "default"
DEFAULT_RATE = 50
DEFAULT_VOLUME = 100
DEFAULT_PITCH = 50


class VoiceNotFoundError(LookupError):
    pass


class SpeakerNotFoundError(LookupError):
    pass


class AudioTask(ABC):
    @abstractmethod
    def generate_audio(self) -> bytes:
        """Generate audio."""


class SilenceTask(AudioTask):
    __slots__ = ["time_ms", "sample_rate"]

    def __init__(self, time_ms, sample_rate):
        self.time_ms = time_ms
        self.sample_rate = sample_rate

    async def generate_audio(self):
        """Generate silence (16-bit mono at sample rate)."""
        num_samples = int((self.time_ms / 1000.0) * self.sample_rate)
        return bytes(num_samples * 2)


@dataclass
class Scales:
    length_scale: float
    noise_scale: float
    noise_w: float


@dataclass
class PiperSpeechSynthesisTask(AudioTask):
    """A pending request to synthesize a token."""

    __slots__ = ["text", "speech_options"]

    def __init__(self, text, speech_options):
        self.text = text
        self.speech_options = speech_options

    async def generate_audio(self):
        return await self.speech_options.speak_text(self.text)


@dataclass
class PiperVoice:
    key: str
    name: str
    language: str
    description: str
    location: str
    properties: typing.Optional[typing.Mapping[str, int]] = field(default_factory=dict)
    remote_id: str = None

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
            self.model_path = next(self.location.glob("*.onnx"))
            self.config_path = next(self.location.glob("*.onnx.json"))
        except StopIteration:
            raise RuntimeError(
                f"Could not load voice from `{os.fspath(self.location)}`"
            )
        voice_info = grpc_client.load_voice(
            os.fspath(self.model_path), os.fspath(self.config_path)
        ).result()
        self.remote_id = voice_info.voice_id
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

    async def synthesize(self, text, rate, volume, pitch):
        stream = grpc_client.speak(
            voice_id=self.remote_id,
            text=text,
            rate=rate,
            volume=volume,
            pitch=pitch,
        )
        async for ret in stream:
            yield ret.wav_samples


class SpeechOptions:
    __slots__ = ["voice", "rate", "volume", "pitch"]

    def __init__(self, voice, speaker=None, rate=None, volume=None, pitch=None):
        self.set_voice(voice)
        self.rate = rate
        self.volume = volume
        self.pitch = pitch

    def set_voice(self, voice: PiperVoice):
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
        )


class PiperTextToSpeechSystem:

    VOICE_NAME_REGEX = re.compile(        r"voice(-|_)(?P<language>[a-z]+[_]?([a-z]+)?)(-|_)(?P<name>[a-z]+)(-|_)(?P<quality>(high|medium|low|x-low))"
    )

    def __init__(
        self, voices: Sequence[PiperVoice], speech_options: SpeechOptions = None
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
        return self.speech_options.volume or DEFAULT_VOLUME

    @volume.setter
    def volume(self, new_volume: float):
        """Set the current volume in [0, 100]"""
        self.speech_options.volume = new_volume

    @property
    def rate(self) -> float:
        """Get the current speaking rate in [0, 100]"""
        return self.speech_options.rate or DEFAULT_RATE

    @rate.setter
    def rate(self, new_rate: float):
        """Set the current speaking rate in [0, 100]"""
        self.speech_options.rate = new_rate

    @property
    def pitch(self) -> float:
        """Get the current speaking pitch in [0, 100]"""
        return self.speech_options.pitch or DEFAULT_PITCH

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

    def create_speech_task(self, text):
        return PiperSpeechSynthesisTask(text, self.speech_options.copy())

    def create_break_task(self, time_ms):
        return SilenceTask(time_ms, self.speech_options.voice.sample_rate)

    @classmethod
    def load_piper_voices_from_nvda_config_dir(cls):
        Path(PIPER_VOICES_DIR).mkdir(parents=True, exist_ok=True)
        return sorted(
            cls.load_voices_from_directory(PIPER_VOICES_DIR),
            key=operator.attrgetter("key"),
        )

    @classmethod
    def load_voices_from_directory(
        cls, voices_directory, *, directory_name_prefix="voice-"
    ):
        rv = []
        for directory in (d for d in Path(voices_directory).iterdir() if d.is_dir()):
            try:
                voice = PiperVoice.from_path(directory)
            except ValueError:
                continue
            rv.append(voice)
        return rv

    @classmethod
    def install_voice(cls, voice_archive_path, dest_dir):
        """Uniform handleing of voice tar archives."""
        archive_path = Path(voice_archive_path)
        voice_name = archive_path.name.rstrip("".join(archive_path.suffixes))
        match = cls.VOICE_NAME_REGEX.match(voice_name)
        if match is None:
            raise ValueError(f"Invalid voice archive: `{archive_path}`")
        info = match.groupdict()
        language = info["language"]
        name = info["name"]
        quality = info["quality"]
        voice_key = f"{language}-{name}-{quality}"
        with tarfile.open(os.fspath(archive_path), "r:gz") as tar:
            members = tar.getmembers()
            try:
                m_onnx_model = next(m for m in members if m.name.endswith(".onnx"))
                m_model_config = next(
                    m for m in members if m.name.endswith(".onnx.json")
                )
            except StopIteration:
                raise ValueError(f"Invalid voice archive: `{archive_path}`")
            dst = Path(dest_dir).joinpath(voice_key)
            dst.mkdir(parents=True, exist_ok=True)
            tar.extract(m_onnx_model, path=os.fspath(dst), set_attrs=False)
            tar.extract(m_model_config, path=os.fspath(dst), set_attrs=False)
            try:
                m_model_card = next(m for m in members if m.name.endswith("MODEL_CARD"))
            except StopIteration:
                pass
            else:
                tar.extract(m_model_card, path=os.fspath(dst), set_attrs=False)
            return voice_key