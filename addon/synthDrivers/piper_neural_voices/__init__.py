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

import config
import languageHandler
import nvwave
import synthDriverHandler
from autoSettingsUtils.driverSetting import DriverSetting
from logHandler import log
from speech.commands import (BreakCommand, CharacterModeCommand, IndexCommand,
                             LangChangeCommand, RateCommand, VolumeCommand, PitchCommand)
from synthDriverHandler import (SynthDriver, VoiceInfo, synthDoneSpeaking,
                                synthIndexReached)

from ._config import PiperConfig
from .tts_system import (PIPER_VOICE_SAMPLES_URL, AudioTask,
                         PiperTextToSpeechSystem, SilenceTask, SpeakerNotFoundError)


import addonHandler

addonHandler.initTranslation()



class ProcessSpeechTask:
    __slots__ = ["task", "player", "is_canceled",]

    def __init__(self, task, player, is_canceled):
        self.task = task
        self.player = player
        self.is_canceled = is_canceled

    def __call__(self):
        if self.is_canceled():
            return
        speech_iter = self.task.generate_audio()
        while True:
            try:
                if self.is_canceled():
                    break
                self.player.idle()
                wave_samples = next(speech_iter)
                self.player.feed(wave_samples.get_wave_bytes())
            except StopIteration:
                break


class ProcessBreakTask:
    __slots__ = ["task", "player", "is_canceled",]

    def __init__(self, task, player, is_canceled):
        self.task = task
        self.player = player
        self.is_canceled = is_canceled

    def __call__(self):
        if not self.is_canceled():
            self.player.feed(self.task.generate_audio())


class DoneSpeaking:
    __slots__ = ["player", "on_index_reached", "is_canceled"]

    def __init__(self, player, onIndexReached, is_canceled):
        self.player = player
        self.on_index_reached = onIndexReached
        self.is_canceled = is_canceled

    def __call__(self):
        if self.is_canceled():
            self.player.stop()
        self.player.idle()
        self.on_index_reached(None)


class BgThread(threading.Thread):
    def __init__(self, bgQueue):
        super().__init__()
        self._bgQueue = bgQueue
        self.setDaemon(True)
        self.start()

    def run(self):
        while True:
            task = self._bgQueue.get()
            if task is None:
                break
            try:
                task()
            except Exception:
                log.error("Error running task from queue", exc_info=True)
            self._bgQueue.task_done()



def SpeakerSetting():
    """Factory function for creating speaker setting."""
    return DriverSetting(
        "speaker",
        # Translators: Label for a setting in voice settings dialog.
        _("&Speaker"),
        availableInSettingsRing=True,
        # Translators: Label for a setting in synth settings ring.
        displayName=_("Speaker")
    )


class SynthDriver(synthDriverHandler.SynthDriver):

    supportedSettings = (
        SynthDriver.VoiceSetting(),
        SynthDriver.VariantSetting(),
        SpeakerSetting(),
        SynthDriver.RateSetting(),
        SynthDriver.RateBoostSetting(),
        SynthDriver.VolumeSetting(),
        SynthDriver.PitchSetting(),
    )
    supportedCommands = {
        IndexCommand,
        LangChangeCommand,
        BreakCommand,
        RateCommand,
        VolumeCommand,
        PitchCommand
    }
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    description = "Piper Neural Voices"
    name = "piper_neural_voices"
    cachePropertiesByDefault = False

    @classmethod
    def check(cls):
        return any(PiperTextToSpeechSystem.load_piper_voices_from_nvda_config_dir())

    def __init__(self):
        super().__init__()
        self._rateBoost = False
        self.voices = PiperTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()
        self.tts = PiperTextToSpeechSystem(self.voices)
        self._bgQueue = queue.Queue()
        self._bgThread = BgThread(self._bgQueue)
        self._silence_event = threading.Event()
        self._players = {}
        self._player = self._get_or_create_player(
            self.tts.speech_options.voice.config.sample_rate
        )
        self.availableLanguages = {v.language for v in self.voices}
        self._voice_map = {v.key: v for v in self.voices}
        self.availableVoices, self.__voice_variants, self.__default_variants = self._get_voices_and_variants()
        self.__voice = None

    def terminate(self):
        self.cancel()
        self.tts.shutdown()
        for player in self._players.values():
            self._bgQueue.put(player.close)
        self._bgQueue.put(self._players.clear)
        self._bgQueue.put(None)
        self._bgThread.join()

    def speak(self, speechSequence):
        self._bgQueue.put(
            DoneSpeaking(
                self._player, self._on_index_reached, self._silence_event.is_set
            )
        )
        default_lang = self.tts.language
        for item in self.combine_adjacent_strings(speechSequence):
            item_type = type(item)
            if item_type is str:
                self._bgQueue.put(
                    ProcessSpeechTask(
                        self.tts.create_speech_task(item),
                        self._player,
                        self._silence_event.is_set,
                    )
                )
            elif item_type is IndexCommand:
                self._bgQueue.put(partial(self._on_index_reached, item.index))
            elif item_type is BreakCommand:
                self._bgQueue.put(ProcessBreakTask(
                    self.tts.create_break_task(item.time),
                    self._player,
                    self._silence_event.is_set,
                ))
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
        self._bgQueue.put(
            DoneSpeaking(
                self._player, self._on_index_reached, self._silence_event.is_set
            )
        )

    def cancel(self):
        self._silence_event.set()
        self._player.stop()
        try:
            while True:
                task = self._bgQueue.get_nowait()
                self._bgQueue.task_done()
        except queue.Empty:
            pass
        self._bgQueue.put(
            DoneSpeaking(
                self._player, self._on_index_reached, self._silence_event.is_set
            )
        )
        self._bgQueue.put(self._silence_event.clear)
        self._bgQueue.join()

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
        self._player = self._get_or_create_player(voice.config.sample_rate)

    def _getAvailableVariants(self):
        rv = OrderedDict()
        for (quality, vinfo) in self.__voice_variants[self.voice].items():
            rv[quality] = VoiceInfo(
                quality,
                quality.title(),
                vinfo.language
            )
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
            display_name =  f"{voice.name} ({lang})"
            all_voices[voice_id] = VoiceInfo(voice_id, display_name, voice.language)
            all_variants.setdefault(voice_id, {})[quality] = VoiceInfo(quality, quality.title(), voice.language)
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
        return {
            spk: VoiceInfo(spk, spk, None)
            for spk in self.tts.get_speakers()
        }
