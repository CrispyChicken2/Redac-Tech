"""Tests of redactech.render.xml_view: escaped, numbered, highlighted XML."""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from redactech.render.xml_view import render_xml
from redactech.s1000d import io as xio

CODE = "AAA-D00-00-00-00AA"
MARKED = f"DMC-RTPROTO-{CODE}-520B-A_007-00_EN-US.XML"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
FIGURE = f"DMC-RTPROTO-{CODE}-041A-A_001-00_EN-US.XML"


def classes(html: str) -> list[str]:
    return re.findall(r'<div class="(rt-line[^"]*)">', html)


def test_everything_is_escaped_and_nothing_is_executable():
    source = '<a x="&lt;1&gt; &quot;q&quot;"><b>1 &lt; 2 &amp; <![CDATA[<z>]]></b></a>'
    html = render_xml(etree.fromstring(source))
    assert "&lt;b&gt;1 &lt; 2 &amp; &lt;z&gt;&lt;/b&gt;" in html
    assert "x=&quot;&lt;1&gt; &quot;q&quot;&quot;" in html
    assert "<b>" not in html and "<a " not in html and "<script" not in html.lower()


def test_lines_are_numbered_and_indented():
    html = render_xml(etree.fromstring("<a><b>text</b><c/></a>"))
    numbers = re.findall(r'<span class="rt-ln">(\d+)</span>', html)
    assert numbers == ["1", "2", "3", "4"]
    assert "<code>&lt;a&gt;</code>" in html
    assert "<code>  &lt;b&gt;text&lt;/b&gt;</code>" in html
    assert "<code>  &lt;c/&gt;</code>" in html and "<code>&lt;/a&gt;</code>" in html


def test_mixed_content_goes_on_separate_lines():
    html = render_xml(etree.fromstring("<p>One <i>two</i> three</p>"))
    assert html.count('class="rt-line"') == 5
    assert "<code>  One</code>" in html and "<code>  three</code>" in html


def test_marked_elements_are_highlighted_by_change_type(fixtures_dir: Path):
    html = render_xml(xio.load(fixtures_dir / MARKED))
    found = classes(html)
    # each marked step is three lines: start tag, paragraph, end tag
    assert found.count("rt-line rt-add") == 3
    assert found.count("rt-line rt-modify") == 3
    assert found.count("rt-line rt-delete") == 3
    assert "rt-delete" in html and "Step marked as deleted but still present." in html


def test_an_unmarked_document_has_no_highlight(fixtures_dir: Path):
    found = classes(render_xml(xio.load(fixtures_dir / PROCED)))
    assert found and set(found) == {"rt-line"}


def test_ids_can_be_highlighted(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / MARKED)
    found = classes(render_xml(doc, highlight_ids=["stp-0001", "stp-0002"]))
    assert found.count("rt-line rt-hl") == 3  # stp-0001, unmarked
    assert found.count("rt-line rt-add rt-hl") == 3  # stp-0002 keeps its change class
    assert classes(render_xml(doc, highlight_ids=())).count("rt-line rt-hl") == 0


def test_namespaces_are_shown_once_on_the_root(fixtures_dir: Path):
    html = render_xml(xio.load(fixtures_dir / PROCED))
    assert html.count("xmlns:xlink=") == 1
    assert "xmlns:xlink=&quot;http://www.w3.org/1999/xlink&quot;" in html
    assert "xsi:noNamespaceSchemaLocation=&quot;" in html


def test_comments_and_processing_instructions_are_shown(fixtures_dir: Path):
    html = render_xml(xio.load(fixtures_dir / FIGURE))
    assert "&lt;!-- editor comment kept by round trips --&gt;" in html
    assert "&lt;?Pub Caret?&gt;" in html


def test_a_document_a_tree_and_an_element_give_the_same_view(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / PROCED)
    assert render_xml(doc) == render_xml(doc.tree) == render_xml(doc.tree.getroot())


def test_rendering_does_not_change_the_document(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / MARKED)
    before = xio.canonical(doc)
    render_xml(doc, highlight_ids=["stp-0001"])
    assert xio.canonical(doc) == before
