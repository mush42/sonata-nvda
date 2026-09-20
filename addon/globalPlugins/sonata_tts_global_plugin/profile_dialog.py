# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

"""
Dialog for managing per-application Sonata voice profiles.
Allows users to add, edit, and delete per-app voice settings.
"""

import os
import sys

import wx
import gui
import synthDriverHandler
from logHandler import log

import addonHandler

addonHandler.initTranslation()

_DIR = os.path.abspath(os.path.dirname(__file__))
_ADDON_ROOT = os.path.abspath(os.path.join(_DIR, os.pardir, os.pardir))
_TTS_MODULE_DIR = os.path.join(_ADDON_ROOT, "synthDrivers")
sys.path.insert(0, _TTS_MODULE_DIR)
from sonata_neural_voices.app_profiles import app_profile_manager
from sonata_neural_voices.tts_system import SonataTextToSpeechSystem, SONATA_VOICES_DIR
sys.path.remove(_TTS_MODULE_DIR)


def _get_installed_voice_ids():
    """Return a list of available voice IDs from installed voices."""
    voices = SonataTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()
    seen = set()
    result = []
    for v in voices:
        std_key = v.key.replace("+RT", "")
        if std_key not in seen:
            seen.add(std_key)
            result.append(std_key)
    return sorted(result)


class SonataEditProfileDialog(wx.Dialog):
    """Dialog for creating or editing a single app profile."""

    def __init__(self, parent, exe_name="", profile=None):
        super().__init__(
            parent,
            # Translators: title of the edit app profile dialog
            title=_("Edit App Profile"),
            style=wx.DEFAULT_DIALOG_STYLE,
        )
        self._exe_name = exe_name
        self._profile = profile or {}
        self._voice_ids = _get_installed_voice_ids()

        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
        grid.AddGrowableCol(1, 1)

        # Application name
        grid.Add(
            # Translators: label for app name field
            wx.StaticText(self, label=_("Application name (e.g. firefox):")),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        self.exe_ctrl = wx.TextCtrl(self, value=exe_name)
        grid.Add(self.exe_ctrl, flag=wx.EXPAND)

        # Voice
        grid.Add(
            # Translators: label for voice selection
            wx.StaticText(self, label=_("Voice:")),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        voice_choices = [""] + self._voice_ids
        self.voice_choice = wx.Choice(self, choices=voice_choices)
        current_voice = self._profile.get("voice", "")
        if current_voice in voice_choices:
            self.voice_choice.SetSelection(voice_choices.index(current_voice))
        else:
            self.voice_choice.SetSelection(0)
        grid.Add(self.voice_choice, flag=wx.EXPAND)

        # Rate
        grid.Add(
            # Translators: label for rate field
            wx.StaticText(self, label=_("Rate (0-100, blank=default):")),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        rate_val = str(self._profile.get("rate", "")) if self._profile.get("rate") is not None else ""
        self.rate_ctrl = wx.TextCtrl(self, value=rate_val)
        grid.Add(self.rate_ctrl, flag=wx.EXPAND)

        # Volume
        grid.Add(
            # Translators: label for volume field
            wx.StaticText(self, label=_("Volume (0-100, blank=default):")),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        vol_val = str(self._profile.get("volume", "")) if self._profile.get("volume") is not None else ""
        self.volume_ctrl = wx.TextCtrl(self, value=vol_val)
        grid.Add(self.volume_ctrl, flag=wx.EXPAND)

        # Pitch
        grid.Add(
            # Translators: label for pitch field
            wx.StaticText(self, label=_("Pitch (0-100, blank=default):")),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        pitch_val = str(self._profile.get("pitch", "")) if self._profile.get("pitch") is not None else ""
        self.pitch_ctrl = wx.TextCtrl(self, value=pitch_val)
        grid.Add(self.pitch_ctrl, flag=wx.EXPAND)

        sizer.Add(grid, proportion=1, flag=wx.ALL | wx.EXPAND, border=12)

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, flag=wx.ALL | wx.ALIGN_RIGHT, border=8)

        self.SetSizerAndFit(sizer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _parse_int(self, ctrl):
        val = ctrl.GetValue().strip()
        if not val:
            return None
        try:
            v = int(val)
            return max(0, min(100, v))
        except ValueError:
            return None

    def _on_ok(self, event):
        exe = self.exe_ctrl.GetValue().strip().lower()
        if not exe:
            gui.messageBox(
                # Translators: error when app name is empty
                _("Please enter an application name."),
                # Translators: error dialog title
                _("Error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._exe_name = exe
        voice_idx = self.voice_choice.GetSelection()
        choices = [""] + self._voice_ids
        voice = choices[voice_idx] if voice_idx >= 0 else ""
        self._profile = {
            "voice": voice or None,
            "rate": self._parse_int(self.rate_ctrl),
            "volume": self._parse_int(self.volume_ctrl),
            "pitch": self._parse_int(self.pitch_ctrl),
        }
        event.Skip()

    def get_result(self):
        return self._exe_name, self._profile


class SonataAppProfileDialog(wx.Dialog):
    """Main dialog listing all app profiles with Add / Edit / Delete."""

    def __init__(self, parent):
        super().__init__(
            parent,
            # Translators: title of app profiles dialog
            title=_("Sonata App Profiles"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._build_ui()
        self._refresh_list()
        self.SetSize((520, 400))
        self.CenterOnScreen()

    def _build_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Translators: description label in app profiles dialog
        sizer.Add(
            wx.StaticText(
                self,
                label=_(
                    "Configure per-application voice settings.\n"
                    "Sonata will automatically switch to the saved profile\n"
                    "when the specified application gains focus."
                ),
            ),
            flag=wx.ALL,
            border=8,
        )

        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        # Translators: column header for app name
        self.list_ctrl.InsertColumn(0, _("Application"), width=160)
        # Translators: column header for voice
        self.list_ctrl.InsertColumn(1, _("Voice"), width=200)
        # Translators: column header for rate
        self.list_ctrl.InsertColumn(2, _("Rate"), width=60)
        sizer.Add(self.list_ctrl, proportion=1, flag=wx.ALL | wx.EXPAND, border=8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: Add button
        self.add_btn = wx.Button(self, label=_("&Add..."))
        # Translators: Edit button
        self.edit_btn = wx.Button(self, label=_("&Edit..."))
        # Translators: Delete button
        self.delete_btn = wx.Button(self, label=_("&Delete"))
        btn_sizer.Add(self.add_btn, flag=wx.RIGHT, border=4)
        btn_sizer.Add(self.edit_btn, flag=wx.RIGHT, border=4)
        btn_sizer.Add(self.delete_btn)
        sizer.Add(btn_sizer, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        close_sizer = self.CreateButtonSizer(wx.CLOSE)
        sizer.Add(close_sizer, flag=wx.ALL | wx.ALIGN_RIGHT, border=8)

        self.SetSizer(sizer)

        self.add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        self.edit_btn.Bind(wx.EVT_BUTTON, self._on_edit)
        self.delete_btn.Bind(wx.EVT_BUTTON, self._on_delete)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_edit, self.list_ctrl)

    def _refresh_list(self):
        self.list_ctrl.DeleteAllItems()
        for exe, profile in app_profile_manager.list_profiles():
            idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), exe)
            self.list_ctrl.SetItem(idx, 1, profile.get("voice") or "")
            rate = profile.get("rate")
            self.list_ctrl.SetItem(idx, 2, str(rate) if rate is not None else "")

    def _selected_exe(self):
        idx = self.list_ctrl.GetFirstSelected()
        if idx == -1:
            return None
        return self.list_ctrl.GetItemText(idx, 0)

    def _on_add(self, event):
        dlg = SonataEditProfileDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            exe, profile = dlg.get_result()
            app_profile_manager.set_profile(exe, **profile)
            self._refresh_list()
        dlg.Destroy()

    def _on_edit(self, event):
        exe = self._selected_exe()
        if exe is None:
            return
        profile = app_profile_manager.get_profile(exe)
        dlg = SonataEditProfileDialog(self, exe_name=exe, profile=profile)
        if dlg.ShowModal() == wx.ID_OK:
            new_exe, new_profile = dlg.get_result()
            if new_exe != exe:
                app_profile_manager.delete_profile(exe)
            app_profile_manager.set_profile(new_exe, **new_profile)
            self._refresh_list()
        dlg.Destroy()

    def _on_delete(self, event):
        exe = self._selected_exe()
        if exe is None:
            return
        if gui.messageBox(
            # Translators: confirmation to delete app profile
            _("Delete profile for '{app}'?").format(app=exe),
            # Translators: title of confirmation dialog
            _("Confirm"),
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        ) == wx.YES:
            app_profile_manager.delete_profile(exe)
            self._refresh_list()
