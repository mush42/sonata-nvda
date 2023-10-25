# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

__all__ = [
    "IGNORED_PUNCS",
    "PIPER_VOICES_VERSION",
    "PIPER_VOICE_SAMPLES_URL",
    "PIPER_VOICES_BASE_DIR",
    "PIPER_VOICES_DIR",
    "BATCH_SIZE",
    "FALLBACK_SPEAKER_NAME",
    "DEFAULT_RATE",
    "DEFAULT_VOLUME",
    "DEFAULT_PITCH",
]


import os
import globalVars


IGNORED_PUNCS = frozenset(",(){}[]`\"'")
PIPER_VOICES_VERSION = "v1.0"
PIPER_VOICE_SAMPLES_URL = "https://rhasspy.github.io/piper-samples/"
PIPER_VOICES_BASE_DIR = os.path.join(globalVars.appArgs.configPath, "piper")
PIPER_VOICES_DIR = os.path.join(PIPER_VOICES_BASE_DIR, "voices", PIPER_VOICES_VERSION)
BATCH_SIZE = max(os.cpu_count() // 2, 2)
FALLBACK_SPEAKER_NAME = "default"
DEFAULT_RATE = 50
DEFAULT_VOLUME = 100
DEFAULT_PITCH = 50
