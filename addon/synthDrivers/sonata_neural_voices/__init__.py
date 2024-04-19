# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

from asyncio.exceptions import CancelledError
from collections import OrderedDict
from contextlib import suppress

import config
import languageHandler
import synthDriverHandler
from autoSettingsUtils.driverSetting import DriverSetting, NumericDriverSetting
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

import addonHandler

addonHandler.initTranslation()


aio.initialize()
_GRPC_IS_INIT = grpc_client.initialize()


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
    ]

    def __init__(self, task, player):
        self.task = task
        self.player = player

    async def __call__(self):
        if sayAll.SayAllHandler.isRunning():
            self.task.text = self.task.text.replace("\n", " ")
            self.task.speech_options.sentence_silence_ms = 50
        speech_stream = await self.task.generate_audio()
        feed_func = self.player.feed
        async for wave_samples in speech_stream:
            await run_in_executor(feed_func, wave_samples)
        self.player.sync()


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

def create_wave_player(sample_rate):
    return WavePlayer(
        channels=1,
        samplesPerSec=sample_rate,
        bitsPerSample=16,
        outputDevice=config.conf["speech"]["outputDevice"],
        buffered=True,
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

    @classmethod
    def check(cls):
        return True

    def __init__(self):
        super().__init__()
        try:
            _GRPC_IS_INIT.result()
        except:
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

    def speak(self, speechSequence):
        with self.tts.create_synthesis_context():
            self._fast_prepare_and_run_speech_task(speechSequence)

    def _prepare_and_run_speech_task(self, speechSequence):
        self.cancel()
        speech_seq = []
        text_list = []
        index_command_list = []
        default_lang = self.tts.language
        for item in speechSequence:
            item_type = type(item)
            if item_type is IndexCommand:
                index_command_list.append(item.index)
                continue
            elif item_type is str:
                text_list.append(item)
                continue
            if any(text_list):
                speech_seq.append(
                    SpeechTask(
                        self.tts.create_speech_provider("".join(text_list)),
                        self._player,
                    )
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
                    self.tts.language = item.lang
            elif item_type is RateCommand:
                self.tts.rate = item.newValue
            elif item_type is VolumeCommand:
                self.tts.volume = item.newValue
            elif item_type is PitchCommand:
                self.tts.pitch = item.newValue
        if any(text_list):
            speech_seq.append(
                SpeechTask(
                    self.tts.create_speech_provider("".join(text_list)),
                    self._player,
                )
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

    def _fast_prepare_and_run_speech_task(self, speechSequence):
        self.cancel()
        speech_seq = []
        text_list = []
        index_command_list = []
        default_lang = self.tts.language
        for item in speechSequence:
            item_type = type(item)
            if item_type is IndexCommand:
                index_command_list.append(item.index)
                continue
            elif item_type is str:
                text_list.append(item)
                continue
            if any(text_list):
                speech_seq.append(
                    SpeechTask(
                        self.tts.create_speech_provider("\n".join(text_list)),
                        self._player,
                    )
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
                    self.tts.language = item.lang
            elif item_type is RateCommand:
                self.tts.rate = item.newValue
            elif item_type is VolumeCommand:
                self.tts.volume = item.newValue
            elif item_type is PitchCommand:
                self.tts.pitch = item.newValue
        if any(text_list):
            speech_seq.append(
                SpeechTask(
                    self.tts.create_speech_provider("\n".join(text_list)),
                    self._player,
                )
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
            self._players[sample_rate] = create_wave_player(sample_rate)
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
        update_displaied_params_on_voice_change(self)

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
        self.tts.voice = voice_key
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
        return {spk: VoiceInfo(spk, spk, None) for spk in self.tts.get_speakers()}

