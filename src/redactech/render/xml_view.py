"""XML view: escaped, pretty-printed XML with line numbers and the change marks highlighted.

``render_xml(doc_or_element, highlight_ids=())`` returns an HTML fragment (no script needed).
Elements carrying ``changeMark="1"`` get the class ``rt-add``, ``rt-modify`` or ``rt-delete``
from their ``changeType`` (their whole block, children included); elements whose ``id`` is in
``highlight_ids`` get ``rt-hl``. The document is never modified: the XML is walked, not
re-serialised, so the layout shown is a normalised one (one tag per line), not the file's bytes.
"""

from __future__ import annotations

from collections.abc import Iterable
from html import escape
from typing import Any

from lxml import etree

from redactech.s1000d import io as xio

INDENT = "  "
XML_CSS = (
    ".rt-xml{font-family:monospace;font-size:.85rem;background:#fafafa;border:1px solid #ddd;"
    "padding:.3rem 0;overflow-x:auto}"
    ".rt-line{display:flex;white-space:pre;border-left:4px solid transparent}"
    ".rt-ln{flex:0 0 3.5rem;text-align:right;padding-right:.6rem;color:#999;user-select:none}"
    ".rt-line.rt-add{background:#e6f7e6;border-left-color:#2a8a2a}"
    ".rt-line.rt-modify{background:#fff6dc;border-left-color:#d49a00}"
    ".rt-line.rt-delete{background:#fde8e8;border-left-color:#c33;text-decoration:line-through}"
    ".rt-line.rt-hl{outline:1px solid #36c}"
)


def _qname(el: Any, name: str) -> str:
    """``prefix:local`` of a Clark name (``{uri}local``) using the prefixes in scope."""
    if not name.startswith("{"):
        return name
    uri, local = name[1:].split("}", 1)
    prefix = next((p for p, u in el.nsmap.items() if u == uri and p), None)
    return f"{prefix}:{local}" if prefix else local


def _tag(el: Any) -> str:
    return _qname(el, el.tag)


def _attributes(el: Any) -> str:
    parts = []
    if el.getparent() is None:  # namespace declarations are shown once, on the root
        for prefix, uri in sorted(el.nsmap.items(), key=lambda item: item[0] or ""):
            name = f"xmlns:{prefix}" if prefix else "xmlns"
            parts.append(f"{name}=&quot;{escape(uri, quote=True)}&quot;")
    for name, value in el.attrib.items():
        parts.append(f"{_qname(el, name)}=&quot;{escape(value, quote=True)}&quot;")
    return (" " + " ".join(parts)) if parts else ""


def _marks(el: Any) -> str:
    """CSS class of the change mark of an element (empty when it has none)."""
    if el.get("changeMark") != "1":
        return ""
    change = el.get("changeType")
    return {"add": "rt-add", "delete": "rt-delete"}.get(change, "rt-modify")


class _Writer:
    def __init__(self, highlight: set[str]) -> None:
        self.highlight = highlight
        self.lines: list[str] = []

    def line(self, depth: int, html_text: str, classes: str) -> None:
        number = len(self.lines) + 1
        css = ("rt-line " + classes).strip()
        self.lines.append(
            f'<div class="{css}"><span class="rt-ln">{number}</span>'
            f"<code>{INDENT * depth}{html_text}</code></div>"
        )

    def text_lines(self, depth: int, text: str | None, classes: str) -> None:
        for piece in (text or "").split("\n"):
            if piece.strip():
                self.line(depth, escape(piece.strip()), classes)

    def element(self, el: Any, depth: int, inherited: str) -> None:
        classes = _marks(el) or inherited
        if el.get("id") in self.highlight:
            classes = (classes + " rt-hl").strip()
        name, attributes = _tag(el), _attributes(el)
        children = list(el)
        text = (el.text or "").strip()
        if not children and not text:
            self.line(depth, f"&lt;{name}{attributes}/&gt;", classes)
            return
        if not children:  # text only: one line
            self.line(
                depth,
                f"&lt;{name}{attributes}&gt;{escape(' '.join(text.split()))}&lt;/{name}&gt;",
                classes,
            )
            return
        self.line(depth, f"&lt;{name}{attributes}&gt;", classes)
        self.text_lines(depth + 1, el.text, classes)
        for child in children:
            self.node(child, depth + 1, classes)
            self.text_lines(depth + 1, child.tail, classes)
        self.line(depth, f"&lt;/{name}&gt;", classes)

    def node(self, node: Any, depth: int, inherited: str) -> None:
        if isinstance(node.tag, str):
            self.element(node, depth, inherited)
        elif node.tag is etree.Comment:
            self.line(depth, escape(f"<!--{node.text or ''}-->"), inherited)
        elif node.tag is etree.ProcessingInstruction:
            body = f" {node.text}" if node.text else ""
            self.line(depth, escape(f"<?{node.target}{body}?>"), inherited)
        else:  # entity references and the like
            self.line(depth, escape(f"&{getattr(node, 'name', '')};"), inherited)


def render_xml(doc_or_element: Any, highlight_ids: Iterable[str] = ()) -> str:
    """HTML fragment of the XML of a document, tree or element (see the module docstring)."""
    root = xio.root_of(doc_or_element)
    writer = _Writer(set(highlight_ids))
    writer.element(root, 0, "")
    return '<div class="rt-xml">' + "".join(writer.lines) + "</div>"
