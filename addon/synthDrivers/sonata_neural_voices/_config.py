# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

import config
from io import StringIO
from configobj import ConfigObj

_configSpec = """[voices]
[[__many__]]
variant = string(default=None)
speaker = string(default=None)
noise_scale = integer(default=50, min=0, max=100)
length_scale = integer(default=50, min=0, max=100)
noise_w = integer(default=50, min=0, max=100)

[lang]
[[__many__]]
voice = string(default=None)
"""


class SonataConfigManager:
    """Config manager for Sonata."""

    def __init__(self):
        if not config.conf["speech"].isSet("sonata_neural_voices"):
            config.conf["speech"]["sonata_neural_voices"] = {}
        confspec = ConfigObj(StringIO(_configSpec), list_values=False, encoding="UTF-8")
        config.conf["speech"]["sonata_neural_voices"].spec.update(confspec)

    def __contains__(self, key):
        return key in config.conf["speech"]["sonata_neural_voices"]

    def __getitem__(self, key):
        return config.conf["speech"]["sonata_neural_voices"][key]

    def __setitem__(self, key, value):
        config.conf["speech"]["sonata_neural_voices"][key] = value

    def setdefault(self, key, value):
        if key not in config.conf["speech"]["sonata_neural_voices"]:
            config.conf["speech"]["sonata_neural_voices"][key] = value
        return config.conf["speech"]["sonata_neural_voices"][key]


SonataConfig = SonataConfigManager()
