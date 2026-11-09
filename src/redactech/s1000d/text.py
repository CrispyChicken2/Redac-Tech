"""Whole-word search and replace on plain text (string operations, no regular expressions).

A *token* (for instance a part number) matches only as a whole word: letters, digits, ``-`` and
``_`` are word characters, any other character (space, punctuation, brackets...) is a boundary.
So ``LRU1010`` is found in ``see LRU1010.`` but not in ``LRU10100`` or ``LRU1010-A``.
"""

from __future__ import annotations

WORD_CHARS = "-_"


def _is_word_char(char: str) -> bool:
    return char.isalnum() or char in WORD_CHARS


def token_spans(text: str, token: str) -> list[tuple[int, int]]:
    """``(start, end)`` of every whole-word occurrence of ``token`` in ``text``."""
    if not token:
        return []
    spans = []
    start = text.find(token)
    while start != -1:
        end = start + len(token)
        before = text[start - 1] if start > 0 else " "
        after = text[end] if end < len(text) else " "
        if not _is_word_char(before) and not _is_word_char(after):
            spans.append((start, end))
        start = text.find(token, start + 1)
    return spans


def contains_token(text: str, token: str) -> bool:
    """Is ``token`` in ``text`` as a whole word?"""
    return bool(token_spans(text, token))


def replace_token(
    text: str, old: str, new: str, occurrence: int | None = None
) -> tuple[str, int]:
    """Replace whole-word occurrences of ``old`` by ``new``; return ``(text, count)``.

    ``occurrence`` selects one occurrence: 1 is the first, -1 the last; ``None`` replaces all.
    """
    spans = token_spans(text, old)
    if occurrence is not None:
        if not spans or not (1 <= abs(occurrence) <= len(spans)):
            return text, 0
        spans = [spans[occurrence - 1] if occurrence > 0 else spans[occurrence]]
    for start, end in reversed(spans):
        text = text[:start] + new + text[end:]
    return text, len(spans)


def substring_spans(text: str, token: str) -> list[tuple[int, int]]:
    """``(start, end)`` of every non-overlapping plain-substring occurrence of ``token``."""
    if not token:
        return []
    spans = []
    start = text.find(token)
    while start != -1:
        spans.append((start, start + len(token)))
        start = text.find(token, start + len(token))
    return spans
