# coding: utf-8

# Copyright (c) 2021 Blind Pandas Team
# This file is covered by the GNU General Public License.

import sys
import os
import contextlib
import socket


import wx
from gui.settingsDialogs import NVDASettingsDialog, SpeechSettingsPanel


PLUGIN_DIRECTORY = os.path.abspath(os.path.dirname(__file__))
LIB_DIRECTORY = os.path.join(PLUGIN_DIRECTORY, "lib")
BIN_DIRECTORY = os.path.join(PLUGIN_DIRECTORY, "bin")


@contextlib.contextmanager
def import_bundled_library(lib_directory=LIB_DIRECTORY):
    sys.path.insert(0, lib_directory)
    try:
        yield
    finally:
        sys.path.remove(lib_directory)


def is_free_port(port):
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        try:
            s.bind(("localhost", port))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return True
        except (OSError, socket.error) as e:
            return False


def find_free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("localhost", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def update_displaied_params_on_voice_change(synth):
    try:
        setting_dialog = next(
            win
            for win in wx.GetTopLevelWindows()
            if isinstance(win, NVDASettingsDialog)
        )
    except StopIteration:
        # No gui displaied 
        return
    current_panel = setting_dialog.currentCategory
    if not isinstance(current_panel, SpeechSettingsPanel):
        # No gui displaied 
        return
    voice_panel = current_panel.voicePanel
    # Patch values
    speakers = list(synth.availableSpeakers.values())
    variants = list(synth.availableVariants.values())
    voice_panel._speakers = speakers
    voice_panel._variants = variants
    voice_panel.speakerList.SetItems([s.displayName for s in speakers])
    voice_panel.variantList.SetItems([v.displayName for v in variants])
    # Update based on config
    # voice_panel.updateDriverSettings("speaker")
    # voice_panel.updateDriverSettings("variant")
