# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

"""
Application-specific voice profile manager for Sonata Neural Voices.

Stores per-application voice settings (voice, variant, rate, volume, pitch,
speaker) in the NVDA configuration file.  When the focused application
changes, the GlobalPlugin calls AppProfileManager.apply_for_exe() to
automatically switch to the appropriate profile.
"""

import os
import config
from io import StringIO
from configobj import ConfigObj
from logHandler import log


_PROFILE_CONFIGSPEC = """
[app_profiles]
[[__many__]]
voice    = string(default=None)
variant  = string(default=None)
speaker  = string(default=None)
rate     = integer(default=None, min=0, max=100)
volume   = integer(default=None, min=0, max=100)
pitch    = integer(default=None, min=0, max=100)
"""


class AppProfileManager:
    """
    Manages per-application Sonata voice profiles.

    Profiles are stored under:
      config.conf["speech"]["sonata_neural_voices"]["app_profiles"][<exe_name>]
    """

    def __init__(self):
        if not config.conf["speech"].isSet("sonata_neural_voices"):
            config.conf["speech"]["sonata_neural_voices"] = {}
        spec = ConfigObj(StringIO(_PROFILE_CONFIGSPEC), list_values=False, encoding="UTF-8")
        config.conf["speech"]["sonata_neural_voices"].spec.update(spec)

    def _profiles_section(self):
        conf = config.conf["speech"]["sonata_neural_voices"]
        if "app_profiles" not in conf:
            conf["app_profiles"] = {}
        return conf["app_profiles"]

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    def get_profile(self, exe_name: str) -> dict:
        """Return the profile dict for an exe, or {} if none configured."""
        exe = exe_name.lower()
        section = self._profiles_section()
        if exe in section:
            return dict(section[exe])
        return {}

    def set_profile(self, exe_name: str, **kwargs):
        """
        Save a profile for the given exe.

        Accepted kwargs: voice, variant, speaker, rate, volume, pitch.
        Pass None to clear a field (means "inherit global setting").
        """
        exe = exe_name.lower()
        section = self._profiles_section()
        if exe not in section:
            section[exe] = {}
        for key, value in kwargs.items():
            if value is None:
                # Remove the key so the default (None) is used
                section[exe].pop(key, None)
            else:
                section[exe][key] = value

    def delete_profile(self, exe_name: str):
        """Delete the profile for the given exe."""
        exe = exe_name.lower()
        section = self._profiles_section()
        if exe in section:
            del section[exe]

    def list_profiles(self) -> list:
        """Return list of (exe_name, profile_dict) tuples, sorted by exe name."""
        section = self._profiles_section()
        return sorted(
            [(name, dict(data)) for name, data in section.items()],
            key=lambda x: x[0],
        )

    # ------------------------------------------------------------------
    # Runtime application
    # ------------------------------------------------------------------

    def apply_for_exe(self, exe_name: str, synth_driver) -> bool:
        """
        Apply the saved profile for exe_name to the given synth driver.

        Returns True if a profile was found and applied, False otherwise.
        """
        profile = self.get_profile(exe_name)
        if not profile:
            return False

        try:
            if profile.get("voice"):
                # Only switch if different from current voice
                if synth_driver.voice != profile["voice"]:
                    synth_driver.voice = profile["voice"]
            if profile.get("variant"):
                synth_driver.variant = profile["variant"]
            if profile.get("speaker"):
                synth_driver.speaker = profile["speaker"]
            if profile.get("rate") is not None:
                synth_driver.rate = int(profile["rate"])
            if profile.get("volume") is not None:
                synth_driver.volume = int(profile["volume"])
            if profile.get("pitch") is not None:
                synth_driver.pitch = int(profile["pitch"])
            log.debug(f"Sonata: applied app profile for '{exe_name}'")
            return True
        except Exception:
            log.exception(f"Sonata: failed to apply app profile for '{exe_name}'")
            return False


# Singleton
app_profile_manager = AppProfileManager()
