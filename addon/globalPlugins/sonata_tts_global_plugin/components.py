# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

from __future__ import annotations

import dataclasses
import contextlib
import typing

import wx
import wx.lib.mixins.listctrl as listmix
from . import sized_controls as sc


import gui


ObjectCollection = typing.Iterable[typing.Any]


def make_sized_static_box(parent, title):
    stbx = sc.SizedStaticBox(parent, -1, title)
    stbx.SetSizerProp("expand", True)
    stbx.Sizer.AddSpacer(25)
    return stbx


class DialogListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
    def __init__(
        self,
        parent,
        id,
        pos=wx.DefaultPosition,
        size=wx.DefaultSize,
        style=wx.BORDER_SUNKEN
        | wx.LC_SINGLE_SEL
        | wx.LC_REPORT
        | wx.LC_EDIT_LABELS
        | wx.LC_VRULES,
    ):
        wx.ListCtrl.__init__(self, parent, id, pos, size, style)
        listmix.ListCtrlAutoWidthMixin.__init__(self)

    def set_focused_item(self, idx: int):
        if idx >= self.ItemCount:
            return
        self.SetFocus()
        self.EnsureVisible(idx)
        self.Select(idx)
        self.SetItemState(idx, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED)


class SimpleDialog(sc.SizedDialog):
    """Basic dialog for simple  GUI forms."""

    def __init__(self, parent, title, style=wx.DEFAULT_DIALOG_STYLE, **kwargs):
        super().__init__(parent, title=title, style=style, **kwargs)
        self.parent = parent

        panel = self.GetContentsPane()
        self.addControls(panel)
        buttonsSizer = self.getButtons(panel)
        if buttonsSizer is not None:
            self.SetButtonSizer(buttonsSizer)

        self.Layout()
        self.Fit()
        self.SetMinSize(self.GetSize())
        self.Center(wx.BOTH)

    def SetButtonSizer(self, sizer):
        bottomSizer = wx.BoxSizer(wx.VERTICAL)
        line = wx.StaticLine(self, -1, size=(20, -1), style=wx.LI_HORIZONTAL)
        bottomSizer.Add(line, 0, wx.TOP | wx.EXPAND, 15)
        bottomSizer.Add(sizer, 0, wx.EXPAND | wx.ALL, 10)
        super().SetButtonSizer(bottomSizer)

    def addControls(self, parent):
        raise NotImplementedError

    def getButtons(self, parent):
        btnsizer = wx.StdDialogButtonSizer()
        # Translators: the label of the OK button in a dialog
        okBtn = wx.Button(self, wx.ID_OK, _("OK"))
        okBtn.SetDefault()
        # Translators: the label of the cancel button in a dialog
        cancelBtn = wx.Button(self, wx.ID_CANCEL, _("Cancel"))
        for btn in (okBtn, cancelBtn):
            btnsizer.AddButton(btn)
        btnsizer.Realize()
        return btnsizer


class SnakDialog(SimpleDialog):
    """A Toast style notification  dialog for showing a simple message without a title."""

    def __init__(self, message, *args, dismiss_callback=None, **kwargs):
        self.message = message
        self.dismiss_callback = dismiss_callback
        super().__init__(*args, title="", style=0, **kwargs)

    def addControls(self, parent):
        ai = wx.ActivityIndicator(parent)
        ai.SetSizerProp("halign", "center")
        self.staticMessage = wx.StaticText(parent, -1, self.message)
        self.staticMessage.SetCanFocus(True)
        self.staticMessage.SetFocusFromKbd()
        self.Bind(wx.EVT_CLOSE, self.onClose, self)
        self.staticMessage.Bind(wx.EVT_KEY_UP, self.onKeyUp, self.staticMessage)
        ai.Start()

    @contextlib.contextmanager
    def ShowBriefly(self):
        try:
            wx.CallAfter(self.ShowModal)
            yield
        finally:
            wx.CallAfter(self.Close)
            wx.CallAfter(self.Destroy)

    def onClose(self, event):
        if event.CanVeto():
            if self.dismiss_callback is not None:
                should_close = self.dismiss_callback()
                if should_close:
                    self.Hide()
                    return
            event.Veto()
        else:
            self.Destroy()

    def onKeyUp(self, event):
        event.Skip()
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()

    def getButtons(self, parent):
        return


class AsyncSnakDialog:
    """A helper to make the use of SnakDialogs Ergonomic."""

    def __init__(
        self,
        executor,
        func,
        done_callback: DoneCallback,
        *sdg_args,
        **sdg_kwargs,
    ):
        self.snak_dg = SnakDialog(*sdg_args, **sdg_kwargs)
        self.done_callback = done_callback
        self.future = executor.submit(func).add_done_callback(
            self.on_future_completed
        )
        self.snak_dg.CenterOnScreen()
        gui.runScriptModalDialog(self.snak_dg)

    def on_future_completed(self, completed_future):
        self.Dismiss()
        wx.CallAfter(self.done_callback, completed_future)

    def Dismiss(self):
        if self.snak_dg:
            wx.CallAfter(self.snak_dg.Hide)
            wx.CallAfter(self.snak_dg.Close)
            wx.CallAfter(self.snak_dg.Destroy)


@dataclasses.dataclass
class ColumnDefn:
    title: str
    alignment: str
    width: int
    string_converter: t.Union[typing.Callable[[typing.Any], str], str]

    _ALIGNMENT_FLAGS = {
        "left": wx.LIST_FORMAT_LEFT,
        "center": wx.LIST_FORMAT_CENTRE,
        "right": wx.LIST_FORMAT_RIGHT,
    }

    @property
    def alignment_flag(self):
        flag = self._ALIGNMENT_FLAGS.get(self.alignment)
        if flag is not None:
            return flag
        raise ValueError(f"Unknown alignment directive {self.alignment}")


class ImmutableObjectListView(DialogListCtrl):
    """An immutable  list view that deals with objects rather than strings."""

    def __init__(
        self,
        *args,
        columns: typing.Iterable[ColumnDefn] = (),
        objects: ObjectCollection = (),
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._objects = None
        self._columns = None
        self.Bind(wx.EVT_LIST_DELETE_ITEM, self.onDeleteItem, self)
        self.Bind(wx.EVT_LIST_DELETE_ALL_ITEMS, self.onDeleteAllItems, self)
        self.Bind(wx.EVT_LIST_INSERT_ITEM, self.onInsertItem, self)
        self.__is_modifying = False
        self.set_columns(columns)
        self.set_objects(objects)

    @contextlib.contextmanager
    def __unsafe_modify(self):
        self.__is_modifying = True
        yield
        self.__is_modifying = False

    def set_columns(self, columns):
        self.ClearAll()
        self._columns = columns
        for col in self._columns:
            self.AppendColumn(col.title, format=col.alignment_flag, width=col.width)
        for i in range(len(columns)):
            self.SetColumnWidth(i, 100)

    def set_objects(
        self, objects: ObjectCollection, focus_item: int = 0, set_focus=True
    ):
        """Clear the list view and insert the objects."""
        self._objects = objects
        self.set_columns(self._columns)
        string_converters = [c.string_converter for c in self._columns]
        with self.__unsafe_modify():
            for obj in self._objects:
                col_labels = []
                for to_str in string_converters:
                    col_labels.append(
                        getattr(obj, to_str) if not callable(to_str) else to_str(obj)
                    )
                self.Append(col_labels)
        if set_focus:
            self.set_focused_item(focus_item)

    def get_selected(self) -> typing.Optional[typing.Any]:
        """Return the currently selected object or None."""
        idx = self.GetFocusedItem()
        if idx != wx.NOT_FOUND:
            return self._objects[idx]

    def prevent_mutations(self):
        if not self.__is_modifying:
            raise RuntimeError(
                "List is immutable. Use 'ImmutableObjectListView.set_objects' instead"
            )

    def onDeleteItem(self, event):
        self.prevent_mutations()

    def onDeleteAllItems(self, event):
        ...

    def onInsertItem(self, event):
        self.prevent_mutations()
