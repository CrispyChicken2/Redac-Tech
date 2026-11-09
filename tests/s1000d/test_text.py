"""Tests of redactech.s1000d.text (whole-word search and replace, no regular expressions)."""

from __future__ import annotations

import pytest

from redactech.s1000d import text


@pytest.mark.parametrize(
    "value,expected",
    [
        ("LRU1010", [(0, 7)]),
        ("a LRU1010, b", [(2, 9)]),
        ("LRU10100", []),
        ("XLRU1010", []),
        ("LRU1010-A", []),
        ("LRU1010 and LRU1010.", [(0, 7), (12, 19)]),
        ("LRU10100 LRU1010", [(9, 16)]),
        ("", []),
    ],
)
def test_token_spans(value: str, expected: list[tuple[int, int]]):
    assert text.token_spans(value, "LRU1010") == expected


def test_empty_token_matches_nothing():
    assert text.token_spans("anything", "") == []
    assert text.substring_spans("anything", "") == []
    assert text.contains_token("anything", "") is False


def test_contains_token():
    assert text.contains_token("see (LRU1010)", "LRU1010") is True
    assert text.contains_token("see LRU10100", "LRU1010") is False


@pytest.mark.parametrize(
    "occurrence,expected,count",
    [
        (None, "Z and LRU10100 and Z", 2),
        (1, "Z and LRU10100 and LRU1010", 1),
        (2, "LRU1010 and LRU10100 and Z", 1),
        (-1, "LRU1010 and LRU10100 and Z", 1),
        (-2, "Z and LRU10100 and LRU1010", 1),
        (3, "LRU1010 and LRU10100 and LRU1010", 0),
        (0, "LRU1010 and LRU10100 and LRU1010", 0),
    ],
)
def test_replace_token(occurrence: int | None, expected: str, count: int):
    source = "LRU1010 and LRU10100 and LRU1010"
    assert text.replace_token(source, "LRU1010", "Z", occurrence) == (expected, count)


def test_replace_token_with_a_longer_replacement_keeps_offsets_right():
    assert text.replace_token("A and A and A", "A", "LONGER") == (
        "LONGER and LONGER and LONGER",
        3,
    )


def test_substring_spans_do_not_overlap():
    assert text.substring_spans("aaaa", "aa") == [(0, 2), (2, 4)]
    assert text.substring_spans("a-b-c", "-") == [(1, 2), (3, 4)]
