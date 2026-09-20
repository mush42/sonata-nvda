# coding: utf-8
"""
Tests for the core TTS system logic in tts_system.py.

All NVDA internals and gRPC calls are stubbed by conftest.py.
No real gRPC server is required.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from sonata_neural_voices.tts_system import (
    SonataVoice,
    SonataTextToSpeechSystem,
    SpeechOptions,
    SilenceProvider,
    VoiceNotFoundError,
    SpeakerNotFoundError,
    Scales,
)
from sonata_neural_voices.const import (
    DEFAULT_RATE,
    DEFAULT_VOLUME,
    DEFAULT_PITCH,
    FALLBACK_SPEAKER_NAME,
    IGNORED_PUNCS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_voice(
    key="en-test-medium",
    name="Test",
    language="en",
    sample_rate=22050,
    is_multi_speaker=False,
    speakers=None,
):
    """Create a fully loaded SonataVoice without hitting the gRPC server."""
    v = SonataVoice(
        key=key,
        name=name,
        language=language,
        description="A test voice",
        location=Path("/tmp/fake-voice"),
        properties={"quality": "medium"},
    )
    v.remote_id = "fake-remote-id"
    v.supports_streaming_output = False
    v.sample_rate = sample_rate
    v.default_scales = Scales(length_scale=1.0, noise_scale=0.667, noise_w=0.8)
    v.is_multi_speaker = is_multi_speaker
    v.speakers = speakers or {}
    v.speaker_names = list((speakers or {}).values())
    v.default_speaker = None
    return v


@pytest.fixture
def single_voice():
    return _make_voice()


@pytest.fixture
def multi_voice():
    return _make_voice(
        key="en-multi-medium",
        name="Multi",
        is_multi_speaker=True,
        speakers={"0": "Alice", "1": "Bob"},
    )


@pytest.fixture
def voice_list(single_voice):
    return [
        single_voice,
        _make_voice(key="en-test+RT-medium", name="Test", language="en", sample_rate=16000),
        _make_voice(key="fr-durand-medium", name="Durand", language="fr"),
    ]


@pytest.fixture
def tts(voice_list):
    opts = SpeechOptions.__new__(SpeechOptions)
    opts.voice = voice_list[0]
    opts.rate = None
    opts.volume = None
    opts.pitch = None
    opts.sentence_silence_ms = None
    system = SonataTextToSpeechSystem.__new__(SonataTextToSpeechSystem)
    system.voices = voice_list
    system.speech_options = opts
    return system


# ---------------------------------------------------------------------------
# SonataVoice unit tests
# ---------------------------------------------------------------------------

class TestSonataVoiceFromPath:

    def test_parses_standard_key(self):
        v = SonataVoice.from_path("/tmp/en-john-medium")
        assert v.key == "en-john-medium"
        assert v.name == "john"
        assert v.language == "en"
        assert v.properties["quality"] == "medium"

    def test_parses_rt_key(self):
        v = SonataVoice.from_path("/tmp/en-john+RT-medium")
        # name should strip '+RT'
        assert v.name == "john"

    def test_invalid_path_raises(self):
        with pytest.raises(ValueError):
            SonataVoice.from_path("/tmp/notavalidkey")

    def test_is_fast_property(self, single_voice):
        assert not single_voice.is_fast
        fast = _make_voice(key="en-test+RT-medium")
        assert fast.is_fast

    def test_variant_property(self, single_voice):
        assert single_voice.variant == "standard"
        fast = _make_voice(key="en-test+RT-medium")
        assert fast.variant == "fast"

    def test_standard_variant_key(self, single_voice):
        assert single_voice.standard_variant_key == "en-test-medium"

    def test_fast_variant_key(self, single_voice):
        assert single_voice.fast_variant_key == "en-test+RT-medium"


# ---------------------------------------------------------------------------
# SilenceProvider unit tests
# ---------------------------------------------------------------------------

class TestSilenceProvider:

    def test_generates_correct_byte_length(self):
        # 100ms at 22050 Hz, 16-bit mono → 2 bytes/sample
        provider = SilenceProvider(time_ms=100, sample_rate=22050)
        audio = provider.generate_audio()
        expected_samples = int((100 / 1000.0) * 22050)
        assert len(audio) == expected_samples * 2

    def test_generates_silence_bytes(self):
        provider = SilenceProvider(time_ms=50, sample_rate=16000)
        audio = provider.generate_audio()
        assert all(b == 0 for b in audio)

    def test_zero_duration_returns_empty_bytes(self):
        provider = SilenceProvider(time_ms=0, sample_rate=22050)
        assert provider.generate_audio() == b""


# ---------------------------------------------------------------------------
# SonataTextToSpeechSystem — defaults
# ---------------------------------------------------------------------------

class TestTTSDefaults:

    def test_rate_default(self, tts):
        assert tts.rate == DEFAULT_RATE

    def test_volume_default(self, tts):
        assert tts.volume == DEFAULT_VOLUME

    def test_pitch_default(self, tts):
        assert tts.pitch == DEFAULT_PITCH

    def test_voice_key_matches(self, tts, voice_list):
        assert tts.voice == voice_list[0].key

    def test_language_matches_voice(self, tts):
        assert tts.language == "en"


# ---------------------------------------------------------------------------
# SonataTextToSpeechSystem — voice switching
# ---------------------------------------------------------------------------

class TestTTSVoiceSwitching:

    def test_set_valid_voice(self, tts, voice_list):
        tts.voice = voice_list[1].key
        assert tts.voice == voice_list[1].key

    def test_set_invalid_voice_raises(self, tts):
        with pytest.raises(VoiceNotFoundError):
            tts.voice = "xx-nonexistent-low"

    def test_set_language_exact_match(self, tts, voice_list):
        tts.language = "fr"
        assert tts.voice == voice_list[2].key

    def test_set_language_no_match_raises(self, tts):
        with pytest.raises(VoiceNotFoundError):
            tts.language = "ja"

    def test_set_language_returns_to_en_voice(self, tts, voice_list):
        """Setting language to 'fr' then back to 'en' should restore an English voice."""
        tts.language = "fr"
        assert tts.language == "fr"
        tts.language = "en"
        assert tts.language == "en"


# ---------------------------------------------------------------------------
# SonataTextToSpeechSystem — rate / volume / pitch
# ---------------------------------------------------------------------------

class TestTTSParameters:

    def test_set_rate(self, tts):
        tts.rate = 75
        assert tts.rate == 75

    def test_set_volume(self, tts):
        tts.volume = 80
        assert tts.volume == 80

    def test_set_pitch(self, tts):
        tts.pitch = 60
        assert tts.pitch == 60


# ---------------------------------------------------------------------------
# SonataTextToSpeechSystem — synthesis context
# ---------------------------------------------------------------------------

class TestSynthesisContext:

    def test_context_restores_rate(self, tts):
        tts.rate = 30
        with tts.create_synthesis_context():
            tts.rate = 99
        assert tts.rate == 30

    def test_context_restores_volume(self, tts):
        tts.volume = 50
        with tts.create_synthesis_context():
            tts.volume = 10
        assert tts.volume == 50

    def test_context_restores_voice(self, tts, voice_list):
        original = tts.voice
        with tts.create_synthesis_context():
            tts.voice = voice_list[1].key
        assert tts.voice == original


# ---------------------------------------------------------------------------
# SonataTextToSpeechSystem — providers
# ---------------------------------------------------------------------------

class TestProviders:

    def test_create_speech_provider_stores_text(self, tts):
        provider = tts.create_speech_provider("Hello world")
        assert provider.text == "Hello world"

    def test_create_break_provider_stores_time(self, tts):
        provider = tts.create_break_provider(500)
        assert provider.time_ms == 500
        assert provider.sample_rate == tts.speech_options.voice.sample_rate


# ---------------------------------------------------------------------------
# SonataTextToSpeechSystem — get_voice_variants
# ---------------------------------------------------------------------------

class TestGetVoiceVariants:

    def test_standard_and_rt_keys(self):
        std, rt = SonataTextToSpeechSystem.get_voice_variants("en-john-medium")
        assert std == "en-john-medium"
        assert rt == "en-john+RT-medium"

    def test_rt_key_is_normalized(self):
        std, rt = SonataTextToSpeechSystem.get_voice_variants("en-john+RT-medium")
        assert std == "en-john-medium"
        assert rt == "en-john+RT-medium"


# ---------------------------------------------------------------------------
# Speaker (single-speaker voice)
# ---------------------------------------------------------------------------

class TestSpeakerSingleVoice:

    def test_speaker_returns_fallback_for_single_speaker(self, tts):
        assert tts.speaker == FALLBACK_SPEAKER_NAME

    def test_set_speaker_on_non_multispeaker_is_noop(self, tts):
        # Should not raise
        tts.speaker = FALLBACK_SPEAKER_NAME


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:

    def test_ignored_puncs_is_frozenset(self):
        assert isinstance(IGNORED_PUNCS, frozenset)

    def test_default_values_are_in_range(self):
        assert 0 <= DEFAULT_RATE <= 100
        assert 0 <= DEFAULT_VOLUME <= 100
        assert 0 <= DEFAULT_PITCH <= 100

    def test_fallback_speaker_name_is_string(self):
        assert isinstance(FALLBACK_SPEAKER_NAME, str)
        assert FALLBACK_SPEAKER_NAME  # non-empty
