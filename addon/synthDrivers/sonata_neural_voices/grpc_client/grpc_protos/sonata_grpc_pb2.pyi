from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SynthesisMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MODE_UNSPECIFIED: _ClassVar[SynthesisMode]
    MODE_LAZY: _ClassVar[SynthesisMode]
    MODE_PARALLEL: _ClassVar[SynthesisMode]
    MODE_BATCHED: _ClassVar[SynthesisMode]

class Quality(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    QUALITY_UNSPECIFIED: _ClassVar[Quality]
    QUALITY_X_LOW: _ClassVar[Quality]
    QUALITY_LOW: _ClassVar[Quality]
    QUALITY_MEDIUM: _ClassVar[Quality]
    QUALITY_HIGH: _ClassVar[Quality]
MODE_UNSPECIFIED: SynthesisMode
MODE_LAZY: SynthesisMode
MODE_PARALLEL: SynthesisMode
MODE_BATCHED: SynthesisMode
QUALITY_UNSPECIFIED: Quality
QUALITY_X_LOW: Quality
QUALITY_LOW: Quality
QUALITY_MEDIUM: Quality
QUALITY_HIGH: Quality

class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Version(_message.Message):
    __slots__ = ("version",)
    VERSION_FIELD_NUMBER: _ClassVar[int]
    version: str
    def __init__(self, version: _Optional[str] = ...) -> None: ...

class VoiceIdentifier(_message.Message):
    __slots__ = ("voice_id",)
    VOICE_ID_FIELD_NUMBER: _ClassVar[int]
    voice_id: str
    def __init__(self, voice_id: _Optional[str] = ...) -> None: ...

class VoiceInfo(_message.Message):
    __slots__ = ("voice_id", "synth_options", "speakers", "audio", "language", "quality", "supports_streaming_output")
    class SpeakersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: str
        def __init__(self, key: _Optional[int] = ..., value: _Optional[str] = ...) -> None: ...
    VOICE_ID_FIELD_NUMBER: _ClassVar[int]
    SYNTH_OPTIONS_FIELD_NUMBER: _ClassVar[int]
    SPEAKERS_FIELD_NUMBER: _ClassVar[int]
    AUDIO_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    QUALITY_FIELD_NUMBER: _ClassVar[int]
    SUPPORTS_STREAMING_OUTPUT_FIELD_NUMBER: _ClassVar[int]
    voice_id: str
    synth_options: SynthesisOptions
    speakers: _containers.ScalarMap[int, str]
    audio: AudioInfo
    language: str
    quality: Quality
    supports_streaming_output: bool
    def __init__(self, voice_id: _Optional[str] = ..., synth_options: _Optional[_Union[SynthesisOptions, _Mapping]] = ..., speakers: _Optional[_Mapping[int, str]] = ..., audio: _Optional[_Union[AudioInfo, _Mapping]] = ..., language: _Optional[str] = ..., quality: _Optional[_Union[Quality, str]] = ..., supports_streaming_output: bool = ...) -> None: ...

class VoicePath(_message.Message):
    __slots__ = ("config_path",)
    CONFIG_PATH_FIELD_NUMBER: _ClassVar[int]
    config_path: str
    def __init__(self, config_path: _Optional[str] = ...) -> None: ...

class Utterance(_message.Message):
    __slots__ = ("voice_id", "text", "speech_args", "synthesis_mode")
    VOICE_ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    SPEECH_ARGS_FIELD_NUMBER: _ClassVar[int]
    SYNTHESIS_MODE_FIELD_NUMBER: _ClassVar[int]
    voice_id: str
    text: str
    speech_args: SpeechArgs
    synthesis_mode: SynthesisMode
    def __init__(self, voice_id: _Optional[str] = ..., text: _Optional[str] = ..., speech_args: _Optional[_Union[SpeechArgs, _Mapping]] = ..., synthesis_mode: _Optional[_Union[SynthesisMode, str]] = ...) -> None: ...

class SynthesisOptions(_message.Message):
    __slots__ = ("speaker", "length_scale", "noise_scale", "noise_w")
    SPEAKER_FIELD_NUMBER: _ClassVar[int]
    LENGTH_SCALE_FIELD_NUMBER: _ClassVar[int]
    NOISE_SCALE_FIELD_NUMBER: _ClassVar[int]
    NOISE_W_FIELD_NUMBER: _ClassVar[int]
    speaker: str
    length_scale: float
    noise_scale: float
    noise_w: float
    def __init__(self, speaker: _Optional[str] = ..., length_scale: _Optional[float] = ..., noise_scale: _Optional[float] = ..., noise_w: _Optional[float] = ...) -> None: ...

class VoiceSynthesisOptions(_message.Message):
    __slots__ = ("voice_id", "synthesis_options")
    VOICE_ID_FIELD_NUMBER: _ClassVar[int]
    SYNTHESIS_OPTIONS_FIELD_NUMBER: _ClassVar[int]
    voice_id: str
    synthesis_options: SynthesisOptions
    def __init__(self, voice_id: _Optional[str] = ..., synthesis_options: _Optional[_Union[SynthesisOptions, _Mapping]] = ...) -> None: ...

class AudioInfo(_message.Message):
    __slots__ = ("sample_rate", "num_channels", "sample_width")
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    NUM_CHANNELS_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_WIDTH_FIELD_NUMBER: _ClassVar[int]
    sample_rate: int
    num_channels: int
    sample_width: int
    def __init__(self, sample_rate: _Optional[int] = ..., num_channels: _Optional[int] = ..., sample_width: _Optional[int] = ...) -> None: ...

class SynthesisResult(_message.Message):
    __slots__ = ("wav_samples", "rtf")
    WAV_SAMPLES_FIELD_NUMBER: _ClassVar[int]
    RTF_FIELD_NUMBER: _ClassVar[int]
    wav_samples: bytes
    rtf: float
    def __init__(self, wav_samples: _Optional[bytes] = ..., rtf: _Optional[float] = ...) -> None: ...

class WaveSamples(_message.Message):
    __slots__ = ("wav_samples",)
    WAV_SAMPLES_FIELD_NUMBER: _ClassVar[int]
    wav_samples: bytes
    def __init__(self, wav_samples: _Optional[bytes] = ...) -> None: ...

class SpeechArgs(_message.Message):
    __slots__ = ("rate", "volume", "pitch", "appended_silence_ms")
    RATE_FIELD_NUMBER: _ClassVar[int]
    VOLUME_FIELD_NUMBER: _ClassVar[int]
    PITCH_FIELD_NUMBER: _ClassVar[int]
    APPENDED_SILENCE_MS_FIELD_NUMBER: _ClassVar[int]
    rate: int
    volume: int
    pitch: int
    appended_silence_ms: int
    def __init__(self, rate: _Optional[int] = ..., volume: _Optional[int] = ..., pitch: _Optional[int] = ..., appended_silence_ms: _Optional[int] = ...) -> None: ...
