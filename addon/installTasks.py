# coding: utf-8

# Copyright (c) Musharraf Omer
# This file is covered by the GNU General Public License.


import platform

import gui


import addonHandler
addonHandler.initTranslation()


def onInstall():
    if platform.machine() != 'AMD64':
        gui.messageBox(
            # Translators: content of a message box
            _("32-bit system detected. Piper voices work on 64-bit systems only. Installation aborted!"),
            # Translators: title of a message box
            _("64-bit system required"),
            wx.ICON_ERROR
        )
        raise RuntimeError("Unsupported OS architecture")

