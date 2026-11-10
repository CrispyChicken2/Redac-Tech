"""Tests of redactech.render.side_by_side: two panes, a proposal's before / after, a page."""

from __future__ import annotations

from pathlib import Path

import pytest

from redactech.models import Proposal, SourceRef
from redactech.render import side_by_side as sbs
from redactech.s1000d import io as xio

CODE = "AAA-D00-00-00-00AA"
MARKED = f"DMC-RTPROTO-{CODE}-520B-A_007-00_EN-US.XML"
REF = SourceRef(source_id="s", doc_key="d")
STEP = '<proceduralStep id="s1"><para>Do it.</para></proceduralStep>'


def proposal(before: str, after: str, **kwargs) -> Proposal:
    values = {
        "id": "p1",
        "operation_id": "op-0001",
        "zone_id": "z1",
        "ref": REF,
        "before_xml": before,
        "after_xml": after,
        "change_type": "modify",
    }
    return Proposal(**{**values, **kwargs})


def panes(html: str) -> tuple[str, str]:
    """The text of the left and of the right pane."""
    parts = html.split('<div class="rt-pane">')
    return parts[1], parts[2]


def test_two_panes_with_escaped_titles_and_trusted_fragments():
    html = sbs.render_side_by_side("<p>left</p>", "<p>right</p>", ("A <b>", "B & C"))
    assert html.startswith('<div class="rt-side">') and html.count('class="rt-pane"') == 2
    left, right = panes(html)
    assert "A &lt;b&gt;" in left and "<p>left</p>" in left and "right" not in left
    assert "B &amp; C" in right and "<p>right</p>" in right
    assert "<b>" not in html


def test_the_xml_view_of_a_proposal_shows_each_side():
    html = sbs.render_before_after(proposal("<para>old</para>", "<para>new</para>"), "xml")
    left, right = panes(html)
    assert "Before" in left and "&lt;para&gt;old&lt;/para&gt;" in left and "new" not in left
    assert "After" in right and "&lt;para&gt;new&lt;/para&gt;" in right and "old" not in right
    assert "rt-xml" in left and "rt-xml" in right


def test_the_published_view_wraps_the_excerpt_in_a_minimal_module():
    changed = STEP.replace("Do it.", "Do that.")
    html = sbs.render_before_after(proposal(STEP, changed), "published")
    left, right = panes(html)
    assert "Do it." in left and "Do that." in right and "Do that." not in left
    assert 'class="rt-step"' in left and 'class="rt-doc"' in right
    assert "rt-xml" not in html


def test_change_marks_in_an_excerpt_show_in_the_published_view():
    marked = (
        '<proceduralStep id="s1" changeMark="1" changeType="add"><para>New</para>'
        "</proceduralStep>"
    )
    html = sbs.render_before_after(proposal("", marked, change_type="add"), "published")
    left, right = panes(html)
    assert "(nothing)" in left and 'class="rt-step rt-add"' in right


def test_an_empty_side_is_a_notice_in_both_views():
    for view in ("xml", "published"):
        left, _ = panes(sbs.render_before_after(proposal("", "<para>x</para>"), view))
        assert '<p class="rt-empty">(nothing)</p>' in left


def test_the_edited_text_is_what_the_after_side_shows():
    edited = proposal(
        "<para>old</para>",
        "<para>proposed</para>",
        status="edited",
        edited_xml="<para>typed</para>",
    )
    _, right = panes(sbs.render_before_after(edited, "xml"))
    assert "typed" in right and "proposed" not in right


def test_an_excerpt_that_is_not_xml_is_shown_as_text_with_a_notice():
    html = sbs.render_before_after(proposal("<para>old</para>", "<para>unclosed"), "xml")
    _, right = panes(html)
    assert "Not well-formed XML" in right and "&lt;para&gt;unclosed" in right
    assert "<para>" not in html


def test_an_unknown_view_is_refused():
    with pytest.raises(ValueError, match="unknown view"):
        sbs.render_before_after(proposal("", ""), "pdf")


def test_a_full_page_in_each_view(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / MARKED)
    both = sbs.render_page(doc, "both", True, title="DM <1>")
    assert both.startswith("<!DOCTYPE html>") and "<title>DM &lt;1&gt;</title>" in both
    assert 'class="rt-side"' in both and "Published" in both
    assert 'class="rt-xml"' in both and 'class="rt-doc"' in both
    only_xml = sbs.render_page(doc, "xml")
    assert 'class="rt-xml"' in only_xml and 'class="rt-side"' not in only_xml
    assert 'class="rt-doc"' not in only_xml
    only_pub = sbs.render_page(doc, "published")
    assert 'class="rt-doc"' in only_pub and 'class="rt-xml"' not in only_pub
    for page in (both, only_xml, only_pub):
        assert "<script" not in page.lower() and "<style>" in page and "<img" not in page


def test_hiding_deleted_elements_applies_to_the_published_pane(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / MARKED)
    deleted = "Step marked as deleted but still present."
    shown = sbs.render_page(doc, "published", show_deleted=True)
    hidden = sbs.render_page(doc, "published", show_deleted=False)
    assert deleted in shown and deleted not in hidden
    # the XML pane always shows everything
    assert deleted in sbs.render_page(doc, "both", show_deleted=False)


def test_an_unknown_page_view_is_refused(fixtures_dir: Path):
    with pytest.raises(ValueError, match="unknown view"):
        sbs.render_page(xio.load(fixtures_dir / MARKED), "pdf")
