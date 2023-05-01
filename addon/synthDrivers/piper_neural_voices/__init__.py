# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

from functools import partial
import os
import sys
import threading
import queue
import webbrowser
from collections import OrderedDict

import config
import synthDriverHandler
import languageHandler
import nvwave
from logHandler import log
from synthDriverHandler import synthDoneSpeaking, SynthDriver, synthIndexReached, VoiceInfo
from speech.commands import (
    BreakCommand,
    CharacterModeCommand,
    IndexCommand,
    LangChangeCommand,
    RateCommand,
    VolumeCommand
)

from .tts_system import (
    PiperTextToSpeechSystem,
    AudioTask,
    PIPER_VOICE_SAMPLES_URL
)


_LIB_PATH = os.path.join(
    os.path.abspath(os.path.dirname(__file__)),
    "lib"
)
sys.path.insert(0, _LIB_PATH)
from pysbd import Segmenter
sys.path.remove(_LIB_PATH)


SENTENCE_SPLIT_THRESHOLD = 50


import addonHandler
addonHandler.initTranslation()


class ProcessPiperTask:
    __slots__ = ["task", "player", "on_index_reached", "is_canceled"]

    def __init__(self, task, player, on_index_reached, is_canceled):
        self.task = task
        self.player = player
        self.on_index_reached = on_index_reached
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



class SynthDriver(synthDriverHandler.SynthDriver):

    supportedSettings = (
        SynthDriver.VoiceSetting(),
        SynthDriver.VariantSetting(),
        SynthDriver.RateSetting(),
        SynthDriver.VolumeSetting(),
    )
    supportedCommands = {
        IndexCommand,
        BreakCommand,
        # RateCommand,
        # VolumeCommand
    }
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    description='Piper Neural Voices'
    name='piper_neural_voices'

    @classmethod
    def check(cls):
        return any(PiperTextToSpeechSystem.load_piper_voices_from_nvda_config_dir())

    def __init__(self):
        self.voices = PiperTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()
        self.tts = PiperTextToSpeechSystem(self.voices)
        self._bgQueue = queue.Queue()
        self._bgThread = BgThread(self._bgQueue)
        self._silence_event = threading.Event()
        self._players = {}
        self._player = self._get_or_create_player(self.tts.speech_options.voice.config.sample_rate)
        self.availableLanguages = {v.language for v in self.voices}
        self.availableVoices, self.__voice_variants, self.__default_variants = self._get_voices_and_variants()
        self._voice_map = {v.key: v for v in self.voices}
        self.__voice = None
        self._segmenter = Segmenter(clean=False)

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
            DoneSpeaking(self._player, self._on_index_reached, self._silence_event.is_set)
        )
        for item in speechSequence:
            if isinstance(item, str):
                if len(item) < SENTENCE_SPLIT_THRESHOLD:
                    self._bgQueue.put(
                        ProcessPiperTask(
                            self.tts.create_speech_task(item),
                            self._player,
                            self._on_index_reached,
                            self._silence_event.is_set
                        )
                    )
                else:
                    for sentence in self._segmenter.segment(item):
                        self._bgQueue.put(
                            ProcessPiperTask(
                                self.tts.create_speech_task(sentence),
                                self._player,
                                self._on_index_reached,
                                self._silence_event.is_set
                            )
                        )
            elif isinstance(item, IndexCommand):
                self._bgQueue.put(partial(self._on_index_reached, item.index))
            elif isinstance(item, BreakCommand):
                self._bgQueue.put(
                    ProcessPiperTask(
                        self.tts.create_break_task(item.time),
                        self._player,
                        self._on_index_reached,
                        self._silence_event.is_set
                    )
                )
        self._bgQueue.put(
            DoneSpeaking(
                self._player,
                self._on_index_reached,
                self._silence_event.is_set
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
            DoneSpeaking(self._player, self._on_index_reached, self._silence_event.is_set)
        )
        self._bgQueue.put(self._silence_event.clear)
        self._bgQueue.join()

    def pause(self, switch):
        self.player.pause(switch)

    def _get_rate(self):
        return self.tts.rate

    def _set_rate(self, value):
        self.tts.rate = value

    def _get_volume(self):
        return self.tts.volume

    def _set_volume(self, value):
        self.tts.volume = value

    def _get_voice(self):
        return self._get_variant_independent_voice_id(self.tts.voice)

    def _set_voice(self, value):
        self.__voice = value
        if hasattr(self, "_availableVariants"):
            del self._availableVariants
        variant = self.variant
        if f"{value}-{variant}" not in self._voice_map:
            variant = self.__default_variants[value]
        self._set_variant(variant)

    def _get_language(self):
        return self.tts.language

    def _set_language(self, value):
        self.tts.language = value

    def _get_variant(self):
        return self.tts.voice.split("-")[-1]

    def _set_variant(self, value):
        voice_key = f"{self.__voice}-{value}"
        self.tts.voice = voice_key
        voice = self.tts.speech_options.voice
        self._player = self._get_or_create_player(voice.config.sample_rate)
        lang = voice.language.split("-")[0]
        if self._segmenter.language != lang:
            try:
                self._segmenter = Segmenter(language=lang, clean=False)
            except ValueError:
                log.exception(f"Sentence segmenter does not support the voice language `{lang}`", exc_info=True)
                self._segmenter = Segmenter(clean=False)

    def _getAvailableVariants(self):
        rv = OrderedDict()
        for (quality, vinfo) in self.__voice_variants[self.voice].items():
            rv[quality] = VoiceInfo(
                quality,
                quality.title(),
                vinfo.language
            )
        return rv

    def _on_index_reached(self, index):
        if index is not None:
            synthIndexReached.notify(synth=self, index=index)
        else:
            synthDoneSpeaking.notify(synth=self)

    def _get_variant_independent_voice_id(self, voice_key):
        return "-".join(voice_key.split("-")[:-1])

    def _get_voices_and_variants(self):
        all_voices = OrderedDict()
        all_variants = OrderedDict()
        default_variants = {}
        for voice in self.voices:
            voice_id = self._get_variant_independent_voice_id(voice.key)
            quality = voice.properties["quality"]
            lang = languageHandler.normalizeLanguage(voice.language).replace("_", "-")
            display_name =  f"{voice.name} ({lang})"
            all_voices[voice_id] = VoiceInfo(voice_id, display_name, voice.language)
            all_variants.setdefault(voice_id, {})[quality] = VoiceInfo(quality, quality.title(), voice.language)
            default_variants.setdefault(voice_id, quality)
        return all_voices, all_variants, default_variants

    def _get_or_create_player(self, sample_rate):
        if sample_rate not in self._players:
            self._players[sample_rate] = nvwave.WavePlayer(
                channels=1,
                samplesPerSec=sample_rate,
                bitsPerSample=16,
                outputDevice=config.conf["speech"]["outputDevice"],
                buffered=True
            )
        return self._players[sample_rate]