"""Tests of redactech.s1000d.io (hardened parsing, byte-exact round trip, serialisation)."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from redactech.s1000d import io as xio

FIGURE_DM = "DMC-RTPROTO-AAA-D00-00-00-00AA-041A-A_001-00_EN-US.XML"


def fixture_files(fixtures_dir: Path) -> list[Path]:
    return sorted(fixtures_dir.glob("*.XML"))


def security_files(fixtures_dir: Path) -> list[Path]:
    return sorted((fixtures_dir / "security").glob("*.xml"))


def bike_xml(repo_root: Path, version: str) -> list[Path]:
    folder = repo_root / "data" / f"s1000d-{version}" / "bike"
    return sorted(p for p in folder.iterdir() if p.suffix.lower() == ".xml")


# --- byte-identical round trip ---------------------------------------------------------------


def test_fixtures_round_trip_byte_identical(fixtures_dir: Path):
    paths = fixture_files(fixtures_dir) + security_files(fixtures_dir)
    assert len(paths) == 14
    for path in paths:
        try:
            doc = xio.load(path)
        except etree.XMLSyntaxError:
            # libxml2 may refuse entity-amplification documents: the safe outcome.
            assert path.name == "billion_laughs.xml", path.name
            continue
        assert xio.dumps(doc) == path.read_bytes(), path.name


def test_render_reproduces_lf_fixtures_exactly(fixtures_dir: Path):
    """The serialiser itself (not the raw-bytes shortcut) reproduces plain LF fixtures."""
    checked = 0
    for path in fixture_files(fixtures_dir):
        raw = path.read_bytes()
        if b"\r\n" in raw or b"&" in raw:
            continue
        assert xio.render(xio.load(path)) == raw, path.name
        checked += 1
    assert checked >= 8


def test_rendered_fixtures_are_canonically_identical(fixtures_dir: Path):
    for path in fixture_files(fixtures_dir):
        doc = xio.load(path)
        again = xio.load_bytes(xio.render(doc))
        assert xio.canonical(again) == xio.canonical(doc), path.name
        assert again.doctype == doc.doctype, path.name
        assert again.xml_declaration == doc.xml_declaration, path.name


def test_render_of_unmodified_fixture_keeps_prolog_verbatim(fixtures_dir: Path):
    for path in fixture_files(fixtures_dir):
        doc = xio.load(path)
        assert xio.render(doc).startswith(doc.prolog.encode()), path.name


def test_figure_fixture_details(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / FIGURE_DM)
    assert doc.newline == "\r\n"
    assert doc.bom is False
    assert doc.xml_declaration == '<?xml version="1.0" encoding="UTF-8"?>'
    assert doc.doctype.startswith("<!DOCTYPE dmodule [")
    assert "<!ENTITY ICN-RTPROTO-A-000001-A-00001-A-001-01 SYSTEM" in doc.doctype
    assert doc.doctype.endswith("]>")
    assert doc.encoding.lower() == "utf-8"


def test_plain_doctype_is_kept_verbatim(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_EN-US.XML")
    assert doc.doctype == "<!DOCTYPE dmodule>"
    assert doc.newline == "\n"


def test_render_restores_crlf_pi_comment_and_entity_name(fixtures_dir: Path):
    out = xio.render(xio.load(fixtures_dir / FIGURE_DM))
    assert b"\n" not in out.replace(b"\r\n", b"")
    assert b"<?Pub Caret?>" in out
    assert b"<!-- editor comment kept by round trips -->" in out
    assert b'infoEntityIdent="ICN-RTPROTO-A-000001-A-00001-A-001-01"' in out
    assert out.count(b"\r\n") == 50


# --- modification ---------------------------------------------------------------------------------


def test_modified_document_is_reserialised_with_everything_kept(fixtures_dir: Path):
    path = fixtures_dir / FIGURE_DM
    doc = xio.load(path)
    para = doc.root.find(".//para")
    para.text = "Changed text."
    out = xio.dumps(doc)
    assert out != path.read_bytes()
    assert b"Changed text." in out
    assert b"<?Pub Caret?>" in out
    assert b"<!--" in out
    assert out.startswith(doc.prolog.encode())
    assert b"\n" not in out.replace(b"\r\n", b"")
    reloaded = xio.load_bytes(out)
    assert reloaded.root.find(".//para").text == "Changed text."
    assert reloaded.doctype == doc.doctype
    assert xio.canonical(reloaded) == xio.canonical(doc)


def test_modify_then_revert_gives_the_original_bytes(fixtures_dir: Path):
    path = fixtures_dir / FIGURE_DM
    doc = xio.load(path)
    para = doc.root.find(".//para")
    original = para.text
    para.text = "Temporary."
    assert xio.dumps(doc) != path.read_bytes()
    para.text = original
    assert xio.dumps(doc) == path.read_bytes()


def test_edited_comment_before_the_root_is_regenerated():
    raw = b'<?xml version="1.0"?>\n<!-- first -->\n<r><a/></r>\n'
    doc = xio.load_bytes(raw)
    assert xio.dumps(doc) == raw
    comment = next(doc.root.itersiblings(preceding=True))
    comment.text = " second "
    out = xio.dumps(doc)
    assert b"<!-- second -->" in out and b"first" not in out
    assert out.startswith(b'<?xml version="1.0"?>\n')
    assert out.endswith(b"<r><a/></r>\n")


def test_entity_reference_in_text_stays_a_reference():
    raw = (
        b'<?xml version="1.0"?>\n<!DOCTYPE r [\n<!ENTITY e1 "expanded">\n]>\n'
        b"<r><p>before &e1; after</p><q>x</q></r>\n"
    )
    doc = xio.load_bytes(raw)
    assert xio.dumps(doc) == raw
    doc.root.find("q").text = "y"
    out = xio.dumps(doc)
    assert b"&e1;" in out
    assert b"expanded" not in out.replace(b'<!ENTITY e1 "expanded">', b"")
    assert b"<q>y</q>" in out


def test_bom_and_missing_declaration():
    with_bom = (
        b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?>'
        b"<!DOCTYPE r[\n]><r>caf\xc3\xa9</r>"
    )
    doc = xio.load_bytes(with_bom)
    assert doc.bom is True
    assert xio.dumps(doc) == with_bom
    doc.root.text = "tea"
    out = xio.dumps(doc)
    assert out.startswith(b"\xef\xbb\xbf")
    assert b"<r>tea</r>" in out
    bare = b"\n<r><a/></r>\n"
    doc2 = xio.load_bytes(bare)
    assert doc2.xml_declaration is None and doc2.doctype is None
    assert xio.dumps(doc2) == bare
    doc2.root.set("k", "v")
    assert xio.dumps(doc2) == b'\n<r k="v"><a/></r>\n'


def test_unmodified_odd_syntax_is_kept_byte_for_byte():
    raw = b"<?xml version='1.0'?>\r\n<r   a='1'\r\n  b = \"2\" >\n<e></e></r>"
    doc = xio.load_bytes(raw)
    assert xio.dumps(doc) == raw


# --- hardening ------------------------------------------------------------------------------------


def test_external_entity_is_not_expanded_and_no_file_is_read(tmp_path: Path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT", encoding="utf-8")
    xml = (
        '<?xml version="1.0"?>\n'
        f'<!DOCTYPE r [<!ENTITY xxe SYSTEM "{secret.as_uri()}">]>\n'
        "<r><para>&xxe;</para></r>\n"
    )
    doc = xio.load_bytes(xml.encode())
    para = doc.root.find("para")
    assert not para.text
    assert any(isinstance(child, etree._Entity) for child in para)
    assert b"TOP-SECRET-CONTENT" not in etree.tostring(doc.tree)
    assert b"TOP-SECRET-CONTENT" not in xio.render(doc)
    assert b"TOP-SECRET-CONTENT" not in xio.canonical(doc)


def test_xxe_fixture_is_inert(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / "security" / "xxe.xml")
    para = doc.root.find("para")
    assert not para.text
    assert any(isinstance(child, etree._Entity) for child in para)


def test_billion_laughs_is_not_expanded(fixtures_dir: Path):
    try:
        doc = xio.load(fixtures_dir / "security" / "billion_laughs.xml")
    except etree.XMLSyntaxError:
        return  # refused by libxml2 (entity amplification limit): the safe outcome
    para = doc.root.find("para")
    assert not para.text
    assert len(etree.tostring(doc.tree)) < 10_000
    assert b"lollol" not in xio.render(doc)


def test_make_parser_returns_an_xml_parser():
    assert isinstance(xio.make_parser(), etree.XMLParser)


# --- prolog scanner -----------------------------------------------------------------------


def test_scan_prolog_handles_quotes_comments_and_pis():
    text = (
        '<?xml version="1.0"?>\n<?xml-stylesheet href="s.xsl"?>\n<!-- it\'s > a comment -->\n'
        "<!DOCTYPE d [\n<!-- it's > odd -->\n<!ENTITY e \"a>b\">\n<?pi x>y?>\n]>\n<d/>"
    )
    decl, doctype, start = xio.scan_prolog(text)
    assert decl == '<?xml version="1.0"?>'
    assert doctype.startswith("<!DOCTYPE d [") and doctype.endswith("]>")
    assert "<!ENTITY e \"a>b\">" in doctype
    assert text[start:] == "<d/>"


def test_scan_prolog_stylesheet_pi_is_not_the_declaration():
    decl, doctype, start = xio.scan_prolog('<?xml-stylesheet href="s.xsl"?>\n<r/>')
    assert decl is None and doctype is None
    assert start == len('<?xml-stylesheet href="s.xsl"?>\n')


def test_scan_prolog_without_prolog():
    assert xio.scan_prolog("<r/>") == (None, None, 0)


# --- canonical, save, helpers -------------------------------------------------------------------


def test_canonical_ignores_comments_attribute_order_and_quotes():
    a = xio.load_bytes(b"<r b='1' a=\"2\"><!-- c --><e/></r>")
    b = xio.load_bytes(b'<r a="2" b="1"><e></e></r>')
    assert xio.canonical(a) == xio.canonical(b)
    assert b"<!--" not in xio.canonical(a)
    assert xio.canonical(a.root) == xio.canonical(b.root)


def test_save_is_atomic_and_writes_dumps(fixtures_dir: Path, tmp_path: Path):
    doc = xio.load(fixtures_dir / FIGURE_DM)
    target = tmp_path / "out.xml"
    assert xio.save(doc, target) == target
    assert target.read_bytes() == xio.dumps(doc)
    doc.root.find(".//para").text = "Saved."
    xio.save(doc, target)
    assert b"Saved." in target.read_bytes()
    assert [p.name for p in tmp_path.iterdir()] == ["out.xml"]


def test_save_without_path_is_an_error():
    doc = xio.load_bytes(b"<r/>")
    with pytest.raises(ValueError):
        xio.save(doc)


def test_find_findall_xpath(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_EN-US.XML")
    assert xio.find(doc.root, "identAndStatusSection/dmAddress") is not None
    assert xio.find(doc.root, "nothing") is None
    assert len(xio.findall(doc.root, ".//proceduralStep")) == 5
    assert len(xio.xpath(doc, "//proceduralStep")) == 5
    assert len(xio.xpath(doc.root, "//proceduralStep[@id=$i]", i="stp-0003")) == 1
    assert xio.root_of(doc) is doc.root and xio.root_of(doc.tree) is doc.root


def test_alias_point(monkeypatch):
    doc = xio.load_bytes(b"<r><newName x='1'/></r>")
    assert xio.find(doc.root, "oldName") is None
    monkeypatch.setitem(xio.ALIASES, "oldName", ["newName"])
    assert xio.find(doc.root, "oldName").get("x") == "1"
    assert len(xio.findall(doc.root, "oldName")) == 1


# --- real Bike data (skipped when data/ is absent) ----------------------------------------


def _check_real(paths: list[Path]) -> None:
    assert paths
    for path in paths:
        raw = path.read_bytes()
        doc = xio.load(path)
        assert xio.dumps(doc) == raw, path.name
        rendered = xio.render(doc)
        if rendered != raw:
            # Re-serialisation may legitimately differ (quotes, empty-tag style, character
            # references, mixed newlines): the canonical form must then be identical.
            assert xio.canonical(xio.load_bytes(rendered)) == xio.canonical(doc), path.name


@pytest.mark.data41
def test_real_bike_41_round_trip(repo_root: Path):
    _check_real(bike_xml(repo_root, "4.1"))


@pytest.mark.data42
def test_real_bike_42_round_trip(repo_root: Path):
    _check_real(bike_xml(repo_root, "4.2"))
