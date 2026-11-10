"""Tests of redactech.report.html: self-contained, escaped, no script, no external URL."""

from __future__ import annotations

import re

from redactech.report import build, html


def page(state, index, write_result) -> str:
    return html.render_html(build.build_report(state, index, write_result))


def test_the_page_is_self_contained(state, index, write_result):
    text = page(state, index, write_result)
    assert text.startswith("<!DOCTYPE html>") and "<style>" in text
    lowered = text.lower()
    assert "<script" not in lowered and "http" not in lowered and "://" not in text
    assert "<link" not in lowered and "<img" not in lowered and "<iframe" not in lowered
    assert " href=" not in lowered and " src=" not in lowered and "@import" not in lowered
    assert "javascript:" not in lowered and " onclick" not in lowered


def test_every_value_is_escaped(state, index, write_result):
    state.proposals[1] = state.proposals[1].model_copy(
        update={"reviewer_comment": '<script>alert("x")</script> & <i>'}
    )
    state.workspace = "C:/work/<ws>&.toml"
    text = page(state, index, write_result)
    assert "<script>" not in text and "<i>" not in text and "<ws>" not in text
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &lt;i&gt;" in text
    assert "C:/work/&lt;ws&gt;&amp;.toml" in text
    assert "No &lt;note&gt; here." in text and "forbidden &lt;value&gt;" in text


def test_xml_excerpts_are_shown_as_text(state, index, write_result):
    text = page(state, index, write_result)
    assert "&lt;para&gt;old&lt;/para&gt;" in text and "&lt;para&gt;typed&lt;/para&gt;" in text
    assert "<para>" not in text


def test_the_sections_are_there_in_order(state, index, write_result):
    text = page(state, index, write_result)
    titles = re.findall(r"<h2>(.*?)</h2>", text)
    assert titles == [
        "Summary", "Versioning", "Changes per document",
        "Pre-existing and introduced issues", "Blocked requests",
        "Illustrations to check", "Pending questions",
    ]


def test_the_page_tells_the_story_of_the_run(state, index, write_result):
    text = page(state, index, write_result)
    assert "20250307-140509-ab12" in text
    assert "DMC-A-520A-A_001-00_EN-US.XML &rarr; DMC-A-520A-A_001-01_EN-US.XML" in text
    assert "Mode: <b>in_work</b> (suggested: new_issue)" in text
    assert "op-0001: part -&gt; in_work" in text  # the reasons, escaped
    assert "R-1: No &lt;note&gt; here." in text and "conflicts with business rule R-1" in text
    assert "reason of z3" in text and "Ask the customer" in text
    assert "read-only document (upf)" in text
    assert 'class="introduced"' in text and 'class="pre_existing"' in text


def test_empty_sections_say_so(state, index):
    state.proposals = []
    state.operations = []
    state.version_policy = None
    text = html.render_html(build.build_report(state, index, None))
    assert "no versioning policy chosen" in text and "no document" in text
    assert text.count('class="none"') >= 5


def test_the_values_of_any_type_are_escaped_by_e():
    assert html.e(None) == "" and html.e(3) == "3"
    assert html.e('<a href="x">&</a>') == "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"
