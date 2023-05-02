# Piper neural voices for NVDA

This add-on implements a speech synthesizer driver for NVDA using [Piper](https://github.com/rhasspy/piper).

[Piper](https://github.com/rhasspy/piper) is a fast, local neural text to speech system that sounds great and is optimized for low-end devices such as the Raspberry Pi.

You can listen to voice samples here: [Piper voice samples](https://rhasspy.github.io/piper-samples/).

# Installation

## Installing the add-on

You can find the add-on package under the assets section of the [release page](https://github.com/mush42/piper-nvda/releases/latest)

## Adding voices

The add-on is just  a driver, it comes with no voices by default. You need to download and install the voices you want manually.

Upon installing the add-on and restarting NVDA, the add-on will ask you to download and install at least one voice. And it will give you the option to open the voices download web page.

You can also open the voices download web page from within `Piper` category in NVDA settings.

Each voice is available as a `.tar.gz` file, which is an archive format similar to `.zip` and `.rar` archives. The archive contains the voice model and the voice configurations.

Note that we recommend choosing the `low` or `x-low` quality voices for your target language(s), because they generally provide better performance.

After downloading a voice, go to NVDA settings, and choose `Piper` category, and then click the button labled `Install from file`. Choose the file you downloaded, wait for the voice to install, and restart NVDA to refresh the voices list.

## A note on voice quality

The currently available voices are trained using freely available TTS datasets, which are generally of low quality (mostly public domain audio books or research quality recordings).

Additionally, these datasets are not comprehensive, hence some voices may exhibit incorrect or weird pronunciation. Both issues could be resolved by using better datasets for training.

Luckily, the `Piper` developer and some developers from the blind and vision-impaired community are working on training better voices.

# A note on add-on's performance

The current release is a technical preview. Soon enough the add-on will be rewritten in `Rust`, a programming language that provides better performance than `Python`.

# License

Copyright(c) 2023, Musharraf Omer. This software is licensed under The GNU GENERAL PUBLIC LICENSE Version 2 (GPL v2).
