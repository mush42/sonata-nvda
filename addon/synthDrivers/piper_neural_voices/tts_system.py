# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.
# Portions are adopted from Piper source-code (https://github.com/rhasspy/piper/)

import audioop
import copy
import io
import json
import os
import operator
import re
import sys
import string
import tarfile
import typing
import wave

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence, Union

import globalVars

_LIB_PATH = os.path.join(
    os.path.abspath(os.path.dirname(__file__)),
    "lib"
)
sys.path.insert(0, _LIB_PATH)
from pathlib import Path
import numpy as np
import onnxruntime
from espeak_phonemizer  import Phonemizer
sys.path.remove(_LIB_PATH)


NVDA_ESPEAK_DIR = Path(globalVars.appDir).joinpath("synthDrivers")
VOICE_NAME_REGEX = re.compile(r"voice(-|_)(?P<language>[a-z]+[-]?([a-z]+)?)(-|_)(?P<name>[a-z]+)(-|_)(?P<quality>(high|medium|low|x-low))")
DEFAULT_RATE = 50
DEFAULT_VOLUME = 100
PIPER_VOICE_SAMPLES_URL = "https://rhasspy.github.io/piper-samples/"
PIPER_VOICES_DIR = Path(globalVars.appArgs.configPath).joinpath("piper", "voices")

_BOS = "^"
_EOS = "$"
_PAD = "_"


class VoiceNotFoundError(LookupError) :
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

    def generate_audio(self):
        """Generate silence (16-bit mono at sample rate)."""
        num_samples = int((time_ms / 1000.0) * sample_rate)
        return bytes(num_samples * 2)



@dataclass
class PiperVoice:
    key: str
    name: str
    language: str
    description: str
    location: str
    properties: typing.Optional[typing.Mapping[str, int]] = field(default_factory=dict)

    def __post_init__(self):
        try:
            self.model_path = next(self.location.glob("*.onnx"))
            self.config_path = next(self.location.glob("*.onnx.json"))
        except StopIteration:
            raise RuntimeError(f"Could not load voice from `{os.fspath(self.location)}`")
        self.config = PiperConfig.load_from_json_file(self.config_path)
        self.__piper_model = None
        self.speakers = tuple(self.config.speaker_id_map.keys())

    @property
    def model(self):
        if self.__piper_model is None:
            self.__piper_model = PiperModel(os.fspath(self.model_path), os.fspath(self.config_path))
        return self.__piper_model

    def phonemize_text(self, text):
        return self.model.text_to_phonemes(text)

    def synthesize(self, text, speaker, rate):
        phonemes = self.phonemize_text(text)
        length_scale = self.config.length_scale
        if rate != DEFAULT_RATE:
            rate = rate or 1
            length_scale = length_scale * (50/rate)
            # Cap length_scale at 2.0 to avoid horrifying  audio result
            length_scale = 2. if length_scale > 2 else length_scale
        speaker_id = None
        if self.config.num_speakers > 1:
            if speaker is None:
                speaker_id = 0
            else:
                speaker_id=self.config.speaker_id_map.get(speaker)
        return self.model.synthesize_to_audio_bytes(
            phonemes=phonemes,
            speaker_id=speaker_id,
            length_scale=length_scale
        )


class SpeechOptions:
    __slots__ = ["voice", "speaker", "rate", "volume"]

    def __init__(self, voice, speaker=None, rate=DEFAULT_RATE, volume=DEFAULT_VOLUME):
        self.voice = voice
        self.speaker = speaker
        self.rate = rate
        self.volume = volume

    def set_voice(self, voice: PiperVoice):
        self.voice = voice
        self.speaker = None

    def copy(self):
        return copy.copy(self)


@dataclass
class PiperSpeechSynthesisTask(AudioTask):
    """A pending request to synthesize a token."""
    __slots__ = ["text", "speech_options"]

    def __init__(self, text, speech_options):
        self.text = text
        self.speech_options = speech_options

    def generate_audio(self):
        audio_bytes = self.speech_options.voice.synthesize(
            self.text,
            self.speech_options.speaker,
            self.speech_options.rate
        )
        volume = self.speech_options.volume
        if volume != DEFAULT_VOLUME:
            audio_bytes = audioop.mul(audio_bytes, 2, volume / 100.0)
        return audio_bytes


class PiperTextToSpeechSystem:

    def __init__(
        self,
        voices: Sequence[PiperVoice],
        speech_options: SpeechOptions=None
    ):
        self.voices = voices
        if speech_options is None:
            try:
                voice = self.voices[0]
            except IndexError:
                raise VoiceNotFoundError("No Piper voices found")
            self.speech_options = SpeechOptions(voice=voice)
        else:
            speech_options = speech_options

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
        raise VoiceNotFoundError(f"A voice with the given key `{new_voice}` was not found")

    @property
    def language(self) -> str:
        """Get the current voice language"""
        return self.speech_options.voice.language

    @language.setter
    def language(self, new_language: str):
        """Set the current voice language"""
        for voice in self.voices:
            if voice.language == new_language:
                self.speech_options.set_voice(voice)
                return
        raise VoiceNotFoundError(f"A voice with the given language `{new_language}` was not found")

    @property
    def volume(self) -> float:
        """Get the current volume in [0, 100]"""
        return self.speech_options.volume

    @volume.setter
    def volume(self, new_volume: float):
        """Set the current volume in [0, 100]"""
        self.speech_options.volume = new_volume

    @property
    def rate(self) -> float:
        """Get the current speaking rate in [0, 100]"""
        return self.speech_options.rate

    @rate.setter
    def rate(self, new_rate: float):
        """Set the current speaking rate in [0, 100]"""
        self.speech_options.rate = new_rate

    def get_voices(self):
        return self.voices

    def create_speech_task(self, text):
        return PiperSpeechSynthesisTask(
            text,
            self.speech_options.copy()
        )

    def create_break_task(self, time_ms):
        return SilenceTask(time_ms, self.speech_options.voice.config.sample_rate)

    @classmethod
    def load_piper_voices_from_nvda_config_dir(cls):
        PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        return sorted(
            cls.load_voices_from_directory(PIPER_VOICES_DIR),
            key=operator.attrgetter("name")
        )

    @staticmethod
    def load_voices_from_directory(voices_directory, *, directory_name_prefix="voice-"):
        rv = []
        for directory in (d for d in Path(voices_directory).iterdir() if d.is_dir()):
            match = VOICE_NAME_REGEX.match(directory.name)
            if match is None:
                continue
            info = match.groupdict()
            language = info["language"]
            name = info["name"]
            quality = info["quality"]
            rv.append(
                PiperVoice(
                    key=f"{language}-{name}-{quality}",
                    name=name.title(),
                    language=language,
                    description="",
                    location=directory.absolute(),
                    properties={"quality": quality}
                )
            )
        return rv

    @staticmethod
    def install_voice(voice_archive_path, dest_dir):
        """Uniform handleing of voice tar archives."""
        archive_path = Path(voice_archive_path)
        voice_name = archive_path.name.rstrip("".join(archive_path.suffixes))
        match = VOICE_NAME_REGEX.match(voice_name)
        if match is None:
            raise ValueError(f"Invalid voice archive: `{archive_path}`")
        info = match.groupdict()
        language = info["language"]
        name = info["name"]
        quality = info["quality"]
        voice_key = f"voice-{language}-{name}-{quality}"
        with tarfile.open(os.fspath(archive_path), "r:gz") as tar:
            members = tar.getmembers()
            try:
                m_onnx_model = next(m for m in members if m.name.endswith(".onnx"))
                m_model_config = next(m for m in members if m.name.endswith(".onnx.json"))
            except StopIteration:
                raise ValueError(f"Invalid voice archive: `{archive_path}`")
            dst = Path(dest_dir).joinpath(voice_key)
            dst.mkdir(parents=True, exist_ok=True)
            tar.extract(m_onnx_model, path=os.fspath(dst), set_attrs=False)
            tar.extract(m_model_config, path=os.fspath(dst), set_attrs=False)
            return voice_key


@dataclass
class PiperConfig:
    num_symbols: int
    num_speakers: int
    sample_rate: int
    espeak_voice: str
    length_scale: float
    noise_scale: float
    noise_w: float
    phoneme_id_map: Mapping[str, Sequence[int]]
    speaker_id_map: Mapping[str, int]

    @classmethod
    def load_from_json_file(cls, config_path: Union[str, Path]):
        with open(config_path, "r", encoding="utf-8") as config_file:
            config_dict = json.load(config_file)
            inference = config_dict.get("inference", {})

            return cls(
                num_symbols=config_dict["num_symbols"],
                num_speakers=config_dict["num_speakers"],
                sample_rate=config_dict["audio"]["sample_rate"],
                espeak_voice=config_dict["espeak"]["voice"],
                noise_scale=inference.get("noise_scale", 0.667),
                length_scale=inference.get("length_scale", 1.0),
                noise_w=inference.get("noise_w", 0.8),
                phoneme_id_map=config_dict["phoneme_id_map"],
                speaker_id_map=config_dict["speaker_id_map"],
            )


class PiperModel:
    def __init__(
        self,
        model_path: Union[str, Path],
        config_path: Optional[Union[str, Path]] = None,
        use_cuda: bool = False,
    ):
        if config_path is None:
            config_path = f"{model_path}.json"

        self.config = PiperConfig.load_from_json_file(config_path)
        self.phonemizer = Phonemizer(
            self.config.espeak_voice,
            espeak_ng_dll=os.fspath(NVDA_ESPEAK_DIR.joinpath("espeak.dll")),
            espeak_ng_data_directory=os.fspath(NVDA_ESPEAK_DIR)
        )

        session_options = onnxruntime.SessionOptions()
        session_options.enable_cpu_mem_arena = True
        session_options.enable_mem_pattern = True
        session_options.enable_mem_reuse = True
        session_options.execution_order = onnxruntime.ExecutionOrder.PRIORITY_BASED
        session_options.execution_mode = onnxruntime.ExecutionMode.ORT_PARALLEL
        session_options.enable_profiling = False
        session_options.inter_op_num_threads = int(os.cpu_count() / 2)
        session_options.intra_op_num_threads = int(os.cpu_count() / 2)

        self.model = onnxruntime.InferenceSession(
            str(model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"]
            if not use_cuda
            else ["CUDAExecutionProvider"],
        )

    def synthesize_to_audio_bytes(
        self,
        phonemes: str,
        speaker_id: Optional[int] = None,
        length_scale: Optional[float] = None,
        noise_scale: Optional[float] = None,
        noise_w: Optional[float] = None,
    ) -> bytes:
        """Synthesize frameless WAV audio from text."""
        if length_scale is None:
            length_scale = self.config.length_scale

        if noise_scale is None:
            noise_scale = self.config.noise_scale

        if noise_w is None:
            noise_w = self.config.noise_w

        phoneme_id_map = self.config.phoneme_id_map
        _pad = self.config.phoneme_id_map[_PAD]
        phoneme_ids: List[int] = []
        for phoneme in (p for p in phonemes if p in phoneme_id_map):
            phoneme_ids.extend(phoneme_id_map[phoneme])
            phoneme_ids.extend(_pad)
        phoneme_ids.extend(self.config.phoneme_id_map[_EOS])
        phoneme_ids_array = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        phoneme_ids_lengths = np.array([phoneme_ids_array.shape[1]], dtype=np.int64)
        scales = np.array(
            [noise_scale, length_scale, noise_w],
            dtype=np.float32,
        )
        if (self.config.num_speakers > 1) and (speaker_id is not None):
            # Default speaker
            speaker_id = 0
        sid = None
        if speaker_id is not None:
            sid = np.array([speaker_id], dtype=np.int64)
        # Synthesize through Onnx
        audio = self.model.run(
            None,
            {
                "input": phoneme_ids_array,
                "input_lengths": phoneme_ids_lengths,
                "scales": scales,
                "sid": sid,
            },
        )[0].squeeze((0, 1))
        audio = self.audio_float_to_int16(audio.squeeze())
        return audio.tobytes()

    def synthesize_to_wav(
        self,
        text: str,
        speaker_id: Optional[int] = None,
        length_scale: Optional[float] = None,
        noise_scale: Optional[float] = None,
        noise_w: Optional[float] = None,
    ):
        audio_bytes = self.synthesize_to_audio_bytes(text, speaker_id, length_scale, noise_scale, noise_w)
        # Convert to WAV
        with io.BytesIO() as wav_io:
            wav_file: wave.Wave_write = wave.open(wav_io, "wb")
            with wav_file:
                wav_file.setframerate(self.config.sample_rate)
                wav_file.setsampwidth(2)
                wav_file.setnchannels(1)
                wav_file.writeframes(audio_bytes)
            return wav_io.getvalue()

    def text_to_phonemes(self, text, text_language=None):
        # RStrip `.` character from the end of the text because it causes unusual audio output
        text = text.rstrip(".")
        phonemes_str = self.phonemizer.phonemize(text, keep_clause_breakers=True)
        phonemes = [_BOS] + list(phonemes_str)
        return phonemes

    def word_to_phonemes(self, word_text, word_role=None, text_language=None):
        return self.text_to_phonemes(word_text, text_language=text_language)

    def say_as_to_phonemes(self, text, interpret_as, say_format=None, text_language=None):
        return self.text_to_phonemes(text, text_language=text_language)

    @staticmethod
    def audio_float_to_int16(
        audio: np.ndarray, max_wav_value: float = 32767.0
    ) -> np.ndarray:
        """Normalize audio and convert to int16 range"""
        audio_norm = audio * (max_wav_value / max(0.01, np.max(np.abs(audio))))
        audio_norm = np.clip(audio_norm, -max_wav_value, max_wav_value)
        audio_norm = audio_norm.astype("int16")
        return audio_norm
