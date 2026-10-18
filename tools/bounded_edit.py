#!/usr/bin/env python3
"""The bounded-edit predicate shared by the approval and final-review gates.

A human gate binds exact bytes. A small, mechanical fix made afterwards -- a
name, a figure, a typo -- does not need the question asked again, so the gates
carry across it. "Small" is decided here, deterministically, from a word-level
diff between the bytes the human saw and the bytes on disk: an edit is bounded
when at most ``LIMIT`` words change (inserted plus deleted) and no Markdown
heading line is added, removed or edited.

The module is pure: no I/O, no clock, same two texts -- same answer.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

LIMIT = 40


def word_diff(old: str, new: str) -> int:
    """Count inserted plus deleted whitespace-separated words from ``old`` to ``new``."""
    old_words, new_words = old.split(), new.split()
    matcher = SequenceMatcher(None, old_words, new_words, autojunk=False)
    return sum(
        (i2 - i1) + (j2 - j1)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    )


_SETEXT_UNDERLINE = re.compile(r"^\s*(?:={3,}|-{3,})\s*$")


def _headings(text: str) -> list[str]:
    """ATX (``#``) lines plus setext headings: a text line over ``===`` or ``---``.

    Setext matches ``rubric_checks``, which treats the same shape as a heading.
    A setext entry keeps its underline character, so a level change counts too.
    """
    lines = text.splitlines()
    found: list[str] = []
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            found.append(line.strip())
        elif index and _SETEXT_UNDERLINE.match(line) and lines[index - 1].strip():
            found.append(f"{lines[index - 1].strip()}\n{line.strip()[0]}")
    return found


def headings_changed(old: str, new: str) -> bool:
    """True when the ordered Markdown headings (ATX or setext) differ between the two texts."""
    return _headings(old) != _headings(new)


def bounded(old: str, new: str, limit: int = LIMIT) -> tuple[bool, int]:
    """Return ``(is_bounded, words_changed)`` for an edit from ``old`` to ``new``."""
    words = word_diff(old, new)
    return words <= limit and not headings_changed(old, new), words
