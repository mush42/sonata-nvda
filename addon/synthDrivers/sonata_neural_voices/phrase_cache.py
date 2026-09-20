# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

"""
Phrase cache for Sonata Neural Voices.

Caches synthesized PCM audio for short, frequently-used phrases to eliminate
gRPC round-trip latency for common UI strings (e.g. "OK", "Cancel", etc.).
"""

import threading
from collections import OrderedDict


# Maximum number of cache entries
_MAX_CACHE_SIZE = 100
# Maximum size in bytes per cached phrase (10 KB)
_MAX_ENTRY_SIZE_BYTES = 10 * 1024
# Common NVDA UI phrases to pre-warm the cache when a voice is loaded
COMMON_PHRASES = [
    "OK",
    "Cancel",
    "Yes",
    "No",
    "Close",
    "Error",
    "Done",
    "Apply",
    "Help",
    "Back",
    "Next",
    "Finish",
]


class PhraseCache:
    """
    Thread-safe LRU cache for synthesized PCM audio chunks.

    Keys are tuples of (text, voice_key, rate, volume, pitch).
    Values are lists of PCM byte-string chunks as returned by the gRPC synthesizer.
    """

    def __init__(self, max_size=_MAX_CACHE_SIZE, max_entry_bytes=_MAX_ENTRY_SIZE_BYTES):
        self._max_size = max_size
        self._max_entry_bytes = max_entry_bytes
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, text, voice_key, rate, volume, pitch):
        # Normalise floats to 1-decimal precision so near-identical rates match
        return (
            text.strip(),
            voice_key,
            round(rate or 50, 1),
            round(volume or 100, 1),
            round(pitch or 50, 1),
        )

    def get(self, text, voice_key, rate, volume, pitch):
        """Return cached PCM chunks or None on miss."""
        key = self._make_key(text, voice_key, rate, volume, pitch)
        with self._lock:
            if key in self._cache:
                # Move to end (most-recently-used)
                self._cache.move_to_end(key)
                self._hits += 1
                return list(self._cache[key])  # return a copy
            self._misses += 1
            return None

    def put(self, text, voice_key, rate, volume, pitch, pcm_chunks):
        """Store PCM chunks in the cache if they are small enough."""
        total_bytes = sum(len(c) for c in pcm_chunks)
        if total_bytes > self._max_entry_bytes:
            # Don't cache long phrases — they are unlikely to repeat exactly
            return
        key = self._make_key(text, voice_key, rate, volume, pitch)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = list(pcm_chunks)
                return
            self._cache[key] = list(pcm_chunks)
            if len(self._cache) > self._max_size:
                # Evict least-recently-used entry
                self._cache.popitem(last=False)

    def invalidate_voice(self, voice_key):
        """Remove all entries for a specific voice (e.g. after voice change)."""
        with self._lock:
            to_delete = [k for k in self._cache if k[1] == voice_key]
            for k in to_delete:
                del self._cache[k]

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


# Module-level singleton shared by the synth driver
phrase_cache = PhraseCache()
