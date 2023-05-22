# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

import functools
import operator
import os
import shutil
import sys
import webbrowser

import wx
from wx.adv import CommandLinkButton

import core
import gui
import globalPluginHandler
import synthDriverHandler
from logHandler import log

from .components import ImmutableObjectListView, ColumnDefn

import addonHandler

addonHandler.initTranslation()


_DIR = os.path.abspath(os.path.dirname(__file__))
_ADDON_ROOT = os.path.abspath(os.path.join(_DIR, os.pardir, os.pardir))
_TTS_MODULE_DIR = os.path.join(_ADDON_ROOT, "synthDrivers", "piper_neural_voices")
sys.path.insert(0, _TTS_MODULE_DIR)
from tts_system import (
    PiperTextToSpeechSystem,
    PIPER_VOICE_SAMPLES_URL,
    PIPER_VOICES_DIR,
)

sys.path.remove(_TTS_MODULE_DIR)


class SettingsPanel(gui.SettingsPanel):
    # Translators: Title for the settings panel in NVDA's multi-category settings
    title = _("Piper Voice Manager")

    def makeSettings(self, settingsSizer):
        voices_sizer = wx.BoxSizer(wx.VERTICAL)
        # Translators: lable for a list of installed voices
        voices_label = wx.StaticText(self, -1, _("Available voices"))
        self.voices_list = ImmutableObjectListView(
            self,
            -1,
            columns=[
                # Translators: list view column title
                ColumnDefn(_("Name"), "left", 30, operator.attrgetter("name")),
                ColumnDefn(
                    # Translators: list view column title
                    _("Quality"), "right", 30, lambda v: v.properties["quality"].title()
                ),
                # Translators: list view column title
                ColumnDefn(_("Language"), "center", 20, operator.attrgetter("language")),
            ],
        )
        voices_sizer.Add(voices_label, border=5, flag=wx.EXPAND|wx.ALL)
        voices_sizer.Add(self.voices_list, border=10, flag=wx.BOTTOM| wx.EXPAND|wx.ALL )
        settingsSizer.Add(voices_sizer, border=10, flag=wx.BOTTOM| wx.EXPAND|wx.ALL )
        buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: lable for a button for showing voice model card
        self.model_card_button = wx.Button(self, -1, _("&Voice model card..."))
        # Translators: lable for a button for removing a voice
        self.remove_voice_button = wx.Button(self, -1, _("&Remove voice..."))
        buttons_sizer.Add(self.model_card_button, border=10, flag=wx.BOTTOM)
        buttons_sizer.Add(self.remove_voice_button, border=10, flag=wx.BOTTOM)
        settingsSizer.Add(buttons_sizer, border=10, flag=wx.BOTTOM| wx.EXPAND|wx.ALL )
        big_buttons_sizer = wx.BoxSizer(wx.VERTICAL)
        add_voice_button = CommandLinkButton(
            self,
            -1,
            # Translators: the main label of a button
            _("Install from local file"),
            # Translators: the note of a button
            _(
                "Install a voice from a local archive.\n"
                "The archive contains the voice model and configuration.\n"
                "The archive should have a (.tar.gz) file extension."
            )
        )
        open_website_button = CommandLinkButton(
            self,
            -1,
            # Translators: the main label of a button
            _("Get Voices"),
            # Translators: the note of a button
            _(
                "Open Piper's samples web page.\n"
                "There you can preview and download voices.\n"
                "To download a voice, just click on the voice's name.\n"
            )
        )
        big_buttons_sizer.Add(add_voice_button, border=10, flag=wx.BOTTOM)
        big_buttons_sizer.Add(open_website_button, border=10, flag=wx.BOTTOM)
        settingsSizer.Add(big_buttons_sizer, border=10, flag=wx.BOTTOM| wx.EXPAND|wx.ALL )
        self.Bind(wx.EVT_BUTTON, self.on_model_card, self.model_card_button)
        self.Bind(wx.EVT_BUTTON, self.on_remove_voice, self.remove_voice_button)
        self.Bind(
            wx.EVT_BUTTON,
            lambda e: webbrowser.open(PIPER_VOICE_SAMPLES_URL),
            open_website_button,
        )
        self.Bind(wx.EVT_BUTTON, self._on_install_voice_from_tar, add_voice_button)
        self.update_voices_list(set_focus=False)

    def onSave(self):
        pass

    def on_model_card(self, event):
        selected = self.voices_list.get_selected()
        if selected is None:
            self.voices_list.set_focused_item(0)
            return
        model_card_file = os.path.join(selected.location, "MODEL_CARD")
        if os.path.exists(model_card_file):
            with open(model_card_file, "r", encoding="utf-8") as file:
                content = file.read()
            content = content.replace("#", "").replace("*", "")
            gui.messageBox(
                content,
                #! Intentionally untranslatable 
                "Info",
                style=wx.ICON_INFORMATION
            )
        else:
            gui.messageBox(
                "Model card information is unavailable for this voice",
                "Info",
                style=wx.ICON_WARNING
            )

    def on_remove_voice(self, event):
        selected = self.voices_list.get_selected()
        if selected is None:
            self.voices_list.set_focused_item(0)
            return
        voice_id = "-".join(selected.key.split("-")[:-1])
        synth = synthDriverHandler.getSynth()
        if (
            (synth.name == "piper_neural_voices")
            and (synth.voice == voice_id)
        ):
            gui.messageBox(
                # Translators: message in a message box
                _("You cannot remove the currently active voice. We're all good citizens, right?!"),
                # Translators: title of a message box
                _("Warning"),
                style=wx.ICON_WARNING
            )
            return
        retval = gui.messageBox(
            # Translators: message in a message box
            _(
                "Do you want to remove this voice?\n"
                "Voice: {name}"
            ).format(name=selected.key),
            # Translators: title of a message box
            _("Remove voice?"),
            style=wx.YES_NO|wx.ICON_WARNING
        )
        if retval == wx.YES:
            try:
                shutil.rmtree(selected.location)
            except:
                log.exception("Failed to remove voice directory", exc_info=True)
                gui.messageBox(
                    # Translators: message in a message box
                    _("Failed to remove voice.\nSee NVDA's log for more details."),
                    # Translators: title of a message box
                    _("Failed"),
                    style=wx.ICON_WARNING
                )
            else:
                gui.messageBox(
                    # Translators: message in a message box
                    _("Voice removed successfully."),
                    # Translators: title of a message box
                    _("Done"),
                    style=wx.ICON_INFORMATION
                )
                self.update_voices_list(set_focus=True, invalidate_synth_voices_cache=True)

    def _on_install_voice_from_tar(self, event):
        openFileDialog = wx.FileDialog(
            parent=gui.mainFrame,
            # Translators: title for a dialog for opening a file
            message=_("Choose voice archive file "),
            defaultDir=wx.GetUserHome(),
            wildcard="Tar archives *.tar.gz | *.tar.gz",
            style=wx.FD_OPEN,
        )
        gui.runScriptModalDialog(
            openFileDialog,
            functools.partial(self._get_process_tar_archive, openFileDialog),
        )

    def _get_process_tar_archive(self, dialog, res):
        if res != wx.ID_OK:
            return
        filepath = dialog.GetPath().strip()
        if not filepath:
            return
        try:
            voice_key = PiperTextToSpeechSystem.install_voice(
                filepath, PIPER_VOICES_DIR
            )
        except:
            log.error("Failed to install voice from archive", exc_info=True)
            gui.messageBox(
                # Translators: message telling the user that installing the voice has failed
                _(
                    "Failed to install voice from archive. See NVDA's log for more details."
                ),
                _("Voice installation failed"),
                style=wx.ICON_ERROR,
            )
        else:
            gui.messageBox(
                # Translators: message telling the user that installing the voice is successful
                _(
                    "Voice {voice} has been installed successfully."
                ).format(voice=voice_key),
                _("Voice installed successfully"),
                style=wx.ICON_INFORMATION,
            )
            self.update_voices_list(set_focus=True, invalidate_synth_voices_cache=True)

    def update_voices_list(self, set_focus=True, invalidate_synth_voices_cache=False):
        voices = list(PiperTextToSpeechSystem.load_piper_voices_from_nvda_config_dir())
        enable = bool(voices)
        self.model_card_button.Enable(enable)
        self.remove_voice_button.Enable(enable)
        self.voices_list.Enable(enable)
        self.voices_list.set_objects(voices, set_focus=set_focus)
        if "piper" in synthDriverHandler.getSynth().name.lower():
            self.remove_voice_button.Enable(len(voices) >= 2)
            if invalidate_synth_voices_cache:
                synth = synthDriverHandler.getSynth()
                synth.terminate()
                synth.__init__()



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
                wx.YES_NO | wx.ICON_WARNING,
            )
            if retval == wx.YES:
                webbrowser.open(PIPER_VOICE_SAMPLES_URL)

    def terminate(self):
        try:
            gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(SettingsPanel)
        except IndexError:
            pass
