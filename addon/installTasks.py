# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.


import os
import sys

from logHandler import log


_DIR = os.path.abspath(os.path.dirname(__file__))
_LIB_DIR = os.path.join(_DIR, "synthDrivers", "piper_neural_voices", "lib")
BIN_DIR = os.path.join(_DIR, "synthDrivers", "piper_neural_voices", "bin")
sys.path.insert(0, _LIB_DIR)
import psutil
sys.path.remove(_LIB_DIR)
del _DIR, _LIB_DIR


def force_kill_piper_grpc_server():
    log.debug("Trying to force kill GRPC server process")
    grpc_server_processes = list(filter(
        lambda p: "piper-grpc" in p.name,
        psutil.process_iter(attrs=["name", "exe"])
    ))
    grpc_server_exe = os.path.normpath(
        os.path.abspath(os.path.join(BIN_DIR, "piper-grpc.exe"))
    )
    for proc in grpc_server_processes:
        if os.path.normpath(os.path.abspath(proc.exe())) == grpc_server_exe:
            proc.kill()
            log.debug(f"Killed process with pid {proc.pid}")
    psutil.wait_procs(
        grpc_server_processes,
        timeout=5,
    )


def onUninstall():
    force_kill_piper_grpc_server()
