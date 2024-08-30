# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.


import contextlib
import os
import shutil
import sys
import tempfile

from logHandler import log


_DIR = os.path.abspath(os.path.dirname(__file__))
_PIPER_SYNTH_DIR = os.path.join(_DIR, "synthDrivers", "sonata_neural_voices")
LIB_DIR = os.path.join(_PIPER_SYNTH_DIR, "lib")
BIN_DIR = os.path.join(_PIPER_SYNTH_DIR, "bin")
del _DIR, _PIPER_SYNTH_DIR


def onUninstall():
    with _temporary_import_psutil() as psutil:
        force_kill_sonata_grpc_server(psutil)


def force_kill_sonata_grpc_server(psutil):
    log.debug("Trying to force kill GRPC server process")
    grpc_server_processes = list(filter(
        lambda p: "sonata-grpc" in p.name().lower(),
        psutil.process_iter(attrs=["name", "exe"])
    ))
    grpc_server_exe = os.path.join(BIN_DIR, "sonata-grpc.exe")
    for proc in grpc_server_processes:
        if os.path.samefile(proc.exe(), grpc_server_exe):
            proc.kill()
            log.debug(f"Killed process with pid {proc.pid}")
    psutil.wait_procs(
        grpc_server_processes,
        timeout=5,
    )


@contextlib.contextmanager
def _temporary_import_psutil():
    temp_import_dir = tempfile.TemporaryDirectory()
    src = os.path.join(LIB_DIR, "psutil")
    # py3_lib_src = os.path.join(LIB_DIR, "python3.dll")
    dst = os.path.join(temp_import_dir.name, "psutil")
    shutil.copytree(src, dst)
    # shutil.copy2(py3_lib_src, dst)
    sys.path.insert(0, temp_import_dir.name)
    import psutil
    yield psutil
    sys.path.remove(temp_import_dir.name)
    with contextlib.suppress(Exception):
        temp_import_dir.cleanup()
