# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

"""
Audio post-processing utilities for Sonata Neural Voices.

Provides:
  - normalize_audio()    : RMS-based volume normalisation with peak limiter
  - apply_panning()      : Convert mono PCM to stereo with L/R panning
  - apply_night_mode()   : Soften audio for quiet/night-time listening
"""

import array
import math


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INT16_MAX = 32767
_INT16_MIN = -32768
# Target RMS level for normalisation (0.0 – 1.0 relative to full-scale)
_TARGET_RMS = 0.20
# Headroom factor: keep peak below this fraction of full-scale after normalise
_PEAK_CEILING = 0.95


# ---------------------------------------------------------------------------
# Helper: read/write 16-bit signed PCM
# ---------------------------------------------------------------------------

def _pcm_to_array(pcm_bytes: bytes) -> array.array:
    """Convert raw PCM bytes to a signed 16-bit array."""
    a = array.array("h")
    a.frombytes(pcm_bytes)
    return a


def _array_to_pcm(a: array.array) -> bytes:
    """Convert a signed 16-bit array back to raw PCM bytes."""
    return a.tobytes()


# ---------------------------------------------------------------------------
# Feature 3: Volume normalisation
# ---------------------------------------------------------------------------

def normalize_audio(pcm_bytes: bytes) -> bytes:
    """
    Normalise the RMS level of 16-bit mono PCM audio.

    Applies a single gain factor so that the RMS of the output reaches
    _TARGET_RMS, then clamps peaks to _PEAK_CEILING to prevent distortion.
    Short or silent clips are returned unchanged.
    """
    if len(pcm_bytes) < 2:
        return pcm_bytes

    samples = _pcm_to_array(pcm_bytes)
    n = len(samples)
    if n == 0:
        return pcm_bytes

    # Compute RMS
    sum_sq = sum(s * s for s in samples)
    rms = math.sqrt(sum_sq / n) / _INT16_MAX  # normalised to [0, 1]

    if rms < 1e-6:
        # Silence — nothing to do
        return pcm_bytes

    gain = _TARGET_RMS / rms
    # Limit gain to avoid over-amplifying very quiet clips unreasonably
    gain = min(gain, 4.0)

    # Apply gain with peak ceiling limiting
    ceiling = int(_PEAK_CEILING * _INT16_MAX)
    result = array.array("h", (
        max(_INT16_MIN, min(ceiling, int(s * gain)))
        for s in samples
    ))
    return _array_to_pcm(result)


# ---------------------------------------------------------------------------
# Feature 5: Spatial audio (stereo panning)
# ---------------------------------------------------------------------------

def mono_to_stereo_panned(pcm_bytes: bytes, pan: float) -> bytes:
    """
    Convert 16-bit mono PCM to 16-bit stereo PCM with equal-power panning.

    pan: float in [-1.0, 1.0]
         -1.0 = hard left, 0.0 = centre, +1.0 = hard right

    Returns bytes with interleaved L/R samples (2× longer than input).
    """
    if len(pcm_bytes) < 2:
        # Return silence in stereo
        return pcm_bytes * 2

    # Clamp pan
    pan = max(-1.0, min(1.0, pan))

    # Equal-power panning law
    angle = (pan + 1.0) / 2.0 * (math.pi / 2.0)  # 0 → π/2
    left_gain = math.cos(angle)
    right_gain = math.sin(angle)

    mono = _pcm_to_array(pcm_bytes)
    stereo = array.array("h")
    for s in mono:
        l = max(_INT16_MIN, min(_INT16_MAX, int(s * left_gain)))
        r = max(_INT16_MIN, min(_INT16_MAX, int(s * right_gain)))
        stereo.append(l)
        stereo.append(r)

    return _array_to_pcm(stereo)


# ---------------------------------------------------------------------------
# Feature 4: Night mode audio softening
# ---------------------------------------------------------------------------

# Night mode parameters
_NIGHT_MODE_GAIN = 0.55          # Reduce overall volume to ~55 %
_NIGHT_MODE_HIGHFREQ_DAMP = 0.4  # Simple 1-tap high-frequency damping


def apply_night_mode(pcm_bytes: bytes) -> bytes:
    """
    Apply night-mode softening to 16-bit mono PCM audio.

    Reduces volume and applies a single-pole low-pass filter to remove
    harsh high-frequency components, making the voice sound softer and
    more soothing for night-time / earphone use.
    """
    if len(pcm_bytes) < 2:
        return pcm_bytes

    samples = _pcm_to_array(pcm_bytes)
    result = array.array("h")
    prev = 0
    alpha = _NIGHT_MODE_HIGHFREQ_DAMP  # low-pass coefficient

    for s in samples:
        # 1-pole IIR low-pass: y[n] = alpha*x[n] + (1-alpha)*y[n-1]
        filtered = int(alpha * s + (1.0 - alpha) * prev)
        prev = filtered
        # Apply volume reduction
        out = int(filtered * _NIGHT_MODE_GAIN)
        result.append(max(_INT16_MIN, min(_INT16_MAX, out)))

    return _array_to_pcm(result)
