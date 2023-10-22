# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

import queue
import sys
import threading
import webbrowser
from collections import OrderedDict
from contextlib import suppress
from functools import partial
from itertools import zip_longest

import config
import globalVars
import languageHandler
import nvwave
import synthDriverHandler
from autoSettingsUtils.driverSetting import DriverSetting, NumericDriverSetting
from logHandler import log
from speech.sayAll import SayAllHandler
from speech.commands import (
    BreakCommand,
    CharacterModeCommand,
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


from . import aio
from . import grpc_client
from ._config import PiperConfig
from .tts_system import (
    PIPER_VOICE_SAMPLES_URL,
    AudioTask,
    PiperTextToSpeechSystem,
    SilenceTask,
    SpeakerNotFoundError,
    SpeechOptions,
)


import addonHandler

addonHandler.initTranslation()


# This should run from the check method
grpc_client.initialize()


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


class DoneSpeakingTask:
    __slots__ = ["player", "on_index_reached", "is_canceled"]

    def __init__(self, player, onIndexReached, is_canceled):
        self.player = player
        self.on_index_reached = onIndexReached
        self.is_canceled = is_canceled

    async def __call__(self):
        await aio.run_in_executor(self.player.idle)
        await aio.run_in_executor(self.on_index_reached, None)


class IndexReachedTask:
    def __init__(self, callback, index):
        self.callback = callback
        self.index = index

    async def __call__(self):
        await aio.run_in_executor(self.callback, self.index)


class SpeechTask:
    __slots__ = [
        "task",
        "player",
        "is_canceled",
    ]

    def __init__(self, task, player, is_canceled):
        self.task = task
        self.player = player
        self.is_canceled = is_canceled

    async def __call__(self):
        if self.is_canceled():
            return
        stream = await self.task.generate_audio()
        async for wave_samples in stream:
            await aio.run_in_executor(self.player.feed, wave_samples)
        await aio.run_in_executor(self.player.idle)


class BreakTask:
    __slots__ = [
        "task",
        "player",
        "is_canceled",
    ]

    def __init__(self, task, player, is_canceled):
        self.task = task
        self.player = player
        self.is_canceled = is_canceled

    async def __call__(self):
        if not self.is_canceled():
            await aio.run_in_executor(self.player.feed, self.task.generate_audio())
            await aio.run_in_executor(self.player.idle)


async def _process_speech_sequence(speech_seq, is_canceled):
    if is_canceled():
        return
    for callable in speech_seq:
        try:
            await callable()
        except aio.CancelledError:
            log.debug(f"Canceld speech task {callable}", exc_info=True)
        except:
            log.exception(f"Failed to execute speech task {callable}", exc_info=True)


@aio.asyncio_coroutine_to_concurrent_future
async def process_speech(speech_seq, is_canceled):
    speech_task = _process_speech_sequence(speech_seq, is_canceled)
    return aio.ASYNCIO_EVENT_LOOP.create_task(speech_task)


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

    description = "Piper Neural Voices"
    name = "piper_neural_voices"
    cachePropertiesByDefault = False

    @classmethod
    def check(cls):
        try:
            piper_grpc_server_version = grpc_client.check_grpc_server().result()
        except:
            log.exception(
                f"Failed to connect to piper GRPC server. Synthesizer will not be available.",
                exc_info=True,
            )
            return False
        log.info(f"Piper GRPC server running on port {grpc_client.PIPER_GRPC_SERVER_PORT}")
        log.info("Connected to Piper GRPC server")
        log.info(f"Piper GRPC server version: {piper_grpc_server_version}")
        if not any(PiperTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()):
            log.error(
                "No installed voices were found for Piper. Synthesizer will not be available."
            )
            return False
        return True

    def __init__(self):
        super().__init__()
        self._current_task = None
        self._rateBoost = False
        self.voices = PiperTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()
        try:
            voice_key = config.conf["speech"]["piper_neural_voices"]["voice"]
            configured_voice = next(
                filter(lambda v: v.key.startswith(voice_key), self.voices)
            )
        except (KeyError, StopIteration):
            configured_voice = self.voices[0]
        init_speech_options = SpeechOptions(voice=configured_voice)
        self.tts = PiperTextToSpeechSystem(
            self.voices, speech_options=init_speech_options
        )
        self._silence_event = threading.Event()
        self._players = {}
        self._player = self._get_or_create_player(
            self.tts.speech_options.voice.sample_rate
        )
        self.availableLanguages = {v.language for v in self.voices}
        self._voice_map = {v.key: v for v in self.voices}
        (
            self.availableVoices,
            self.__voice_variants,
            self.__default_variants,
        ) = self._get_voices_and_variants()
        self.__voice = None

    def terminate(self):
        self.cancel()
        self.tts.shutdown()
        for player in self._players.values():
            player.close()
        self._players.clear()

    def speak(self, speechSequence):
        return self.speak_navigation(speechSequence)

    def speak_navigation(self, speechSequence):
        self.cancel()
        self._silence_event.clear()
        speech_seq = []
        default_lang = self.tts.language
        for item in self.combine_adjacent_strings(speechSequence):
            item_type = type(item)
            if item_type is str:
                speech_seq.append(
                    SpeechTask(
                        self.tts.create_speech_task(item),
                        self._player,
                        self._silence_event.is_set,
                    )
                )
            elif item_type is IndexCommand:
                speech_seq.append(IndexReachedTask(self._on_index_reached, item.index))
            elif item_type is BreakCommand:
                speech_seq.append(
                    BreakTask(
                        self.tts.create_break_task(item.time),
                        self._player,
                        self._silence_event.is_set,
                    )
                )
            elif item_type is LangChangeCommand:
                if item.isDefault:
                    self.tts.language = default_lang
                else:
                    self.tts.language = item.lang
            elif item_type is RateCommand:
                self.tts.rate = item.newValue
            elif item_type is VolumeCommand:
                self.tts.volume = item.newValue
            elif item_type is PitchCommand:
                self.tts.pitch = item.newValue
        speech_seq.append(
            DoneSpeakingTask(
                self._player, self._on_index_reached, self._silence_event.is_set
            )
        )
        self._current_task = process_speech(
            speech_seq, self._silence_event.is_set
        ).result()

    def cancel(self):
        if self._current_task is not None:
            aio.asyncio_cancel_task(self._current_task)
        self._silence_event.set()
        self._player.stop()

    def pause(self, switch):
        self._player.pause(switch)

    def _on_index_reached(self, index):
        if index is not None:
            synthIndexReached.notify(synth=self, index=index)
        else:
            synthDoneSpeaking.notify(synth=self)

    def combine_adjacent_strings(self, lst):
        """Taken from IBMTTS add-on."""
        result = []
        current_string = ""
        for item in lst:
            if isinstance(item, str):
                current_string += item
            else:
                if current_string:
                    result.append(current_string)
                    current_string = ""
                result.append(item)
        if current_string:
            result.append(current_string)
        return result

    def _get_or_create_player(self, sample_rate):
        if sample_rate not in self._players:
            self._players[sample_rate] = nvwave.WavePlayer(
                channels=1,
                samplesPerSec=sample_rate,
                bitsPerSample=16,
                outputDevice=config.conf["speech"]["outputDevice"],
                buffered=True,
            )
        return self._players[sample_rate]

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
        elif self.voice in PiperConfig:
            factor = PiperConfig[self.voice].get("noise_scale", 50)
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
        elif self.voice in PiperConfig:
            factor = PiperConfig[self.voice].get("length_scale", 50)
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
        elif self.voice in PiperConfig:
            factor = PiperConfig[self.voice].get("noise_w", 50)
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
        with suppress(AttributeError):
            del self._availableVariants
        with suppress(AttributeError):
            del self._availableSpeakers
        if value in PiperConfig:
            variant = PiperConfig[value].get("variant", self.variant)
            speaker = PiperConfig[value].get("speaker")
        else:
            variant = self.__default_variants[value]
            speaker = None
        self._set_variant(variant)

        # Reset params
        self.noise_scale = self.noise_scale
        self.length_scale = self.length_scale
        self.noise_w = self.noise_w

        if speaker is not None:
            self._set_speaker(speaker)

    def _get_language(self):
        return self.tts.language

    def _set_language(self, value):
        self.tts.language = value

    def _get_variant(self):
        return self._voice_map[self.tts.voice].properties["quality"]

    def _set_variant(self, value):
        voice_key = f"{self.__voice}-{value}"
        if voice_key in self._voice_map:
            self.tts.voice = voice_key
            PiperConfig.setdefault(self.voice, {})["variant"] = value
        else:
            variant = self.__default_variants[self.__voice]
            PiperConfig.setdefault(self.voice, {})["variant"] = variant
            self._set_variant(variant)
        voice = self.tts.speech_options.voice
        self._player = self._get_or_create_player(voice.sample_rate)

    def _getAvailableVariants(self):
        rv = OrderedDict()
        for (quality, vinfo) in self.__voice_variants[self.voice].items():
            rv[quality] = VoiceInfo(quality, quality.title(), vinfo.language)
        return rv

    def _get_variant_independent_voice_id(self, voice_key):
        return "-".join(voice_key.split("-")[:-1])

    def _get_voices_and_variants(self):
        all_voices = OrderedDict()
        all_variants = OrderedDict()
        default_variants = OrderedDict()
        for voice in self.voices:
            voice_id = self._get_variant_independent_voice_id(voice.key)
            quality = voice.properties["quality"]
            lang = languageHandler.normalizeLanguage(voice.language).replace("_", "-")
            display_name = f"{voice.name} ({lang})"
            all_voices[voice_id] = VoiceInfo(voice_id, display_name, voice.language)
            all_variants.setdefault(voice_id, {})[quality] = VoiceInfo(
                quality, quality.title(), voice.language
            )
            default_variants.setdefault(voice_id, quality)
        return all_voices, all_variants, default_variants

    def _get_speaker(self):
        return self.tts.speaker

    def _set_speaker(self, value):
        try:
            self.tts.speaker = value
            PiperConfig.setdefault(self.voice, {})["speaker"] = value
        except SpeakerNotFoundError:
            PiperConfig.setdefault(self.voice, {})["speaker"] = self.tts.speaker

    def _get_availableSpeakers(self):
        return {spk: VoiceInfo(spk, spk, None) for spk in self.tts.get_speakers()}
