# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

from asyncio.exceptions import CancelledError
from collections import OrderedDict
from contextlib import suppress

import api
import config
import languageHandler
import synthDriverHandler
import tones
from autoSettingsUtils.driverSetting import BooleanDriverSetting, DriverSetting, NumericDriverSetting
from nvwave import WavePlayer
from logHandler import log
from speech import sayAll
from speech.commands import (
    BreakCommand,
    IndexCommand,
    LangChangeCommand,
    RateCommand,
    VolumeCommand,
    PitchCommand,
)
from synthDriverHandler import (
    SynthDriver,
    VoiceInfo,
    synthDoneSpeaking,
    synthIndexReached,
)

from . import grpc_client
from ._config import SonataConfig
from .helpers import update_displaied_params_on_voice_change
from .aio import (
    ASYNCIO_EVENT_LOOP,
    CancelledError,
    asyncio,
    asyncio_cancel_task,
    asyncio_coroutine_to_concurrent_future,
    run_in_executor,
)
from .tts_system import (
    SonataTextToSpeechSystem,
    SpeakerNotFoundError,
    SpeechOptions,
)
from .audio_processing import normalize_audio, mono_to_stereo_panned, apply_night_mode
from .phrase_cache import phrase_cache
from .structural_reading import split_into_segments

import addonHandler

addonHandler.initTranslation()


aio.initialize()
_GRPC_IS_INIT = grpc_client.initialize()


def _get_focus_pan() -> float:
    """
    Compute a stereo pan value [-1.0, +1.0] based on the horizontal position
    of the currently focused NVDA object on the screen.
    Returns 0.0 (centre) when position is unavailable.
    """
    try:
        import wx
        obj = api.getFocusObject()
        if obj is None:
            return 0.0
        loc = obj.location
        if loc is None:
            return 0.0
        screen_width = wx.SystemSettings.GetMetric(wx.SYS_SCREEN_X)
        if screen_width <= 0:
            return 0.0
        # Centre of the object relative to screen width → [-1, +1]
        centre_x = loc.left + loc.width / 2.0
        pan = (centre_x / screen_width) * 2.0 - 1.0
        return max(-1.0, min(1.0, pan))
    except Exception:
        return 0.0


class DoneSpeakingTask:
    __slots__ = ["player", "on_index_reached",]

    def __init__(self, player, onIndexReached):
        self.player = player
        self.on_index_reached = onIndexReached

    async def __call__(self):
        await run_in_executor(self.player.idle)
        await run_in_executor(self.on_index_reached, None)


class IndexReachedTask:
    __slots__ = ["callback", "index_list"]

    def __init__(self, callback, index_list):
        self.callback = callback
        self.index_list = index_list

    async def __call__(self):
        for index in self.index_list:
            await run_in_executor(self.callback, index)


class SpeechTask:
    __slots__ = [
        "task",
        "player",
        "normalize",
        "spatial_audio",
        "night_mode",
    ]

    def __init__(self, task, player, normalize=False, spatial_audio=False, night_mode=False):
        self.task = task
        self.player = player
        self.normalize = normalize
        self.spatial_audio = spatial_audio
        self.night_mode = night_mode

    async def __call__(self):
        if sayAll.SayAllHandler.isRunning():
            self.task.text = self.task.text.replace("\n", " ")
            self.task.speech_options.sentence_silence_ms = 50

        voice_key = self.task.speech_options.voice.key
        rate = self.task.speech_options.rate
        volume = self.task.speech_options.volume
        pitch = self.task.speech_options.pitch

        # --- Phrase cache check ---
        cached = phrase_cache.get(self.task.text, voice_key, rate, volume, pitch)
        if cached is not None:
            feed_func = self.player.feed
            for chunk in cached:
                await run_in_executor(feed_func, chunk)
            self.player.sync()
            return

        # --- Generate audio from gRPC ---
        speech_stream = await self.task.generate_audio()
        feed_func = self.player.feed
        collected_chunks = []

        # Compute pan once per utterance (position of focused object)
        pan = _get_focus_pan() if self.spatial_audio else 0.0

        async for wave_samples in speech_stream:
            chunk = wave_samples
            # Post-processing pipeline
            if self.night_mode:
                chunk = await run_in_executor(apply_night_mode, chunk)
            if self.normalize:
                chunk = await run_in_executor(normalize_audio, chunk)
            if self.spatial_audio:
                chunk = await run_in_executor(mono_to_stereo_panned, chunk, pan)
            collected_chunks.append(chunk)
            await run_in_executor(feed_func, chunk)

        self.player.sync()

        # Store in phrase cache (only if spatial audio is off — panned audio is
        # position-specific and must not be replayed at a different position)
        if not self.spatial_audio and collected_chunks:
            phrase_cache.put(self.task.text, voice_key, rate, volume, pitch, collected_chunks)


class BreakTask:
    __slots__ = [
        "task",
        "player",
    ]

    def __init__(self, task, player):
        self.task = task
        self.player = player

    async def __call__(self):
        await run_in_executor(self.player.feed, self.task.generate_audio())
        await run_in_executor(self.player.sync)


def SpeakerSetting():
    """Factory function for creating speaker setting."""
    return DriverSetting(
        "speaker",
        # Translators: Label for a setting in voice settings dialog.
        _("&Speaker"),
        availableInSettingsRing=True,
        # Translators: Label for a setting in synth settings ring.
        displayName=_("Speaker"),
    )

def create_wave_player(sample_rate, channels=1):
    return WavePlayer(
        channels=channels,
        samplesPerSec=sample_rate,
        bitsPerSample=16,
    )


async def _process_speech_sequence(speech_seq):
    for callable in speech_seq:
        try:
            await callable()
        except Exception as e:
            if isinstance(e, CancelledError):
                log.debug("Canceld speech task {callable}", exc_info=True)
            else:
                log.exception(f"Failed to execute speech task {callable}", exc_info=True)
            break


@asyncio_coroutine_to_concurrent_future
async def process_speech(speech_seq):
    speech_task = _process_speech_sequence(speech_seq)
    return ASYNCIO_EVENT_LOOP.create_task(speech_task)



class SynthDriver(synthDriverHandler.SynthDriver):

    supportedSettings = (
        SynthDriver.VoiceSetting(),
        SynthDriver.VariantSetting(),
        SpeakerSetting(),
        SynthDriver.RateSetting(),
        SynthDriver.RateBoostSetting(),
        SynthDriver.VolumeSetting(),
        SynthDriver.PitchSetting(),
        NumericDriverSetting("noise_scale", _("&Noise scale"), False),
        NumericDriverSetting("length_scale", _("&Length scale"), True),
        NumericDriverSetting("noise_w", _("Noise &w"), False),
        # Feature 3: Volume normalisation
        BooleanDriverSetting(
            "normalize_audio",
            # Translators: Label for normalize audio setting
            _("&Normalize audio volume"),
            defaultVal=False,
        ),
        # Feature 5: Spatial audio
        BooleanDriverSetting(
            "spatial_audio",
            # Translators: Label for spatial audio setting
            _("&Spatial audio (stereo panning)"),
            defaultVal=False,
        ),
        # Feature 8: Structural speaker alternation
        BooleanDriverSetting(
            "structural_reading",
            # Translators: Label for structural reading setting
            _("Alternate &speaker for brackets and quotes"),
            defaultVal=False,
        ),
    )
    supportedCommands = {
        IndexCommand,
        LangChangeCommand,
        BreakCommand,
        RateCommand,
        VolumeCommand,
        PitchCommand,
    }
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    description = "Sonata Neural Voices"
    name = "sonata_neural_voices"
    cachePropertiesByDefault = False

    # Feature 4: Night mode state
    _night_mode = False

    @classmethod
    def check(cls):
        return True

    def __init__(self):
        super().__init__()
        try:
            _GRPC_IS_INIT.result()
        except Exception:
            log.exception(
                f"Failed to initialize Sonata services. Synthesizer will not be available.",
                exc_info=True,
            )
            return
        try:
            sonata_grpc_server_version = grpc_client.check_grpc_server().result()
        except:
            log.exception(
                f"Failed to connect to sonata GRPC server. Synthesizer will not be available.",
                exc_info=True,
            )
            return
        log.info(f"Sonata GRPC server running on port {grpc_client.SONATA_GRPC_SERVER_PORT}")
        log.info("Connected to Sonata GRPC server")
        log.info(f"Sonata GRPC server version: {sonata_grpc_server_version}")
        if not any(SonataTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()):
            log.error(
                "No installed voices were found for Sonata. Synthesizer will not be available."
            )
            return
        self._current_task = None
        self._rateBoost = False
        self.voices = SonataTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()
        try:
            voice_key = config.conf["speech"]["sonata_neural_voices"]["voice"]
            configured_voice = next(
                filter(lambda v: v.key.startswith(voice_key), self.voices)
            )
        except (KeyError, StopIteration):
            configured_voice = self.voices[0]
        init_speech_options = SpeechOptions(voice=configured_voice)
        self.tts = SonataTextToSpeechSystem(
            self.voices, speech_options=init_speech_options
        )
        self._players = {}
        self._player = self._get_or_create_player(
            self.tts.speech_options.voice.sample_rate
        )
        self.availableLanguages = {v.language for v in self.voices}
        self._voice_map = {v.key: v for v in self.voices}
        self._standard_voice_map = {v.standard_variant_key: v for v in self.voices}
        self.availableVoices = self._get_valid_voices()
        self.__voice = None

    def terminate(self):
        self.cancel()
        self.tts.shutdown()
        for player in self._players.values():
            player.close()
        self._players.clear()
        aio.terminate()

    def speak(self, speechSequence):
        with self.tts.create_synthesis_context():
            self._fast_prepare_and_run_speech_task(speechSequence)

    def _fast_prepare_and_run_speech_task(self, speechSequence):
        self.cancel()
        speech_seq = []
        text_list = []
        index_command_list = []
        default_lang = self.tts.language

        # Read feature flags once per utterance
        do_normalize = self._get_normalize_audio()
        do_spatial = self._get_spatial_audio()
        do_structural = self._get_structural_reading()
        do_night = self.__class__._night_mode

        for item in speechSequence:
            item_type = type(item)
            if item_type is IndexCommand:
                index_command_list.append(item.index)
                continue
            elif item_type is str:
                text_list.append(item)
                continue
            if any(text_list):
                self._append_speech_tasks(
                    speech_seq, text_list,
                    do_normalize, do_spatial, do_night, do_structural,
                )
                text_list.clear()
            if item_type is BreakCommand:
                speech_seq.append(
                    BreakTask(
                        self.tts.create_break_provider(item.time),
                        self._player,
                    )
                )
            elif item_type is LangChangeCommand:
                if item.isDefault:
                    self.tts.language = default_lang
                else:
                    # Feature 7: graceful fallback — keep current voice if lang not found
                    try:
                        self.tts.language = item.lang
                    except Exception:
                        pass  # silently continue with current voice language
            elif item_type is RateCommand:
                self.tts.rate = item.newValue
            elif item_type is VolumeCommand:
                self.tts.volume = item.newValue
            elif item_type is PitchCommand:
                self.tts.pitch = item.newValue

        if any(text_list):
            self._append_speech_tasks(
                speech_seq, text_list,
                do_normalize, do_spatial, do_night, do_structural,
            )

        if any(index_command_list):
            speech_seq.append(IndexReachedTask(self._on_index_reached, index_command_list))
        speech_seq.append(
            DoneSpeakingTask(
                self._player, self._on_index_reached
            )
        )
        self._current_task = process_speech(
            speech_seq
        ).result()

    def _append_speech_tasks(self, speech_seq, text_list, do_normalize, do_spatial, do_night, do_structural):
        """Build SpeechTask(s) for the accumulated text, applying structural reading if enabled."""
        joined_text = "\n".join(text_list)
        voice = self.tts.speech_options.voice

        if do_structural and voice.is_multi_speaker and len(voice.speaker_names) >= 2:
            # Split text into main/aside segments and alternate speakers
            segments = split_into_segments(joined_text)
            default_speaker = voice.speaker
            alt_speaker = voice.speaker_names[1] if voice.speaker_names[0] == default_speaker else voice.speaker_names[0]

            for seg in segments:
                # Switch speaker for aside segments
                if seg.speaker_index is not None:
                    try:
                        voice.speaker = alt_speaker
                    except Exception:
                        pass
                else:
                    try:
                        voice.speaker = default_speaker
                    except Exception:
                        pass
                speech_seq.append(
                    SpeechTask(
                        self.tts.create_speech_provider(seg.text),
                        self._player,
                        normalize=do_normalize,
                        spatial_audio=do_spatial,
                        night_mode=do_night,
                    )
                )
            # Restore default speaker
            try:
                voice.speaker = default_speaker
            except Exception:
                pass
        else:
            speech_seq.append(
                SpeechTask(
                    self.tts.create_speech_provider(joined_text),
                    self._player,
                    normalize=do_normalize,
                    spatial_audio=do_spatial,
                    night_mode=do_night,
                )
            )

    def cancel(self):
        if self._current_task is not None:
            asyncio_cancel_task(self._current_task)
        self._player.stop()

    def pause(self, switch):
        self._player.pause(switch)

    def _on_index_reached(self, index):
        if index is not None:
            synthIndexReached.notify(synth=self, index=index)
        else:
            synthDoneSpeaking.notify(synth=self)

    def _get_or_create_player(self, sample_rate):
        # When spatial audio is active we need stereo players
        channels = 2 if self._get_spatial_audio() else 1
        key = (sample_rate, channels)
        if key not in self._players:
            self._players[key] = create_wave_player(sample_rate, channels)
        return self._players[key]

    # ------------------------------------------------------------------ #
    # Feature 3: Normalize audio                                           #
    # ------------------------------------------------------------------ #
    def _get_normalize_audio(self):
        return getattr(self, "_normalize_audio_enabled", False)

    def _set_normalize_audio(self, value):
        self._normalize_audio_enabled = bool(value)

    # ------------------------------------------------------------------ #
    # Feature 5: Spatial audio                                             #
    # ------------------------------------------------------------------ #
    def _get_spatial_audio(self):
        return getattr(self, "_spatial_audio_enabled", False)

    def _set_spatial_audio(self, value):
        enabled = bool(value)
        self._spatial_audio_enabled = enabled
        # Recreate player with correct channel count
        voice = self.tts.speech_options.voice
        self._player = self._get_or_create_player(voice.sample_rate)

    # ------------------------------------------------------------------ #
    # Feature 8: Structural reading                                        #
    # ------------------------------------------------------------------ #
    def _get_structural_reading(self):
        return getattr(self, "_structural_reading_enabled", False)

    def _set_structural_reading(self, value):
        self._structural_reading_enabled = bool(value)

    # ------------------------------------------------------------------ #
    # Feature 4: Night mode script                                         #
    # ------------------------------------------------------------------ #
    def script_toggleNightMode(self, gesture):
        self.__class__._night_mode = not self.__class__._night_mode
        if self.__class__._night_mode:
            # Translators: announced when night mode is turned on
            tones.beep(300, 80)
        else:
            # Translators: announced when night mode is turned off
            tones.beep(600, 80)

    script_toggleNightMode.__doc__ = _(
        # Translators: description of the toggle night mode script
        "Toggles Sonata night mode (soft, quiet audio)"
    )

    __gestures = {}

    # ------------------------------------------------------------------ #
    # Rate / Volume / Pitch                                               #
    # ------------------------------------------------------------------ #
    def _get_rateBoost(self):
        return self._rateBoost

    def _set_rateBoost(self, enable):
        if enable != self._rateBoost:
            rate = self.rate
            self._rateBoost = enable
            self.rate = rate

    def _get_rate(self):
        if self._rateBoost:
            return self.tts.rate
        else:
            self.tts.rate = min(40, self.tts.rate)
            return int(self.tts.rate * 2.5)

    def _set_rate(self, value):
        if self._rateBoost:
            self.tts.rate = value
        else:
            self.tts.rate = int(self._percentToParam(value, 0, 40))

    def _get_volume(self):
        return self.tts.volume

    def _set_volume(self, value):
        self.tts.volume = value
        self._player.setVolume(all=value / 100)

    def _get_pitch(self):
        return self.tts.pitch

    def _set_pitch(self, value):
        self.tts.pitch = value

    def _get_voice(self):
        return self._get_variant_independent_voice_id(self.tts.voice)

    def _get_noise_scale(self):
        factor = 50
        if hasattr(self, "_noise_scale_factor"):
            factor = self._noise_scale_factor
        elif self.voice in SonataConfig:
            factor = SonataConfig[self.voice].get("noise_scale", 50)
            self._noise_scale_factor = factor

        return factor

    def _set_noise_scale(self, value):
        voice = self.tts.speech_options.voice
        default_noise_scale = voice.default_scales.noise_scale
        if value == 50:
            self.tts.speech_options.voice.noise_scale = default_noise_scale
        else:
            self.tts.speech_options.voice.noise_scale = max(
                0.1, round(self._percentToParam(value, 0.0, default_noise_scale * 3), 2)
            )
        self._noise_scale_factor = value

    def _get_length_scale(self):
        factor = 50
        if hasattr(self, "_length_scale_factor"):
            factor = self._length_scale_factor
        elif self.voice in SonataConfig:
            factor = SonataConfig[self.voice].get("length_scale", 50)
            self._length_scale_factor = factor

        return factor

    def _set_length_scale(self, value):
        voice = self.tts.speech_options.voice
        default_length_scale = voice.default_scales.length_scale
        if value == 50:
            self.tts.speech_options.voice.length_scale = default_length_scale
        else:
            self.tts.speech_options.voice.length_scale = max(
                0.1,
                round(self._percentToParam(value, 0.0, default_length_scale * 2), 2),
            )

        self._length_scale_factor = value

    def _get_noise_w(self):
        factor = 50
        if hasattr(self, "_noise_w_factor"):
            factor = self._noise_w_factor
        elif self.voice in SonataConfig:
            factor = SonataConfig[self.voice].get("noise_w", 50)
            self._noise_w_factor = factor

        return factor

    def _set_noise_w(self, value):
        factor = getattr(self, "_noise_w_factor", None)
        if factor and value == factor:
            return

        voice = self.tts.speech_options.voice
        default_noise_w = voice.default_scales.noise_w
        if value == 50:
            self.tts.speech_options.voice.noise_w = default_noise_w
        else:
            self.tts.speech_options.voice.noise_w = max(
                0.1, round(self._percentToParam(value, 0.0, default_noise_w * 3), 2)
            )
        self._noise_w_factor = value

    def _set_voice(self, value):
        if value not in self.availableVoices:
            value = list(self.availableVoices)[0]
        self.__voice = value
        # Invalidate phrase cache for the old voice before switching
        if hasattr(self, "tts"):
            phrase_cache.invalidate_voice(self.tts.voice)
        with suppress(AttributeError):
            del self._availableVariants
        with suppress(AttributeError):
            del self._availableSpeakers
        self.tts.voice = self._standard_voice_map[value].key
        if value in SonataConfig:
            variant = SonataConfig[value].get("variant", self.variant)
            speaker = SonataConfig[value].get("speaker")
        else:
            variant = self._standard_voice_map[value].variant
            speaker = None
        self._set_variant(variant)

        # Reset params
        self.noise_scale = self.noise_scale
        self.length_scale = self.length_scale
        self.noise_w = self.noise_w

        if speaker is not None:
            self._set_speaker(speaker)
        # Update gui if shown
        try:
            update_displaied_params_on_voice_change(self)
        except Exception:
            log.exception("Failed to update Speech GUI", exc_info=True)

    def _get_language(self):
        return self.tts.language

    def _set_language(self, value):
        self.tts.language = value

    def _get_variant(self):
        return self.tts.speech_options.voice.variant

    def _set_variant(self, value):
        variant = value.lower()
        if variant == "standard":
            voice_key = self.tts.speech_options.voice.standard_variant_key
        elif variant == "fast":
            voice_key = self.tts.speech_options.voice.fast_variant_key
        else:
            log.info(f"Unknown voice variant: {variant}")
            return
        if voice_key not in self._voice_map:
            return
        prev_speaker = self.tts.speech_options.voice.speaker
        self.tts.voice = voice_key
        self.tts.speech_options.voice.speaker = prev_speaker
        SonataConfig.setdefault(self.voice, {})["variant"] = value
        voice = self.tts.speech_options.voice
        self._player = self._get_or_create_player(voice.sample_rate)

    def _getAvailableVariants(self):
        std_key, rt_key = SonataTextToSpeechSystem.get_voice_variants(self.__voice)
        rv = OrderedDict()
        if std_key in self._voice_map:
            rv["standard"] = VoiceInfo("standard", "Standard", self.language)
        if rt_key in self._voice_map:
            rv["fast"] = VoiceInfo("fast", "Fast", self.language)
        return rv

    def _get_variant_independent_voice_id(self, voice_key):
        return SonataTextToSpeechSystem.get_voice_variants(voice_key)[0]

    def _get_valid_voices(self):
        all_voices = OrderedDict()
        for voice in self.voices:
            voice_id = self._get_variant_independent_voice_id(voice.key)
            quality = voice.properties["quality"]
            lang = languageHandler.normalizeLanguage(voice.language).replace("_", "-")
            display_name = f"{voice.name} ({lang}) - {quality}"
            all_voices[voice_id] = VoiceInfo(voice_id, display_name, voice.language)
        return all_voices

    def _get_speaker(self):
        return self.tts.speaker

    def _set_speaker(self, value):
        try:
            self.tts.speaker = value
            SonataConfig.setdefault(self.voice, {})["speaker"] = value
        except SpeakerNotFoundError:
            SonataConfig.setdefault(self.voice, {})["speaker"] = self.tts.speaker

    def _get_availableSpeakers(self):
        return {spk: VoiceInfo(spk, spk, None) for spk in sorted(self.tts.get_speakers())}
