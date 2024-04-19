# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.


"""Preview and download sonata voices."""

import functools
import operator
import os
import shutil
import tempfile
import threading
import winsound

import wx
from wx.adv import CommandLinkButton
import gui
import synthDriverHandler
from logHandler import log

from . import SonataTextToSpeechSystem, SONATA_VOICES_DIR
from . import voice_download
from . import aio
from . import helpers
from .components import AsyncSnakDialog, ColumnDefn, ImmutableObjectListView, SimpleDialog, make_sized_static_box
from .sized_controls import SizedPanel


with helpers.import_bundled_library():
    import miniaudio
    from pathlib import Path


class InstalledSonataVoicesPanel(SizedPanel):
    def __init__(self, parent):
        super().__init__(parent, -1)
        self.__already_populated = threading.Event()
        # Add controls
        # Translators: label for a list of installed voices
        voices_label = wx.StaticText(self, -1, _("Installed voices"))
        self.voices_list = ImmutableObjectListView(
            self,
            -1,
            columns=[
                # Translators: list view column title
                ColumnDefn(_("Name"), "left", 30, self._get_installed_voice_name),
                ColumnDefn(
                    # Translators: list view column title
                    _("Quality"), "center", 30, lambda v: v.properties["quality"].title()
                ),
                # Translators: list view column title
                ColumnDefn(_("Language"), "right", 20, operator.attrgetter("language")),
            ],
        )
        self.buttons_panel = SizedPanel(self, -1)
        self.buttons_panel.SetSizerType("horizontal")
        # Translators: label for a button for showing voice model card
        self.model_card_button = wx.Button(self.buttons_panel, -1, _("&Voice model card..."))
        # Translators: label for a button for removing a voice
        self.remove_voice_button = wx.Button(self.buttons_panel, -1, _("&Remove voice..."))
        add_voice_button = CommandLinkButton(
            self,
            -1,
            # Translators: the main label of the install button
            _("Install from local file"),
            # Translators: the note for this button
            _(
                "Install a voice from a local archive.\n"
                "The archive contains the voice model and configuration.\n"
                "The archive should have a (.tar.gz) file extension."
            )
        )
        self.Bind(wx.EVT_BUTTON, self.on_model_card, self.model_card_button)
        self.Bind(wx.EVT_BUTTON, self.on_remove_voice, self.remove_voice_button)
        self.Bind(wx.EVT_BUTTON, self._on_install_voice_from_tar, add_voice_button)

    def update_voices_list(self, set_focus=False, invalidate_synth_voices_cache=False):
        voices = list(SonataTextToSpeechSystem.load_piper_voices_from_nvda_config_dir())
        enable = bool(voices)
        self.buttons_panel.Enable(enable)
        self.voices_list.set_objects(voices, set_focus=set_focus)
        if "sonata" in synthDriverHandler.getSynth().name.lower():
            self.remove_voice_button.Enable(len(voices) >= 2)
            if invalidate_synth_voices_cache:
                synth = synthDriverHandler.getSynth()
                synth.terminate()
                synth.__init__()

    def populate_list(self):
        if self.__already_populated.is_set():
            return
        self.update_voices_list()

    def invalidate_cache(self):
        self.__already_populated.clear()
        if "sonata" in synthDriverHandler.getSynth().name.lower():
            if invalidate_synth_voices_cache:
                synth = synthDriverHandler.getSynth()
                synth.terminate()
                synth.__init__()

    def _get_installed_voice_name(self, voice):
        return f"{voice.name} ({voice.variant})"

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
                # Translators: title of a message box showing voice model card
                _("Model card"),
                style=wx.ICON_INFORMATION
            )
        else:
            gui.messageBox(
                # Translators: content of a message box
                _("Model card information is unavailable for this voice"),
                # Translators: title of a message box
                _("Not found"),
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
            (synth.name == "sonata_neural_voices")
            and (synth.voice == voice_id)
        ):
            gui.messageBox(
                # Translators: message in a message box
                _("You cannot remove the currently active voice!"),
                # Translators: title of a message box
                _("Error"),
                style=wx.ICON_ERROR
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
            voice_key = voice_download.install_voice_from_tar_archive(
                filepath, SONATA_VOICES_DIR
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


class OnlineSonataVoicesPanel(SizedPanel):
    def __init__(self, parent):
        super().__init__(parent, -1)
        self.__already_populated = threading.Event()
        self.languages = []
        self.lang_to_voices = {}
        # Build controls
        # Translators: label of a choice
        wx.StaticText(self, -1, _("Language"))
        self.language_choice = wx.Choice(self, -1, choices=[])
        wx.StaticText(self, -1, _("Available voices"))
        voice_list_columns=[
            # Translators: list view column title
            ColumnDefn(_("Name"), "left", 30, operator.attrgetter("name")),
            # Translators: list view column title
            ColumnDefn(_("Quality"), "center", 30, operator.attrgetter("quality")),
        ]
        self.voices_list = ImmutableObjectListView(
            self,
            -1,
            columns=voice_list_columns
        )
        self.voices_list.SetSizerProps(expand=True)
        self.buttons_panel = SizedPanel(self, -1)
        self.buttons_panel.SetSizerType("vertical")
        # Translators: header of a group of controls for previewing the voice
        preview_box = make_sized_static_box(self.buttons_panel, _("Preview"))
        preview_box.SetSizerType("horizontal")
        wx.StaticText(preview_box, -1, _("Speaker"))
        self.speaker_choice = wx.Choice(preview_box, -1, choices=[])
        # Translators: label of a button
        preview_btn = wx.Button(preview_box, -1, _("&Preview"))
        dl_buttons_panel = SizedPanel(self.buttons_panel, -1)
        dl_buttons_panel.SetSizerType("horizontal")
        # Translators: label of a button to download the standard variant of the voice
        self.download_std_btn = wx.Button(dl_buttons_panel, -1, _("&Download standard variant"))
        # Translators: label of a button to download the fast variant of voice
        self.download_rt_btn = wx.Button(dl_buttons_panel, -1, _("Download &fast variant"))
        # Translators: label of a button to refresh the voices list
        refresh_list_btn = wx.Button(self, -1, _("&Refresh voices list"))
        self.Bind(wx.EVT_CHOICE, self.on_language_selection_change, self.language_choice)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_voice_selected, self.voices_list)
        self.Bind(wx.EVT_CHOICE, self.on_speaker_selection_changed, self.speaker_choice)
        self.Bind(wx.EVT_BUTTON, self.on_preview, preview_btn)
        self.Bind(wx.EVT_BUTTON, self.on_download, self.download_std_btn)
        self.Bind(wx.EVT_BUTTON, self.on_download_rt, self.download_rt_btn)
        self.Bind(wx.EVT_BUTTON, lambda e: self.populate_list(force_online=True), refresh_list_btn)
        self.speaker_choice.Enable(False)
        self.buttons_panel.Enable(False)

    def populate_list(self, force_online=False):
        if not force_online and  self.__already_populated.is_set():
            return
        AsyncSnakDialog(
            executor=voice_download.THREAD_POOL_EXECUTOR,
            func=functools.partial(voice_download.get_available_voices, force_online=force_online),
            done_callback=self._voice_list_retrieved_callback,
            parent=self,
            # Translators: message in a dialog
            message=_("Retrieving voices list. Please wait..."),
            dismiss_callback=lambda: self.Close()
        )

    def _voice_list_retrieved_callback(self, future):
        try:
            result = future.result()
        except:
            log.exception("Failed to retreive voices list", exc_info=True)
            wx.CallAfter(
                gui.messageBox,
                _("Could not retrieve voice list.\nPlease check your connection and try again."),
                _("Error"),
                style=wx.ICON_ERROR,
            )
            return
        wx.CallAfter(self.set_voices, result)

    def invalidate_cache(self):
        self.__already_populated.clear()

    def on_language_selection_change(self, event):
        self.voices_list.Enable(True)
        selected_lang = self.languages[event.GetSelection()]
        voices = self.lang_to_voices[selected_lang]
        self.voices_list.set_objects(voices, set_focus=False)
        self.voices_list.EnsureVisible(0)
        self.voices_list.Select(0)
        self.voices_list.SetItemState(0, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED)
        self.buttons_panel.Enable(True)
        self.speaker_choice.SetItems([])
        self.speaker_choice.Enable(False)

    def on_voice_selected(self, event):
        self.speaker_choice.SetItems([])
        selected_voice = self.voices_list.get_selected()
        if selected_voice is None:
            return
        self.download_std_btn.Enable(not selected_voice.standard_variant_installed)
        self.download_rt_btn.Enable(
            selected_voice.has_rt_variant and not selected_voice.fast_variant_installed
        )
        if selected_voice.num_speakers > 1:
            self.speaker_choice.Enable(True)
            speakers = list(selected_voice.speaker_id_map.keys())
            self.speaker_choice.SetItems(speakers)
            self.speaker_choice.SetSelection(0)
        else:
            self.speaker_choice.Enable(False)

    def on_speaker_selection_changed(self, event):
        pass

    def on_preview(self, event):
        selected_voice = self.voices_list.get_selected()
        if selected_voice is None:
            return
        speaker_idx = 0
        if selected_voice.num_speakers > 1:
            speaker_idx = self.speaker_choice.GetSelection()
        mp3url = selected_voice.get_preview_url(speaker_idx=speaker_idx)
        AsyncSnakDialog(
            # Translators: message in a dialog
            message=_("Playing preview..."),
            executor=aio.THREADED_EXECUTOR,
            func=functools.partial(play_remote_mp3, mp3url),
            done_callback=lambda future: True,
            parent=self.GetTopLevelParent()
        )

    def on_download(self, event):

        def success_callback():
            self.Parent._invalidate_pages_voice_cache()
            wx.CallAfter(self.populate_list)
            wx.CallAfter(self.voices_list.SetFocus)

        selected_voice = self.voices_list.get_selected()
        if selected_voice is not None:
            downloader = voice_download.PiperVoiceDownloader(
                selected_voice,
                success_callback=success_callback
            )
            downloader.download()

    def on_download_rt(self, event):

        def success_callback():
            self.Parent._invalidate_pages_voice_cache()
            wx.CallAfter(self.populate_list)
            wx.CallAfter(self.voices_list.SetFocus)

        selected_voice = self.voices_list.get_selected()
        if selected_voice is None:
            return
        downloader = voice_download.PiperRTVoiceDownloader(
            selected_voice,
            success_callback=success_callback
        )
        downloader.download()


    def set_voices(self, voices):
        self.lang_to_voices = {}
        for voice in voices:
            self.lang_to_voices.setdefault(voice.language, []).append(voice)
        for vlist in self.lang_to_voices.values():
            vlist.sort(key=operator.attrgetter("key"))
        self.languages = list(sorted(
            self.lang_to_voices.keys(),
            key=operator.attrgetter("name_english")
        ))
        self.language_choice.SetItems([lang.description for lang in self.languages])
        self.__already_populated.set()


class SonataVoiceManagerDialog(SimpleDialog):

    def __init__(self):
        super().__init__(
            gui.mainFrame,
            # Translators: title of voice manager dialog
            title=_("Sonata voice manager"),
        )
        self.SetSize((500, -1))
        self.CenterOnScreen()

    def addControls(self, parent):
        self.notebookCtrl = wx.Notebook(parent, -1)
        self.notebookCtrl.SetSizerProps(expand=True)
        panel_info = [
            (
                # Translators: label of a tab in a tab control
                _("Installed"),
                InstalledSonataVoicesPanel(self.notebookCtrl),
            ),
            (
                # Translators: label of a tab in a tab control
                _("Download"),
                OnlineSonataVoicesPanel(self.notebookCtrl),
            ),
        ]
        for label, panel in panel_info:
            panel.SetSizerType("vertical")
            self.notebookCtrl.AddPage(panel, label)
        self.Bind(
            wx.EVT_NOTEBOOK_PAGE_CHANGED, self.onNotebookPageChanged, self.notebookCtrl
        )
        self.notebookCtrl._invalidate_pages_voice_cache = self._invalidate_pages_voice_cache
        self.notebookCtrl.GetCurrentPage().populate_list()

    def getButtons(self, parent):
        btnsizer = wx.StdDialogButtonSizer()
        # Translators: the label of the close button in a dialog
        cancelBtn = wx.Button(self, wx.ID_CANCEL, _("&Close"))
        btnsizer.AddButton(cancelBtn)
        btnsizer.Realize()
        return btnsizer

    def onNotebookPageChanged(self, event):
        selected_page = self.notebookCtrl.GetPage(event.GetSelection())
        selected_page.populate_list()

    def _invalidate_pages_voice_cache(self):
        for i in range(self.notebookCtrl.GetPageCount()):
            panel = self.notebookCtrl.GetPage(i)
            panel.invalidate_cache()


def play_remote_mp3(mp3_url):
    resp = voice_download.request.get(mp3_url)
    resp.raise_for_status()
    decoded_file = miniaudio.decode(resp.body, nchannels=1, sample_rate=22050)
    with tempfile.TemporaryDirectory() as tempdir:
        wav_file = os.path.join(tempdir, "speaker_0.wav")
        miniaudio.wav_write_file(wav_file, decoded_file)
        winsound.PlaySound(
            wav_file,
            winsound.SND_FILENAME | winsound.SND_PURGE
        )

