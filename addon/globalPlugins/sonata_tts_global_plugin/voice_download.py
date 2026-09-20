# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.


import json
import math
import os
import re
import shutil
import tarfile
import tempfile
import typing
import urllib.parse
from dataclasses import dataclass
from enum import Enum, auto
from fnmatch import fnmatch
from functools import partial
from hashlib import md5
from http.client import HTTPException
from io import BytesIO

import wx
import core
import gui
from languageHandler import normalizeLanguage
from logHandler import log

from . import SonataTextToSpeechSystem, helpers, SONATA_VOICES_DIR

with helpers.import_bundled_library():
    import mureq as request
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path


PIPER_VOICE_LIST_URL = "https://huggingface.co/rhasspy/piper-voices/raw/v1.0.0/voices.json"
PIPER_VOICE_DOWNLOAD_URL_PREFIX = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
PIPER_SAMPLES_URL_PREFIX = "https://rhasspy.github.io/piper-samples/samples"
PIPER_VOICES_JSON_LOCAL_CACHE = os.path.join(SONATA_VOICES_DIR, "piper-voices.json")
RT_VOICE_LIST_URL = "https://huggingface.co/datasets/mush42/piper-rt/raw/main/voices.json"
RT_VOICE_DOWNLOAD_URL_PREFIX = "https://huggingface.co/datasets/mush42/piper-rt/resolve/main"

VOICE_INFO_REGEX = re.compile(
    r"(?P<language>[a-z]+(_|-)?([a-z]+)?)(-|_)"
    r"(?P<name>[\w]+(\+RT)?)(-|_)"
    r"(?P<quality>(high|medium|low|x-low|x_low))",
    re.I
)
THREAD_POOL_EXECUTOR = ThreadPoolExecutor()


class PiperVoiceQualityLevel(Enum):
    XLow = "x_low"
    Low = "low"
    Medium = "medium"
    High = "high"

    def __str__(self):
        return " ".join(v.title() for v in self.value.split("_"))


class PiperVoiceFileType(Enum):
    Onnx = auto()
    Config = auto()
    ModelCard = auto()


@dataclass
class PiperVoiceFile:
    file_path: str
    size_in_bytes: int
    md5hash: str

    def __post_init__(self):
        self.name = os.path.split(self.file_path)[-1]
        self.download_url = f"{PIPER_VOICE_DOWNLOAD_URL_PREFIX}/{self.file_path}"

    @property
    def type(self):
        suffix = Path(self.file_path).suffix.lstrip(".")
        if suffix == "onnx":
            return PiperVoiceFileType.Onnx
        elif suffix == "json":
            return PiperVoiceFileType.Config
        elif suffix == "":
            return PiperVoiceFileType.ModelCard
        raise ValueError(f"Unknown file type: {suffix}")


@dataclass(eq=False)
class PiperVoiceLanguage:
    code: str
    family: str
    region: str
    name_native: str
    name_english: str
    country_english: str

    def __str__(self):
        return self.code.replace("_", "-")

    def __eq__(self, other):
        if isinstance(other, PiperVoiceLanguage):
            return self.code == other.code
        return NotImplemented

    def __hash__(self):
        return hash(self.code)

    @property
    def description(self):
        code = self.code.replace("_", "-")
        if "English" not in self.name_native:
            return f"{self.name_english} ({self.country_english}) , {code}, {self.name_native}"
        return f"{self.name_english} ({self.country_english}), {code}"


@dataclass
class PiperVoice:
    key: str
    name: str
    quality: PiperVoiceQualityLevel
    num_speakers: int
    speaker_id_map: typing.Dict[str, int]
    language: PiperVoiceLanguage
    files: typing.List[PiperVoiceFile]
    has_rt_variant: bool = False
    standard_variant_installed: bool = False
    fast_variant_installed: bool = False

    @classmethod
    def from_list_of_dicts(cls, voice_data):
        retval = []

        for data in voice_data:
            file_list = []
            for (path, finfo) in data["files"].items():
                file_list.append(PiperVoiceFile(
                    file_path=path,
                    size_in_bytes=finfo["size_bytes"],
                    md5hash=finfo["md5_digest"]
                ))
            lang_info = data["language"]
            language = PiperVoiceLanguage(
                code=lang_info["code"],
                family=lang_info["family"],
                region=lang_info["region"],
                name_native=lang_info["name_native"],
                name_english=lang_info["name_english"],
                country_english=lang_info["country_english"],
            )
            retval.append(cls(
                key=data["key"],
                name=data["name"],
                quality=PiperVoiceQualityLevel(data["quality"]),
                num_speakers=data["num_speakers"],
                speaker_id_map=data["speaker_id_map"],
                language=language,
                files=file_list,
                has_rt_variant=data["has_rt_variant"],
                standard_variant_installed=data["standard_variant_installed"],
                fast_variant_installed=data["fast_variant_installed"]
            ))

        retval.sort(key=lambda v: v.language.family)
        return retval

    def get_preview_url(self, speaker_idx=0):
        lang_path = f"{self.language.family.lower()}/{self.language.code}"
        quality = self.quality.value.lower()
        return f"{PIPER_SAMPLES_URL_PREFIX}/{lang_path}/{self.name}/{quality}/speaker_{speaker_idx}.mp3"

    def get_rt_variant_download_url(self):
        if not self.has_rt_variant:
            raise ValueError(f"Voice `{self.key}` has no RT variant")
        ___, rt_voice_key = SonataTextToSpeechSystem.get_voice_variants(self.key)
        return f"{RT_VOICE_DOWNLOAD_URL_PREFIX}/{rt_voice_key}.tar.gz"


class PiperVoiceDownloader:
    def __init__(self, voice: PiperVoice, success_callback):
        self.voice = voice
        self.success_callback = success_callback
        self.temp_download_dir = tempfile.TemporaryDirectory()
        self.progress_dialog = None

    def update_progress(self, progress):
        self.progress_dialog.Update(
            progress,
            # Translators: message of a progress dialog
            _("Downloaded: {progress}%").format(progress=progress),
        )

    def done_callback(self, result):
        has_error = isinstance(result, Exception)
        if not has_error:
            self.progress_dialog.Update(
                0,
                # Translators: message shown in the voice download progress dialog
                _("Installing voice")
            )
            hashes = {
                file.name: (file.md5hash, md5hash)
                for (file, __, md5hash) in result
            }
            if not all(expected == actual for expected, actual in hashes.values()):
                has_error = True
                log.error("File hashes do not match")
            else:
                voice_dir = Path(SONATA_VOICES_DIR).joinpath(self.voice.key)
                voice_dir.mkdir(parents=True, exist_ok=True)
                for file, src, __ in result:
                    dst = os.path.join(voice_dir, file.name)
                    try:
                        shutil.copy(src, dst)
                    except IOError:
                        log.exception(f"Failed to copy file: {file}", exc_info=True)
                        has_error = True

        self.progress_dialog.Hide()
        self.progress_dialog.Destroy()
        del self.progress_dialog

        if not has_error:
            self.success_callback()
            retval = gui.messageBox(
            # Translators: content of a message box
            _(
                "Successfully downloaded voice  {voice}.\n"
                "To use this voice, you need to restart NVDA.\n"
                "Do you want to restart NVDA now?"
            ).format(
                voice=self.voice.key
            ),
            # Translators: title of a message box
            _("Voice downloaded"),
                wx.YES_NO | wx.ICON_WARNING,
                parent=gui.mainFrame,
            )
            if retval == wx.YES:
                core.restart()
        else:
            wx.CallAfter(
                gui.messageBox,
                _(
                    "Cannot download voice {voice}.\nPlease check your connection and try again."
                ).format(voice=self.voice.key),
                _("Download failed"),
                style=wx.ICON_ERROR,
                parent=gui.mainFrame,
            )
            log.exception(
                f"Failed to download voice.\nException: {result}"
            )

    def download(self):
        self.progress_dialog = wx.ProgressDialog(
            # Translators: title of a progress dialog
            title=_("Downloading voice {voice}").format(
                voice=self.voice.key
            ),
            # Translators: message of a progress dialog
            message=_("Retrieving download information..."),
            parent=gui.mainFrame,
        )
        self.progress_dialog.CenterOnScreen()
        THREAD_POOL_EXECUTOR.submit(self.download_voice_files).add_done_callback(partial(self._done_callback_wrapper, self.done_callback))

    def download_voice_files(self):
        retvals = []
        for file in self.voice.files:
            self.progress_dialog.Update(
                0,
                # Translators: message shown in progress dialog
                _("Downloading file: {file}").format(file=file.name)
            )
            result = self._do_download_file(file, self.temp_download_dir.name, self.update_progress)
            retvals.append(result)

        return retvals

    @classmethod
    def _do_download_file(cls, file, download_dir, progress_callback):
        target_file = os.path.join(download_dir, file.file_path.replace('/', os.sep))
        os.makedirs(os.path.dirname(target_file), exist_ok=True)

        hasher = md5()
        total_size = file.size_in_bytes
        downloaded_til_now = 0

        url = file.download_url
        redirect_limit = 5

        for _redirect in range(redirect_limit):
            with request.yield_response('GET', url) as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location:
                        raise ValueError("Redirect without Location header.")
                    url = urllib.parse.urljoin(url, location)
                    continue

                if response.status != 200:
                    raise RuntimeError(f"Download failed for {file.file_path} (status {response.status})")

                content_type = response.getheader("Content-Type", "").lower()
                if "text/html" in content_type or "xml" in content_type:
                    raise RuntimeError(f"Wrong content-type while downloading {file.file_path}: {content_type}")

                with open(target_file, "wb") as file_buffer:
                    while True:
                        chunk = response.read(4096)
                        if not chunk:
                            break
                        file_buffer.write(chunk)
                        hasher.update(chunk)
                        downloaded_til_now += len(chunk)
                        if total_size > 0:
                            progress = math.floor((downloaded_til_now / total_size) * 100)
                            progress_callback(progress)
                break
        else:
            raise RuntimeError(f"Too many redirects while downloading {file.file_path}")

        return (file, target_file, hasher.hexdigest())

    @staticmethod
    def _done_callback_wrapper(done_callback, future):
        if done_callback is None:
            return
        try:
            result = future.result()
        except Exception as e:
            done_callback(e)
        else:
            done_callback(result)


class PiperRTVoiceDownloader:
    def __init__(self, voice: PiperVoice, success_callback):
        self.voice = voice
        self.success_callback = success_callback
        self.rt_download_url = self.voice.get_rt_variant_download_url()
        self.temp_download_dir = tempfile.TemporaryDirectory()
        self.progress_dialog = None

    def update_progress(self, progress):
        self.progress_dialog.Update(
            progress,
            # Translators: message of a progress dialog
            _("Downloaded: {progress}%").format(progress=progress),
        )

    def done_callback(self, result):
        has_error = isinstance(result, Exception)
        if not has_error:
            self.progress_dialog.Update(
                0,
                # Translators: message shown in the voice download progress dialog
                _("Installing voice")
            )
            try:
                install_voice_from_tar_archive(result, SONATA_VOICES_DIR)
            except:
                log.exception("Failed to extract voice archive", exc_info=True)
                has_error = True
        self.progress_dialog.Hide()
        self.progress_dialog.Destroy()
        del self.progress_dialog

        if not has_error:
            self.success_callback()
            retval = gui.messageBox(
            # Translators: content of a message box
            _(
                "Successfully downloaded fast variant of the voice  {voice}.\n"
                "To use this voice, you need to restart NVDA.\n"
                "Do you want to restart NVDA now?"
            ).format(
                voice=self.voice.key
            ),
            # Translators: title of a message box
            _("Voice downloaded"),
                wx.YES_NO | wx.ICON_WARNING,
                parent=gui.mainFrame,
            )
            if retval == wx.YES:
                core.restart()
        else:
            wx.CallAfter(
                gui.messageBox,
                _(
                    "Cannot download fast variant of the voice {voice}.\nPlease check your connection and try again."
                ).format(voice=self.voice.key),
                _("Download failed"),
                style=wx.ICON_ERROR,
                parent=gui.mainFrame,
            )
            log.exception(
                f"Failed to download voice.\nException: {result}"
            )

    def download(self):
        self.progress_dialog = wx.ProgressDialog(
            # Translators: title of a progress dialog
            title=_("Downloading fast variant of the voice {voice}").format(
                voice=self.voice.key
            ),
            # Translators: message of a progress dialog
            message=_("Retrieving download information..."),
            parent=gui.mainFrame,
        )
        self.progress_dialog.CenterOnScreen()
        THREAD_POOL_EXECUTOR.submit(self.download_voice_archive).add_done_callback(partial(self._done_callback_wrapper, self.done_callback))

    def download_voice_archive(self):
        voice_name = self.rt_download_url.split("/")[-1].strip()
        self.progress_dialog.Update(
            0,
            # Translators: message shown in progress dialog
            _("Downloading file: {file}").format(file=voice_name)
        )
        result = self._do_download_archive(self.rt_download_url, voice_name, self.temp_download_dir.name, self.update_progress)
        return result

    @classmethod
    def _do_download_archive(cls, download_url, voice_name, download_dir, progress_callback):
        target_file = os.path.join(download_dir, voice_name)
        url = download_url
        redirect_limit = 5

        for _redirect in range(redirect_limit):
            with request.yield_response('GET', url) as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location:
                        raise ValueError("Redirect without Location header.")
                    url = urllib.parse.urljoin(url, location)
                    continue

                if response.status != 200:
                    raise RuntimeError(f"Download failed for {voice_name} (status {response.status})")

                content_type = response.getheader("Content-Type", "").lower()
                if "text/html" in content_type or "xml" in content_type:
                    raise RuntimeError(f"Wrong content-type while downloading {voice_name}: {content_type}")

                total_size = int(response.getheader("Content-Length", 0))
                downloaded_til_now = 0
                with open(target_file, "wb") as file_buffer:
                    while True:
                        chunk = response.read(4096)
                        if not chunk:
                            break
                        file_buffer.write(chunk)
                        downloaded_til_now += len(chunk)
                        if total_size > 0:
                            progress = math.floor((downloaded_til_now / total_size) * 100)
                            progress_callback(progress)
                break
        else:
            raise RuntimeError(f"Too many redirects while downloading {voice_name}")

        return target_file

    @staticmethod
    def _done_callback_wrapper(done_callback, future):
        if done_callback is None:
            return
        try:
            result = future.result()
        except Exception as e:
            done_callback(e)
        else:
            done_callback(result)


def install_voice_from_tar_archive(tar_path, voices_dir):
    tar = tarfile.open(tar_path)
    filenames = {f.name: f for f in tar.getmembers()}
    onnx_files = list(filter(
        lambda pth: fnmatch(pth, "*.onnx"),
        filenames
    ))
    config_files = list(filter(
        lambda pth: fnmatch(pth, "*.json"),
        filenames
    ))
    if not (onnx_files and config_files):
        raise FileNotFoundError("Required files not found in archive")
    if len(onnx_files) == 1:
        voice_info = VOICE_INFO_REGEX.match(Path(onnx_files[0]).stem)
    else:
        voice_info = VOICE_INFO_REGEX.match(Path(tar_path).stem[:-4])
    if voice_info is None:
        raise FileNotFoundError("Required files not found in archive")
    info = voice_info.groupdict()
    voice_key = "-".join([
        normalizeLanguage(info["language"]),
        info["name"].replace("-", "_"),
        info["quality"].replace("-", "_"),
    ])
    voice_folder_name = Path(voices_dir).joinpath(voice_key)
    voice_folder_name.mkdir(parents=True, exist_ok=True)
    voice_folder_name = os.fspath(voice_folder_name)
    files_to_extract = [*onnx_files, *config_files]
    if "MODEL_CARD" in filenames:
        files_to_extract.append("MODEL_CARD")
    for file in files_to_extract:
        member = filenames[file]
        filename_only = os.path.basename(member.name)
        target_path = os.path.join(voice_folder_name, filename_only)
        with tar.extractfile(member) as source, open(target_path, "wb") as dest:
            shutil.copyfileobj(source, dest)
    return voice_key


def get_available_voices(force_online=False):
    # Trry an offline cache first
    if not force_online and os.path.exists(PIPER_VOICES_JSON_LOCAL_CACHE):
        try:
            with open(PIPER_VOICES_JSON_LOCAL_CACHE, "rb") as file:
                voices = json.load(file)
        except:
            log.exception("Failed to get voices from local file", exc_info=True)
        else:
            installed_voices = SonataTextToSpeechSystem.load_piper_voices_from_nvda_config_dir()
            installed_voice_keys = {voice.key for voice in installed_voices}
            not_installed = []
            for (key, value) in voices.items():
                std_key, rt_key = SonataTextToSpeechSystem.get_voice_variants(key)
                value["standard_variant_installed"] = std_key in installed_voice_keys
                value["fast_variant_installed"] = rt_key in installed_voice_keys
                if value["standard_variant_installed"] and value["fast_variant_installed"]:
                    continue
                if value["standard_variant_installed"] and not value["has_rt_variant"]:
                    continue
                not_installed.append(value)
            voice_objs = PiperVoice.from_list_of_dicts(not_installed)
            return voice_objs
    std_resp = request.get(PIPER_VOICE_LIST_URL)
    std_resp.raise_for_status()
    std_voices = std_resp.json()
    rt_resp = request.get(RT_VOICE_LIST_URL)
    rt_resp.raise_for_status()
    rt_voice_names = {
        vdata["base"]
        for vdata in rt_resp.json().values()
    }
    voice_list = {}
    for vname, vdata in std_voices.items():
        if vname in rt_voice_names:
            vdata["has_rt_variant"] = True
        else:
            vdata["has_rt_variant"] = False
        voice_list[vname] = vdata
    with open(PIPER_VOICES_JSON_LOCAL_CACHE, "w", encoding="utf-8") as file:
        json.dump(voice_list, file, ensure_ascii=False, indent=2)
    return get_available_voices()

