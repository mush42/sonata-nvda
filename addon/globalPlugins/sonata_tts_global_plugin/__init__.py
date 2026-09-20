# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

import os
import sys

import wx

import api
import core
import gui
import globalPluginHandler
import synthDriverHandler
from logHandler import log

import addonHandler

addonHandler.initTranslation()


_DIR = os.path.abspath(os.path.dirname(__file__))
_ADDON_ROOT = os.path.abspath(os.path.join(_DIR, os.pardir, os.pardir))
_TTS_MODULE_DIR = os.path.join(_ADDON_ROOT, "synthDrivers")
sys.path.insert(0, _TTS_MODULE_DIR)
from sonata_neural_voices import helpers
from sonata_neural_voices import aio
from sonata_neural_voices.tts_system import (
    SonataTextToSpeechSystem,
    SONATA_VOICES_DIR,
)
from sonata_neural_voices.app_profiles import app_profile_manager
sys.path.remove(_TTS_MODULE_DIR)
del _DIR, _ADDON_ROOT, _TTS_MODULE_DIR

from .voice_manager import SonataVoiceManagerDialog
from .profile_dialog import SonataAppProfileDialog


def _get_sonata_synth():
    """Return the active Sonata SynthDriver instance, or None."""
    synth = synthDriverHandler.getSynth()
    if synth is not None and synth.name == "sonata_neural_voices":
        return synth
    return None


def _get_foreground_exe():
    """Return the executable name (lower-case, no extension) of the foreground app."""
    try:
        obj = api.getForegroundObject()
        if obj is None:
            return None
        # appModule.appName gives the exe stem without extension
        app = obj.appModule
        if app:
            return app.appName.lower()
    except Exception:
        pass
    return None


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__voice_manager_shown = False
        self._last_exe = None
        self._voice_checker = lambda: wx.CallLater(3000, self._perform_voice_check)
        core.postNvdaStartup.register(self._voice_checker)

        # Sonata Voice Manager menu item
        self.itemHandle = gui.mainFrame.sysTrayIcon.menu.Append(
            wx.ID_ANY,
            # Translators: label of a menu item
            _("Sonata &voice manager..."),
            # Translators: Sonata's voice manager menu item help
            _("Open the voice manager to preview, install or download sonata voices"),
        )
        gui.mainFrame.sysTrayIcon.menu.Bind(wx.EVT_MENU, self.on_manager, self.itemHandle)

        # App Profile Settings menu item
        self.profileItemHandle = gui.mainFrame.sysTrayIcon.menu.Append(
            wx.ID_ANY,
            # Translators: label of a menu item
            _("Sonata app &profiles..."),
            # Translators: help text for app profiles menu item
            _("Configure per-application Sonata voice profiles"),
        )
        gui.mainFrame.sysTrayIcon.menu.Bind(
            wx.EVT_MENU, self.on_app_profiles, self.profileItemHandle
        )

    def on_manager(self, event):
        manager_dialog = SonataVoiceManagerDialog()
        gui.runScriptModalDialog(manager_dialog)
        self.__voice_manager_shown = True

    def on_app_profiles(self, event):
        profile_dialog = SonataAppProfileDialog(gui.mainFrame)
        profile_dialog.ShowModal()
        profile_dialog.Destroy()

    # Feature 6: Auto-switch voice profile on application focus change
    def event_gainFocus(self, obj, nextHandler):
        try:
            app = obj.appModule
            if app:
                exe = app.appName.lower()
                if exe != self._last_exe:
                    self._last_exe = exe
                    synth = _get_sonata_synth()
                    if synth is not None:
                        app_profile_manager.apply_for_exe(exe, synth)
        except Exception:
            pass
        nextHandler()

    def _perform_voice_check(self):
        if self.__voice_manager_shown:
            return
        if not any(SonataTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()):
            retval = gui.messageBox(
                # Translators: message telling the user that no voice is installed
                _(
                    "No Sonata voice was found.\n"
                    "You can preview and download voices from the voice manager.\n"
                    "Do you want to open the voice manager now?"
                ),
                # Translators: title of a message telling the user that no Sonata voice was found
                _("Sonata Neural Voices"),
                wx.YES_NO | wx.ICON_WARNING,
            )
            if retval == wx.YES:
                self.on_manager(None)

    def terminate(self):
        try:
            gui.mainFrame.sysTrayIcon.menu.DestroyItem(self.itemHandle)
        except Exception:
            pass
        try:
            gui.mainFrame.sysTrayIcon.menu.DestroyItem(self.profileItemHandle)
        except Exception:
            pass
