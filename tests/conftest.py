# coding: utf-8
"""
conftest.py — Stubs for NVDA's internal modules so tests can run
outside of the NVDA runtime environment.

Strategy
--------
1. Stub all NVDA-internal packages (config, languageHandler, etc.).
2. Stub the bundled Windows-only grpc Cython extensions.
3. Register `sonata_neural_voices` as a package in sys.modules WITHOUT
   running its __init__.py (which imports grpc_client at module level).
4. Stub the intra-package submodules that have platform-specific deps
   (grpc_client, aio) so relative imports in tts_system.py succeed.
5. Load the real submodules we want to test (const, helpers, tts_system).
"""

import sys
import os
import types
import importlib.util
from concurrent.futures import Future as _Future
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _stub_module(name: str, **attrs) -> types.ModuleType:
    """Create a plain module stub and register it in sys.modules."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _make_ready_future(value=None) -> _Future:
    f: _Future = _Future()
    f.set_result(value)
    return f


_TESTS_DIR = os.path.dirname(__file__)
_SYNTH_DIR = os.path.join(_TESTS_DIR, "..", "addon", "synthDrivers")
_SYNTH_PKG_DIR = os.path.join(_SYNTH_DIR, "sonata_neural_voices")


def _load_real_module(module_name: str, filename: str) -> types.ModuleType:
    """Execute a real .py file as a registered module (with relative imports)."""
    path = os.path.join(_SYNTH_PKG_DIR, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "sonata_neural_voices"
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. Stub grpc, SCons, and all submodules
# ---------------------------------------------------------------------------

for _grpc_name in [
    "grpc", "grpc._cython", "grpc._cython.cygrpc",
    "grpc._compression", "grpc.experimental", "grpc.aio",
]:
    sys.modules.setdefault(_grpc_name, MagicMock())

_stub_module("SCons")
_stub_module("SCons.Script", Environment=MagicMock(), Builder=MagicMock())
_stub_module("markdown")


# ---------------------------------------------------------------------------
# 2. NVDA internal stubs
# ---------------------------------------------------------------------------

# globalVars
_stub_module("globalVars", appArgs=types.SimpleNamespace(configPath="/tmp/nvda_test_config"))

# languageHandler
def _normalize_language(lang: str) -> str:
    return lang.lower().replace("_", "-")

_stub_module("languageHandler", normalizeLanguage=_normalize_language)

# config
class _FakeConfSection(dict):
    def __missing__(self, key):
        val = _FakeConfSection()
        self[key] = val
        return val
    def isSet(self, key):
        return key in self
    @property
    def spec(self):
        return _FakeConfSection()
    def update(self, other):
        pass

_fake_conf = _FakeConfSection()
_fake_conf["audio"]["outputDevice"] = "default"
_fake_conf["speech"]["sonata_neural_voices"] = _FakeConfSection()
_stub_module("config", conf=_fake_conf)

# configobj
_stub_module("configobj", ConfigObj=MagicMock())

# logHandler
_stub_module("logHandler", log=MagicMock())

# synthDriverHandler
class _FakeSynthDriver:
    cachePropertiesByDefault = False
    VoiceSetting = MagicMock(return_value=MagicMock())
    VariantSetting = MagicMock(return_value=MagicMock())
    RateSetting = MagicMock(return_value=MagicMock())
    RateBoostSetting = MagicMock(return_value=MagicMock())
    VolumeSetting = MagicMock(return_value=MagicMock())
    PitchSetting = MagicMock(return_value=MagicMock())
    def __init__(self): pass
    def _percentToParam(self, percent, min_val, max_val):
        return min_val + (max_val - min_val) * percent / 100

_stub_module(
    "synthDriverHandler",
    SynthDriver=_FakeSynthDriver,
    VoiceInfo=MagicMock(side_effect=lambda id, name, lang: (id, name, lang)),
    synthDoneSpeaking=MagicMock(),
    synthIndexReached=MagicMock(),
)

# autoSettingsUtils
_stub_module("autoSettingsUtils")
_stub_module(
    "autoSettingsUtils.driverSetting",
    DriverSetting=MagicMock(return_value=MagicMock()),
    NumericDriverSetting=MagicMock(return_value=MagicMock()),
)

# nvwave
class _FakeWavePlayer:
    def __init__(self, *args, **kwargs): pass
    def feed(self, data): pass
    def sync(self): pass
    def stop(self): pass
    def pause(self, switch): pass
    def close(self): pass
    def idle(self): pass
    def setVolume(self, **kwargs): pass

_stub_module("nvwave", WavePlayer=_FakeWavePlayer)

# speech + speech.commands
_say_all = MagicMock()
_say_all.isRunning.return_value = False
_speech_mod = _stub_module("speech")
_speech_mod.sayAll = MagicMock()
_speech_mod.sayAll.SayAllHandler = _say_all
_stub_module(
    "speech.commands",
    IndexCommand=type("IndexCommand", (), {"index": 0}),
    BreakCommand=type("BreakCommand", (), {"time": 0}),
    LangChangeCommand=type("LangChangeCommand", (), {"lang": "en", "isDefault": False}),
    RateCommand=type("RateCommand", (), {"newValue": 50}),
    VolumeCommand=type("VolumeCommand", (), {"newValue": 100}),
    PitchCommand=type("PitchCommand", (), {"newValue": 50}),
)

# addonHandler
_stub_module("addonHandler", initTranslation=MagicMock())

# wx / gui
_stub_module("wx", ID_ANY=0, YES=1, NO=2, YES_NO=3, ICON_WARNING=4, EVT_MENU=MagicMock())
_stub_module("gui")
_stub_module("gui.settingsDialogs", NVDASettingsDialog=MagicMock(), SpeechSettingsPanel=MagicMock())
_stub_module("core", postNvdaStartup=MagicMock())
_stub_module("globalPluginHandler", GlobalPlugin=MagicMock())


# ---------------------------------------------------------------------------
# 3. Register `sonata_neural_voices` as a package WITHOUT running __init__.py
# ---------------------------------------------------------------------------

# Add synthDrivers to path so the package is findable
if _SYNTH_DIR not in sys.path:
    sys.path.insert(0, _SYNTH_DIR)

# Register the package stub (no __init__.py executed)
_pkg = types.ModuleType("sonata_neural_voices")
_pkg.__path__ = [_SYNTH_PKG_DIR]
_pkg.__package__ = "sonata_neural_voices"
_pkg.__spec__ = importlib.util.spec_from_file_location(
    "sonata_neural_voices",
    os.path.join(_SYNTH_PKG_DIR, "__init__.py"),
    submodule_search_locations=[_SYNTH_PKG_DIR],
)
sys.modules["sonata_neural_voices"] = _pkg


# ---------------------------------------------------------------------------
# 4. Stub intra-package submodules that have platform/runtime dependencies
# ---------------------------------------------------------------------------

# grpc_client — talks to a real gRPC server; stub completely
class _FakeVoiceInfo:
    voice_id = "test-voice-id"
    supports_streaming_output = False
    class audio:
        sample_rate = 22050
    class synth_options:
        length_scale = 1.0
        noise_scale = 0.667
        noise_w = 0.8
        speaker = "default"
    speakers = {}

_grpc_client = _stub_module("sonata_neural_voices.grpc_client")
_grpc_client.initialize = MagicMock(return_value=_make_ready_future(None))
_grpc_client.check_grpc_server = MagicMock(return_value=_make_ready_future("1.0.0"))
_grpc_client.load_voice = MagicMock(return_value=_make_ready_future(_FakeVoiceInfo()))
_grpc_client.speak = MagicMock(return_value=iter([]))
_grpc_client.get_synth_options = MagicMock(
    return_value=_make_ready_future(_FakeVoiceInfo.synth_options())
)
_grpc_client.set_synth_options = MagicMock(return_value=_make_ready_future(None))
_grpc_client.SONATA_GRPC_SERVER_PORT = 50051

# aio — starts real threads/event loops; stub completely
_aio = _stub_module("sonata_neural_voices.aio")
_aio.initialize = MagicMock()
_aio.terminate = MagicMock()
_aio.ASYNCIO_EVENT_LOOP = MagicMock()
_aio.CancelledError = Exception
_aio.asyncio = MagicMock()
_aio.asyncio_cancel_task = MagicMock()
_aio.asyncio_coroutine_to_concurrent_future = lambda f: f
_aio.run_in_executor = MagicMock()


# ---------------------------------------------------------------------------
# 5. Load real submodules we actually want to test
# ---------------------------------------------------------------------------

_load_real_module("sonata_neural_voices.const", "const.py")
_load_real_module("sonata_neural_voices.helpers", "helpers.py")
_load_real_module("sonata_neural_voices.tts_system", "tts_system.py")
