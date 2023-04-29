# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

import functools
import os
import sys
import webbrowser

import wx

import core
import gui
import globalPluginHandler
from logHandler import log


import addonHandler
addonHandler.initTranslation()


_DIR = os.path.abspath(os.path.dirname(__file__))
_ADDON_ROOT = os.path.abspath(os.path.join(_DIR, os.pardir))
_TTS_MODULE_DIR = os.path.join(_ADDON_ROOT, "synthDrivers", "piper_neural_voices")
sys.path.insert(0, _TTS_MODULE_DIR)
from tts_system import PiperTextToSpeechSystem, PIPER_VOICE_SAMPLES_URL, PIPER_VOICES_DIR
sys.path.remove(_TTS_MODULE_DIR)


class SettingsPanel(gui.SettingsPanel):
    # Translators: Title for the settings panel in NVDA's multi-category settings
    title = _("Piper")

    def makeSettings(self, settingsSizer):
        voices_sizer = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: lable for a list of installed voices
        voices_label = wx.StaticText(self, -1, _("Available voices"))
        self.voices_choice = wx.Choice(
            self,
            -1,
            choices=[v.key for v in self.get_available_piper_voices()]
        )
        voices_sizer.AddMany([voices_label, self.voices_choice])
        settingsSizer.Add(voices_sizer, border=10, flag=wx.BOTTOM)
        # Translators: lable for a button for installing a voice from an archive file
        add_voice_button = wx.Button(self, -1, _("&Install from file..."))
        # Translators: lable for a button for opening piper voice download web page
        open_website_button = wx.Button(self, -1, _("Open download &web page"))
        settingsSizer.Add(add_voice_button, border=10, flag=wx.BOTTOM)
        settingsSizer.Add(open_website_button, border=10, flag=wx.BOTTOM)
        self.Bind(wx.EVT_BUTTON, lambda e: webbrowser.open(PIPER_VOICE_SAMPLES_URL), open_website_button)
        self.Bind(wx.EVT_BUTTON, self._on_install_voice_from_tar, add_voice_button)

    def onSave(self):
        pass

    def _on_install_voice_from_tar(self, event):
        openFileDialog = wx.FileDialog(
            parent=gui.mainFrame,
            # Translators: title for a dialog for opening a file
            message=_("Choose voice archive file "),
            defaultDir=wx.GetUserHome(),
            wildcard="Tar archives *.tar.gz | *.tar.gz",
            style=wx.FD_OPEN
        )
        gui.runScriptModalDialog(
            openFileDialog, functools.partial(self._get_process_tar_archive, openFileDialog)
        )

    def _get_process_tar_archive(self, dialog, res):
        if res != wx.ID_OK:
            return
        filepath = dialog.GetPath().strip()
        if not filepath:
            return
        try:
            voice_key = PiperTextToSpeechSystem.install_voice(filepath, PIPER_VOICES_DIR)
        except:
            log.error("Failed to install voice from archive", exc_info=True)
            gui.messageBox(
                # Translators: message telling the user that installing the voice has failed
                _("Failed to install voice from archive. See the log for more details."),
                _("Voice installation failed"),
                style=wx.ICON_ERROR
            )
        else:
            gui.messageBox(
                # Translators: message telling the user that installing the voice is successful
                _("Voice {voice} has been installed successfully. Restart NVDA to refresh the voices list.").format(voice=voice_key),
                _("Voice installed successfully"),
                style=wx.ICON_INFORMATION
            )

    def get_available_piper_voices(self):
        return PiperTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(SettingsPanel)
        self._voice_checker = lambda: wx.CallLater(3000, self._perform_voice_check)
        core.postNvdaStartup.register(self._voice_checker)

    def _perform_voice_check(self):
        if not any(PiperTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()):
            retval = gui.messageBox(
                # Translators: message telling the user that no voice is installed
                _(
                    "No Piper voice was found.\n"
                    "You can checkout and download voices from the following URL:\n{url}\n"
                    "After downloading a voice, you can install the voice from `Piper` category in NVDA settings dialog.\n\n"
                    "Do you want to open Piper voices download page now?"
                ).format(url=PIPER_VOICE_SAMPLES_URL),
                # Translators: title of a message telling the user that no Piper voice was found
                _("Piper Neural Voices"),
                wx.YES_NO|wx.ICON_WARNING
            )
            if retval == wx.YES:
                webbrowser.open(PIPER_VOICE_SAMPLES_URL)

    def terminate(self):
        try:
            gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(SettingsPanel)
        except IndexError:
            pass
