"""Side-by-side display: two HTML fragments in two columns, and a proposal's before / after."""

from __future__ import annotations

from html import escape
from typing import Any

from lxml import etree

from redactech.models import Proposal
from redactech.render.published import PUBLISHED_CSS, render_published
from redactech.render.xml_view import XML_CSS, render_xml
from redactech.s1000d import io as xio

SIDE_CSS = (
    ".rt-side{display:grid;grid-template-columns:1fr 1fr;gap:1rem;align-items:start}"
    ".rt-pane{min-width:0;border:1px solid #ccc;padding:.5rem}"
    ".rt-pane-title{font-family:sans-serif;font-weight:bold;margin-bottom:.4rem}"
    ".rt-empty{color:#777;font-style:italic;font-family:sans-serif}"
    ".rt-invalid{font-family:sans-serif;color:#a00}"
)
VIEWS = ("xml", "published")


def render_side_by_side(left_html: str, right_html: str, titles: tuple[str, str]) -> str:
    """Two panes next to each other; the titles are escaped, the fragments are trusted HTML."""
    left, right = titles
    return (
        '<div class="rt-side">'
        f'<div class="rt-pane"><div class="rt-pane-title">{escape(left)}</div>{left_html}</div>'
        f'<div class="rt-pane"><div class="rt-pane-title">{escape(right)}</div>{right_html}</div>'
        "</div>"
    )


def _fragment(xml: str, view: str) -> str:
    """One excerpt in the chosen view; an empty or invalid excerpt gets a short notice."""
    if not xml.strip():
        return '<p class="rt-empty">(nothing)</p>'
    try:
        element = etree.fromstring(xml.encode("utf-8"), xio.make_parser())
    except etree.LxmlError as exc:
        notice = f'<p class="rt-invalid">Not well-formed XML: {escape(str(exc))}</p>'
        return notice + f"<pre>{escape(xml)}</pre>"
    if view == "xml":
        return render_xml(element)
    shell = etree.Element("dmodule")  # the minimal data module around the excerpt
    etree.SubElement(shell, "identAndStatusSection")
    etree.SubElement(shell, "content").append(element)
    return render_published(shell)


def render_before_after(proposal: Proposal, view: str = "xml") -> str:
    """The before and after excerpts of a proposal side by side (``xml`` or ``published``).

    The "after" side shows what the writer typed when the proposal was edited.
    """
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r} (expected one of {', '.join(VIEWS)})")
    edited = proposal.status == "edited" and proposal.edited_xml
    after = proposal.edited_xml if edited else proposal.after_xml
    return render_side_by_side(
        _fragment(proposal.before_xml, view), _fragment(after or "", view), ("Before", "After")
    )


def render_page(doc: Any, view: str = "both", show_deleted: bool = True, title: str = "") -> str:
    """A full self-contained HTML page of a document: XML view, published view, or both."""
    if view not in (*VIEWS, "both"):
        raise ValueError(f"unknown view {view!r} (expected one of xml, published, both)")
    xml = render_xml(doc) if view in ("xml", "both") else ""
    published = render_published(doc, show_deleted) if view in ("published", "both") else ""
    if view == "both":
        body = render_side_by_side(xml, published, ("XML", "Published"))
    else:
        body = xml or published
    css = XML_CSS + PUBLISHED_CSS + SIDE_CSS
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape(title or 'Render')}</title><style>{css}</style></head>"
        f"<body>{body}</body></html>\n"
    )
