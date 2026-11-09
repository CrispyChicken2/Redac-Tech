"""Hardened XML input/output for S1000D files (lxml).

Design:

* The parser never resolves entities, never touches the network and never loads an external DTD
  (``make_parser``), so XXE and entity-expansion fixtures stay inert: an ``&xxe;`` stays an
  entity reference node.
* ``load`` keeps what a tree cannot: the exact XML declaration text, the exact DOCTYPE text
  (internal subset included), the text of everything before the root, the newline style, the BOM
  and the raw bytes.
* ``dumps`` returns the original bytes untouched while the tree is unmodified (byte-identical
  round trip, whatever the original quoting, spacing or mixed newlines). Once the tree has been
  modified it is re-serialised (``render``): original prolog re-emitted verbatim, root serialised
  by lxml, comments and processing instructions around the root kept, newline style and BOM
  restored. Limitation: ASCII-compatible encodings only for the newline restore.
* Regular expressions are used only on the raw prolog text (declaration encoding), never on
  XML content.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from lxml import etree

BOM = b"\xef\xbb\xbf"
# Issue alias point (SPEC section 6): ALIASES["name"] lists other element names tried by
# find/findall when another Issue names the same thing differently. Empty for now.
ALIASES: dict[str, list[str]] = {}


def make_parser() -> etree.XMLParser:
    """Hardened parser: no entity resolution, no network, no DTD loading, nothing dropped."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        remove_blank_text=False,
        remove_comments=False,
        remove_pis=False,
        strip_cdata=False,
    )


@dataclass
class XmlDoc:
    tree: Any  # etree._ElementTree
    path: Path | None
    encoding: str
    xml_declaration: str | None  # exact original text, or None
    doctype: str | None  # exact original DOCTYPE text incl. internal subset, or None
    newline: str  # "\r\n" or "\n"
    bom: bool
    raw: bytes = field(default=b"", repr=False)
    prolog: str = field(default="", repr=False)  # exact text before the root (BOM excluded)
    trailer: str = field(default="", repr=False)  # trailing whitespace after the last token
    signature: bytes = field(default=b"", repr=False)  # serialisation at load time
    prolog_nodes: list[str] = field(default_factory=list, repr=False)

    @property
    def root(self) -> Any:
        return self.tree.getroot()


# --- prolog scanning (raw text before the root, string operations only) -----------------------


def _doctype_end(text: str, start: int) -> int:
    """Index just after the ``>`` closing the DOCTYPE that starts at ``start`` (or -1)."""
    i = start + len("<!DOCTYPE")
    n = len(text)
    quote = ""
    in_subset = False
    while i < n:
        c = text[i]
        if quote:
            if c == quote:
                quote = ""
        elif in_subset and text.startswith("<!--", i):
            end = text.find("-->", i + 4)
            if end < 0:
                return -1
            i = end + 2
        elif in_subset and text.startswith("<?", i):
            end = text.find("?>", i + 2)
            if end < 0:
                return -1
            i = end + 1
        elif c in "\"'":
            quote = c
        elif c == "[":
            in_subset = True
        elif c == "]":
            in_subset = False
        elif c == ">" and not in_subset:
            return i + 1
        i += 1
    return -1


def scan_prolog(text: str) -> tuple[str | None, str | None, int]:
    """Return (xml declaration text, DOCTYPE text, index where the root element starts)."""
    decl: str | None = None
    doctype: str | None = None
    i = 0
    n = len(text)
    while i < n:
        j = i
        while j < n and text[j] in " \t\r\n":
            j += 1
        if j >= n:
            return decl, doctype, n
        if j == 0 and text.startswith("<?xml") and text[5:6] in (" ", "\t", "\r", "\n", "?"):
            end = text.find("?>", j)
            if end < 0:
                return decl, doctype, j
            decl = text[j : end + 2]
            i = end + 2
        elif text.startswith("<?", j):
            end = text.find("?>", j + 2)
            if end < 0:
                return decl, doctype, j
            i = end + 2
        elif text.startswith("<!--", j):
            end = text.find("-->", j + 4)
            if end < 0:
                return decl, doctype, j
            i = end + 3
        elif text.startswith("<!DOCTYPE", j):
            end = _doctype_end(text, j)
            if end < 0:
                return decl, doctype, j
            doctype = text[j:end]
            i = end
        else:
            return decl, doctype, j
    return decl, doctype, n


def _declared_encoding(decl: str | None) -> str | None:
    if not decl:
        return None
    found = re.search(r"""encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""", decl)
    return found.group(1) if found else None


def _newline_style(raw: bytes) -> str:
    crlf = raw.count(b"\r\n")
    lone_lf = raw.count(b"\n") - crlf
    return "\r\n" if crlf > lone_lf else "\n"


def _signature(tree: Any) -> bytes:
    return etree.tostring(tree, encoding="utf-8")


def _serialize_node(node: Any) -> str:
    return etree.tostring(node, encoding="unicode", with_tail=False)


def _prolog_nodes(root: Any) -> list[str]:
    before = list(root.itersiblings(preceding=True))
    return [_serialize_node(n) for n in reversed(before)]


# --- load / dump ---------------------------------------------------------------------------------


def load_bytes(data: bytes, path: Path | str | None = None) -> XmlDoc:
    """Parse ``data`` with the hardened parser and record what the tree cannot keep."""
    has_bom = data.startswith(BOM)
    body = data[len(BOM) :] if has_bom else data
    head = body[:200].decode("ascii", errors="ignore")
    declared = _declared_encoding(scan_prolog(head)[0])
    encoding = declared or "utf-8"
    try:
        text = body.decode(encoding, errors="replace")
    except LookupError:  # unknown codec name in the declaration: parser will complain if relevant
        text = body.decode("utf-8", errors="replace")
        encoding = "utf-8"
    decl, doctype, root_start = scan_prolog(text)
    tree = etree.parse(BytesIO(data), make_parser())
    root = tree.getroot()
    stripped = text.rstrip(" \t\r\n")
    return XmlDoc(
        tree=tree,
        path=Path(path) if path is not None else None,
        encoding=encoding,
        xml_declaration=decl,
        doctype=doctype,
        newline=_newline_style(data),
        bom=has_bom,
        raw=data,
        prolog=text[:root_start],
        trailer=text[len(stripped) :],
        signature=_signature(tree),
        prolog_nodes=_prolog_nodes(root),
    )


def load(path: Path | str) -> XmlDoc:
    """Read and parse a file (bytes are read once, the encoding is detected, nothing is fetched)."""
    p = Path(path)
    return load_bytes(p.read_bytes(), p)


def render(doc: XmlDoc) -> bytes:
    """Always re-serialise the tree (see module docstring)."""
    root = doc.tree.getroot()
    nodes = _prolog_nodes(root)
    if nodes == doc.prolog_nodes:
        head = doc.prolog
    else:  # comments / PIs before the root were edited: regenerate the prolog
        pieces = [p for p in (doc.xml_declaration, doc.doctype, *nodes) if p]
        head = "\n".join(pieces) + ("\n" if pieces else "")
    body = etree.tostring(root, encoding=doc.encoding, xml_declaration=False, with_tail=False)
    after = "".join("\n" + _serialize_node(n) for n in root.itersiblings())
    text = head.replace("\r\n", "\n") + body.decode(doc.encoding) + after + doc.trailer
    text = text.replace("\r\n", "\n")
    if doc.newline == "\r\n":
        text = text.replace("\n", "\r\n")
    out = text.encode(doc.encoding)
    return BOM + out if doc.bom else out


def dumps(doc: XmlDoc) -> bytes:
    """Bytes of the document: the original bytes while unmodified, ``render(doc)`` otherwise."""
    if doc.raw and _signature(doc.tree) == doc.signature:
        return doc.raw
    return render(doc)


def save(doc: XmlDoc, path: Path | str | None = None) -> Path:
    """Atomic write (temporary file in the same folder, then replace)."""
    target = Path(path) if path is not None else doc.path
    if target is None:
        raise ValueError("no path to save to")
    data = dumps(doc)
    tmp = target.with_name(target.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def canonical(obj: Any) -> bytes:
    """C14N 1.0 without comments of a document, tree or element.

    If libxml2 refuses to canonicalise (for instance unexpanded entity reference nodes), falls
    back to the plain serialisation, which is still deterministic for comparisons.
    """
    target = obj.tree if isinstance(obj, XmlDoc) else obj
    try:
        return etree.tostring(target, method="c14n", with_comments=False)
    except etree.LxmlError:
        return etree.tostring(target, encoding="utf-8")


# --- element access helpers (Issue alias point) ---------------------------------------------------


def _tree_or_element(obj: Any) -> Any:
    return obj.tree if isinstance(obj, XmlDoc) else obj


def root_of(obj: Any) -> Any:
    """Root element of an ``XmlDoc``, an lxml tree or an element (an element is returned as is)."""
    target = _tree_or_element(obj)
    return target.getroot() if hasattr(target, "getroot") else target


def _names(name: str) -> list[str]:
    return [name, *ALIASES.get(name, [])]


def find(el: Any, name: str) -> Any | None:
    """First match of the ElementPath ``name`` (aliases tried in order), or None."""
    target = _tree_or_element(el)
    for candidate in _names(name):
        found = target.find(candidate)
        if found is not None:
            return found
    return None


def findall(el: Any, name: str) -> list[Any]:
    """All matches of the ElementPath ``name`` (aliases tried in order, first non-empty wins)."""
    target = _tree_or_element(el)
    for candidate in _names(name):
        found = target.findall(candidate)
        if found:
            return found
    return []


def xpath(el: Any, expr: str, **variables: Any) -> Any:
    """XPath 1.0 evaluation on a document, tree or element."""
    return _tree_or_element(el).xpath(expr, **variables)
