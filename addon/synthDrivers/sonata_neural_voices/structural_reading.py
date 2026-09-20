# coding: utf-8

# Copyright (c) 2023 Musharraf Omer
# This file is covered by the GNU General Public License.

"""
Structural reading: alternate speakers for bracketed/quoted text segments.

When a multi-speaker voice is active and structural reading is enabled,
text is split into segments.  Parenthetical or quoted content is assigned
an alternate speaker index so it sounds distinct from the main narrative.
"""

import re
from dataclasses import dataclass
from typing import List, Optional


# Patterns that mark "aside" regions — to be read in an alternate speaker
_ASIDE_PATTERNS = [
    # Parentheses: (text)
    re.compile(r"\(([^)]{1,200})\)", re.DOTALL),
    # Square brackets: [text]
    re.compile(r"\[([^\]]{1,200})\]", re.DOTALL),
    # Double-quoted: "text"
    re.compile(r'"([^"]{1,200})"', re.DOTALL),
    # Japanese corner brackets: 「text」
    re.compile(r"「([^」]{1,200})」", re.DOTALL),
]


@dataclass
class SpeechSegment:
    """A contiguous segment of text with an optional speaker override."""
    text: str
    # None means "use the current default speaker"
    speaker_index: Optional[int] = None


def split_into_segments(text: str) -> List[SpeechSegment]:
    """
    Split *text* into a list of SpeechSegments.

    Main body segments have speaker_index=None (default speaker).
    Aside/quoted segments have speaker_index=1 (alternate speaker).

    The function merges overlapping match regions and preserves the
    entire original text character-for-character.
    """
    if not text:
        return []

    # Collect all aside regions as (start, end) character spans
    aside_spans = []
    for pattern in _ASIDE_PATTERNS:
        for m in pattern.finditer(text):
            aside_spans.append((m.start(), m.end()))

    if not aside_spans:
        return [SpeechSegment(text=text)]

    # Merge overlapping/adjacent spans
    aside_spans.sort()
    merged = [aside_spans[0]]
    for start, end in aside_spans[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Build segments by walking the text
    segments: List[SpeechSegment] = []
    cursor = 0
    for aside_start, aside_end in merged:
        if cursor < aside_start:
            main_text = text[cursor:aside_start]
            if main_text.strip():
                segments.append(SpeechSegment(text=main_text, speaker_index=None))
        aside_text = text[aside_start:aside_end]
        if aside_text.strip():
            segments.append(SpeechSegment(text=aside_text, speaker_index=1))
        cursor = aside_end

    if cursor < len(text):
        tail = text[cursor:]
        if tail.strip():
            segments.append(SpeechSegment(text=tail, speaker_index=None))

    return segments if segments else [SpeechSegment(text=text)]
