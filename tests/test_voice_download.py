import os
import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

# Set up mock NVDA runtime modules before importing addon modules
for mod_name in ("wx", "core", "gui", "languageHandler", "logHandler"):
    if mod_name not in sys.modules:
        m = types.ModuleType(mod_name)
        m.normalizeLanguage = lambda lang: lang
        m.log = MagicMock()
        sys.modules[mod_name] = m

import builtins
if not hasattr(builtins, "_"):
    builtins._ = lambda s: s

# Setup package mock for sonata_tts_global_plugin
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
plugin_dir = os.path.join(repo_root, "addon", "globalPlugins", "sonata_tts_global_plugin")
synth_lib_dir = os.path.join(repo_root, "addon", "synthDrivers", "sonata_neural_voices", "lib")

if "sonata_tts_global_plugin" not in sys.modules:
    pkg = types.ModuleType("sonata_tts_global_plugin")
    pkg.__path__ = [plugin_dir]
    pkg.SonataTextToSpeechSystem = MagicMock()
    pkg.SonataTextToSpeechSystem.load_piper_voices_from_nvda_config_dir.return_value = []
    pkg.SonataTextToSpeechSystem.get_voice_variants.return_value = ("", "")
    pkg.SONATA_VOICES_DIR = "/tmp/sonata_voices_test"

    @contextmanager
    def _dummy_import_bundled_library():
        if synth_lib_dir not in sys.path:
            sys.path.insert(0, synth_lib_dir)
        yield

    pkg.helpers = MagicMock()
    pkg.helpers.import_bundled_library = _dummy_import_bundled_library
    sys.modules["sonata_tts_global_plugin"] = pkg

import importlib
voice_download = importlib.import_module("sonata_tts_global_plugin.voice_download")


class TestVoiceDownload(unittest.TestCase):
    def setUp(self):
        self.test_voices_dir = os.path.join("/tmp", "sonata_voices_test")
        os.makedirs(self.test_voices_dir, exist_ok=True)
        voice_download.PIPER_VOICES_JSON_LOCAL_CACHE = os.path.join(
            self.test_voices_dir, "piper-voices.json"
        )
        if os.path.exists(voice_download.PIPER_VOICES_JSON_LOCAL_CACHE):
            os.remove(voice_download.PIPER_VOICES_JSON_LOCAL_CACHE)

    def tearDown(self):
        if os.path.exists(voice_download.PIPER_VOICES_JSON_LOCAL_CACHE):
            os.remove(voice_download.PIPER_VOICES_JSON_LOCAL_CACHE)

    def test_voice_list_urls_use_raw_endpoint(self):
        """Verify voice list URLs use /raw/ endpoints to avoid HuggingFace redirects."""
        self.assertIn("/raw/", voice_download.PIPER_VOICE_LIST_URL)
        self.assertNotIn("/resolve/", voice_download.PIPER_VOICE_LIST_URL)
        self.assertIn("/raw/", voice_download.RT_VOICE_LIST_URL)
        self.assertNotIn("/resolve/", voice_download.RT_VOICE_LIST_URL)

    @patch.object(voice_download.request, "get")
    def test_get_available_voices_passes_max_redirects(self, mock_get):
        """Verify request.get is invoked with max_redirects=5."""
        fake_piper = {
            "en_US-test-low": {
                "key": "en_US-test-low",
                "name": "test",
                "quality": "low",
                "num_speakers": 1,
                "speaker_id_map": {},
                "language": {
                    "code": "en_US",
                    "family": "en",
                    "region": "US",
                    "name_native": "English",
                    "name_english": "English",
                    "country_english": "United States",
                },
                "files": {},
                "has_rt_variant": False,
                "standard_variant_installed": False,
                "fast_variant_installed": False,
            }
        }
        fake_rt = {}

        mock_std_resp = MagicMock()
        mock_std_resp.json.return_value = fake_piper
        mock_rt_resp = MagicMock()
        mock_rt_resp.json.return_value = fake_rt

        mock_get.side_effect = [mock_std_resp, mock_rt_resp]

        voices = voice_download.get_available_voices(force_online=True)
        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].key, "en_US-test-low")

        self.assertEqual(mock_get.call_count, 2)
        std_call_args, std_call_kwargs = mock_get.call_args_list[0]
        self.assertEqual(std_call_args[0], voice_download.PIPER_VOICE_LIST_URL)
        self.assertEqual(std_call_kwargs.get("max_redirects"), 5)

        rt_call_args, rt_call_kwargs = mock_get.call_args_list[1]
        self.assertEqual(rt_call_args[0], voice_download.RT_VOICE_LIST_URL)
        self.assertEqual(rt_call_kwargs.get("max_redirects"), 5)

    @patch.object(voice_download.request, "get")
    def test_get_available_voices_json_decode_error_raises_runtime_error(self, mock_get):
        """Verify JSONDecodeError when parsing voice list response raises RuntimeError."""
        import json

        mock_resp = MagicMock()
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        mock_get.return_value = mock_resp

        with self.assertRaises(RuntimeError) as ctx:
            voice_download.get_available_voices(force_online=True)

        self.assertIn("Failed to parse standard voices JSON", str(ctx.exception))

    @patch.object(voice_download.request, "get")
    def test_get_available_voices_rt_json_decode_error_raises_runtime_error(self, mock_get):
        """Verify JSONDecodeError on RT voice list response raises RuntimeError."""
        import json

        mock_std_resp = MagicMock()
        mock_std_resp.json.return_value = {}
        mock_rt_resp = MagicMock()
        mock_rt_resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        mock_get.side_effect = [mock_std_resp, mock_rt_resp]

        with self.assertRaises(RuntimeError) as ctx:
            voice_download.get_available_voices(force_online=True)

        self.assertIn("Failed to parse RT voices JSON", str(ctx.exception))

    @patch.object(voice_download.request, "yield_response")
    def test_do_download_file_passes_max_redirects(self, mock_yield_response):
        """Verify _do_download_file calls yield_response with max_redirects=5."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.side_effect = [b"chunk1", b"chunk2", b""]
        mock_yield_response.return_value.__enter__.return_value = mock_resp

        fake_file = voice_download.PiperVoiceFile(
            file_path="test/path/file.onnx",
            size_in_bytes=12,
            md5hash="dummy",
        )
        fake_progress = MagicMock()

        voice_download.PiperVoiceDownloader._do_download_file(
            fake_file, self.test_voices_dir, fake_progress
        )

        mock_yield_response.assert_called_once()
        args, kwargs = mock_yield_response.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], fake_file.download_url)
        self.assertEqual(kwargs.get("max_redirects"), 5)

    @patch.object(voice_download.request, "yield_response")
    def test_do_download_archive_passes_max_redirects(self, mock_yield_response):
        """Verify _do_download_archive calls yield_response with max_redirects=5."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.getheader.return_value = "12"
        mock_resp.read.side_effect = [b"chunk1", b"chunk2", b""]
        mock_yield_response.return_value.__enter__.return_value = mock_resp

        fake_progress = MagicMock()
        download_url = "https://example.com/voice.tar.gz"

        voice_download.PiperRTVoiceDownloader._do_download_archive(
            download_url, "voice.tar.gz", self.test_voices_dir, fake_progress
        )

        mock_yield_response.assert_called_once()
        args, kwargs = mock_yield_response.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], download_url)
        self.assertEqual(kwargs.get("max_redirects"), 5)


if __name__ == "__main__":
    unittest.main()
