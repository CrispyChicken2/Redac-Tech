"""Published view: an S1000D data module as an IETP-like HTML fragment (XSLT 1.0).

``render_published(doc, show_deleted=True)`` applies ``xslt/published.xsl`` (compiled once) to a
COPY of the document: the file and the caller's tree are never touched, and entity references
(ICN names) stay as they are, since the stylesheet only reads attribute values. Elements marked
``changeType="delete"`` are struck through, or left out with ``show_deleted=False``. The result
is a fragment; ``PUBLISHED_CSS`` styles it. No image is ever loaded: a ``graphic`` is a box with
its ICN name.
"""

from __future__ import annotations

import copy
from io import BytesIO
from pathlib import Path
from typing import Any

from lxml import etree

from redactech.s1000d import io as xio

STYLESHEET = Path(__file__).resolve().parent / "xslt" / "published.xsl"
PUBLISHED_CSS = (
    ".rt-doc{font-family:sans-serif;line-height:1.45;color:#222}"
    ".rt-title{font-size:1.4rem;border-bottom:2px solid #345;padding-bottom:.3rem}"
    ".rt-doc h2{font-size:1.15rem;margin-top:1.4rem;border-bottom:1px solid #ccc}"
    ".rt-doc h3{font-size:1rem;margin:.8rem 0 .3rem}"
    ".rt-applic{display:inline-block;background:#e8eefc;border:1px solid #9ab;border-radius:.8rem;"
    "padding:0 .6rem;font-size:.8rem}"
    ".rt-step{display:flex;gap:.6rem;margin:.4rem 0;padding-left:.4rem;"
    "border-left:4px solid transparent}"
    ".rt-num{flex:0 0 3rem;font-weight:bold}.rt-step-body{flex:1}"
    ".rt-add{border-left:4px solid #2a8a2a}.rt-modify{border-left:4px solid #d49a00}"
    ".rt-deleted{text-decoration:line-through;color:#888;border-left:4px solid #c33}"
    ".rt-box{border:2px solid #888;margin:.5rem 0;padding:.3rem .6rem}"
    ".rt-warning{border-color:#c00;background:#fff0f0}"
    ".rt-caution{border-color:#d80;background:#fff8e8}"
    ".rt-note{border-color:#36a;background:#eef4ff}.rt-box-title{font-weight:bold}"
    ".rt-table{border-collapse:collapse;margin:.4rem 0}"
    ".rt-table th,.rt-table td{border:1px solid #bbb;padding:.2rem .5rem;text-align:left}"
    ".rt-table th{background:#f0f0f0}"
    ".rt-icn{border:1px dashed #888;background:#f6f6f6;padding:1.2rem;margin:.5rem 0;"
    "text-align:center;color:#555}"
    ".rt-unknown{margin:.2rem 0;padding-left:.5rem;border-left:2px dotted #aaa}"
    ".rt-unknown-name{font-family:monospace;font-size:.75rem;background:#eee;padding:0 .3rem}"
    ".rt-none{color:#777;font-style:italic}.rt-ref{color:#36a}"
)

_compiled: etree.XSLT | None = None


def _stylesheet() -> etree.XSLT:
    """The compiled stylesheet (compiled on first use, then reused)."""
    global _compiled
    if _compiled is None:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        tree = etree.parse(BytesIO(STYLESHEET.read_bytes()), parser)
        _compiled = etree.XSLT(tree)
    return _compiled


def _copy_of(doc: Any) -> Any:
    """An independent tree of the document that keeps its DOCTYPE and internal subset.

    A deep copy of an lxml tree drops the internal subset, so a loaded document is serialised
    again (``xio.dumps``: the exact prolog is kept) and parsed with the hardened parser; entity
    references stay unexpanded. An element is copied and wrapped in a new tree.
    """
    if isinstance(doc, xio.XmlDoc):
        return etree.parse(BytesIO(xio.dumps(doc)), xio.make_parser())
    target = xio.tree_of(doc)
    if hasattr(target, "getroot"):
        return etree.parse(BytesIO(etree.tostring(target)), xio.make_parser())
    return etree.ElementTree(copy.deepcopy(target))


def render_published(doc: Any, show_deleted: bool = True) -> str:
    """HTML fragment of the published view of a document, tree or element."""
    source = _copy_of(doc)
    flag = etree.XSLT.strparam("1" if show_deleted else "0")
    result = _stylesheet()(source, **{"show-deleted": flag})
    return str(result)
