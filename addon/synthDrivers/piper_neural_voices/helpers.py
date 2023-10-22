# coding: utf-8

# Copyright (c) 2021 Blind Pandas Team
# This file is covered by the GNU General Public License.

import sys
import os
import contextlib


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
