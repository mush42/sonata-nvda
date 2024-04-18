# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

__all__ = [
    "IGNORED_PUNCS",
    "PIPER_VOICES_VERSION",
    "SONATA_VOICES_BASE_DIR",
    "SONATA_VOICES_DIR",
    "BATCH_SIZE",
    "FALLBACK_SPEAKER_NAME",
    "DEFAULT_RATE",
    "DEFAULT_VOLUME",
    "DEFAULT_PITCH",
]


import os
import globalVars


# An utterance is ignored if it only contains the following chars
# Eventually, this should be moved to sonata-rs
IGNORED_PUNCS = frozenset(",(){}[]`\"'")
PIPER_VOICES_VERSION = "v1.0"
SONATA_VOICES_BASE_DIR = os.path.join(globalVars.appArgs.configPath, "sonata")
SONATA_VOICES_DIR = os.path.join(
    SONATA_VOICES_BASE_DIR, "voices", "piper"
)
BATCH_SIZE = max(os.cpu_count() // 2, 2)
FALLBACK_SPEAKER_NAME = "default"
DEFAULT_RATE = 50
DEFAULT_VOLUME = 100
DEFAULT_PITCH = 50
