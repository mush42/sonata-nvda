# Sonata neural voices for NVDA

This add-on implements a speech synthesizer driver for NVDA using neural TTS models. It supports [Piper](https://github.com/rhasspy/piper).

[Piper](https://github.com/rhasspy/piper) is a fast, local neural text to speech system that sounds great and is optimized for low-end devices such as the Raspberry Pi.

You can listen to Piper's voice samples here: [Piper voice samples](https://rhasspy.github.io/piper-samples/).

This add-on uses [Sonata: A cross-platform Rust engine for neural TTS models](https://github.com/mush42/sonata) which is being developed by Musharraf Omer.


# Installation

## Downloading the add-on

You can find the add-on package under the assets section of the [release page](https://github.com/mush42/sonata-nvda/releases/latest)

## Adding voices

The add-on is just  a driver, it comes with no voices by default. You need to download and install the voices you want from the voice manager.

Upon installing the add-on and restarting NVDA, the add-on will ask you to download and install at least one voice, and it will give you the option to open the voice manager.

You can also open the voice manager from NVDA's main menu.

Note that we recommend choosing the `low` or `medium` quality voices for your target language(s), because they generally provide better responsiveness. For additional responsiveness, you can choose to download the `fast` variant of a voice at a cost of slightly lower speech quality.

You can also install voices from local archives. After obtaining the voice's file, open the voice manager, in the installed tab, click the button labeled `Install from local file`. Choose the voice file, wait for the voice to install, and restart NVDA to refresh the voices list.

## A note on voice quality

The currently available voices are trained using freely available TTS datasets, which are generally of low quality (mostly public domain audio books or research quality recordings).

Additionally, these datasets are not comprehensive, hence some voices may exhibit incorrect or weird pronunciation. Both issues could be resolved by using better datasets for training.

Luckily, the `Piper` developer and some developers from the blind and vision-impaired community are working on training better voices.

# License

Copyright(c) 2024, Musharraf Omer. This software is licensed under The GNU GENERAL PUBLIC LICENSE Version 2 (GPL v2).
