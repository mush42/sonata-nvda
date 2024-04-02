# coding: utf-8

import atexit
import os
import subprocess
import time

import globalVars
from logHandler import log

from ..const import PIPER_VOICES_BASE_DIR
from ..helpers import BIN_DIRECTORY, find_free_port, import_bundled_library
from pathlib import Path

with import_bundled_library():
    from grpclib.client import Channel
    from .. import aio
    from .grpc_protos.piper_grpc_grpc import piper_grpcStub
    from .grpc_protos import piper_grpc_pb2 as msgs


PIPER_GRPC_SERVER_PORT = None
GRPC_SERVER_PROCESS = None
CHANNEL = None
PIPER_GRPC_SERVICE = None


def start_grpc_server():
    global GRPC_SERVER_PROCESS, PIPER_GRPC_SERVER_PORT
    if hasattr(globalVars, "PIPER_GRPC_SERVER_PORT"):
        PIPER_GRPC_SERVER_PORT = globalVars.PIPER_GRPC_SERVER_PORT
        GRPC_SERVER_PROCESS = globalVars.GRPC_SERVER_PROCESS
        return True
    PIPER_GRPC_SERVER_PORT = find_free_port()
    grpc_server_exe = os.path.join(BIN_DIRECTORY, "piper-grpc.exe")
    nvda_espeak_dir = os.path.join(globalVars.appDir, "synthDrivers")
    onnx_dll_path = os.path.join(BIN_DIRECTORY, "onnxruntime.dll")
    env = os.environ.copy()
    env.update({
        "PIPER_GRPC_SERVER_PORT": str(PIPER_GRPC_SERVER_PORT),
        "PIPER_ESPEAKNG_DATA_DIRECTORY": os.fspath(nvda_espeak_dir),
        "ORT_DYLIB_PATH": os.fspath(onnx_dll_path),
        "PIPER_GRPC": "info",
    })
    creationflags = (
        subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.REALTIME_PRIORITY_CLASS
    )
    try:
        server_log_file = os.path.join(PIPER_VOICES_BASE_DIR, "logs", "piper-grpc.log")
        Path(server_log_file).parent.mkdir(parents=True, exist_ok=True)
        server_stdout = open(server_log_file, "wb")
    except:
        log.exception("Failed to open server log file for writing", exc_info=True)
        server_stdout = subprocess.DEVNULL
    try:
        GRPC_SERVER_PROCESS = subprocess.Popen(
            args=grpc_server_exe,
            cwd=os.fspath(BIN_DIRECTORY),
            env=env,
            creationflags=creationflags,
            stdout=server_stdout,
            stderr=subprocess.STDOUT,
        )
    except:
        log.exception(
            "Failed to start Piper GRPC server. The synth will not be available.",
            exc_info=True
        )
        return False
    globalVars.PIPER_GRPC_SERVER_PORT = PIPER_GRPC_SERVER_PORT
    globalVars.GRPC_SERVER_PROCESS = GRPC_SERVER_PROCESS
    return True


def initialize():
    global CHANNEL, PIPER_GRPC_SERVICE, PIPER_GRPC_SERVER_PORT
    start_grpc_server()
    aio.initialize()
    if CHANNEL is not None:
        log.warning("Attempted to re-initialize an already initialized GRPC connection")
        return
    CHANNEL = Channel(
        "localhost",
        PIPER_GRPC_SERVER_PORT,
        loop=aio.ASYNCIO_EVENT_LOOP
    )
    PIPER_GRPC_SERVICE = piper_grpcStub(CHANNEL)


@atexit.register
def terminate():
    global CHANNEL, GRPC_SERVER_PROCESS, PIPER_GRPC_SERVER_PORT
    PIPER_GRPC_SERVER_PORT = None
    aio.terminate()
    if CHANNEL is not None:
        CHANNEL.close()
        CHANNEL = None
    if GRPC_SERVER_PROCESS is not None:
        GRPC_SERVER_PROCESS.terminate()
        GRPC_SERVER_PROCESS = None


@aio.asyncio_coroutine_to_concurrent_future
async def check_grpc_server(timeout=30) -> str:
    return await asyncio.wait_for(
        get_piper_version(), timeout, loop=aio.ASYNCIO_EVENT_LOOP
    )


async def get_piper_version():
    resp = await PIPER_GRPC_SERVICE.GetPiperVersion(msgs.Empty())
    return resp.version


@aio.asyncio_coroutine_to_concurrent_future
async def load_voice(config_path):
    req = msgs.VoicePath(config_path=config_path)
    return await PIPER_GRPC_SERVICE.LoadVoice(req)


@aio.asyncio_coroutine_to_concurrent_future
async def get_synth_options(voice_id):
    req = msgs.VoiceIdentifier(voice_id=voice_id)
    return await PIPER_GRPC_SERVICE.GetSynthesisOptions(req)


@aio.asyncio_coroutine_to_concurrent_future
async def set_synth_options(
    voice_id, speaker=None, length_scale=None, noise_scale=None, noise_w=None
):
    req = msgs.VoiceSynthesisOptions(
        voice_id=voice_id,
        synthesis_options=msgs.SynthesisOptions(
            speaker=speaker,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w=noise_w,
        ),
    )
    return await PIPER_GRPC_SERVICE.SetSynthesisOptions(req)


async def speak(
    voice_id, text, rate=None, volume=None, pitch=None, appended_silence_ms=None, streaming=False
):
    speech_args = None
    if any([rate, volume, pitch, appended_silence_ms]):
        speech_args = msgs.SpeechArgs(
            rate=rate,
            volume=volume,
            pitch=pitch,
            appended_silence_ms=appended_silence_ms,
        )
    utterance = msgs.Utterance(
        voice_id=voice_id,
        text=text,
        speech_args=speech_args,
    )
    if streaming:
        stream = PIPER_GRPC_SERVICE.SynthesizeUtteranceRealtime.open()
    else:
        stream = PIPER_GRPC_SERVICE.SynthesizeUtterance.open()
    async with stream:
        await stream.send_message(utterance, end=True)
        async for ret in stream:
            yield ret


async def bench(n=10000):
    initialize()
    t0 = time.perf_counter()
    for i in range(n):
        await get_piper_version()
    return time.perf_counter() - t0
