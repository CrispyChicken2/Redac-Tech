"""Tests of redactech.render.published: the XSLT 1.0 published view."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lxml import etree

from redactech.render import published
from redactech.render.published import render_published
from redactech.s1000d import io as xio

CODE = "AAA-D00-00-00-00AA"
PROCED = f"DMC-RTPROTO-{CODE}-520A-A_001-00_EN-US.XML"
MARKED = f"DMC-RTPROTO-{CODE}-520B-A_007-00_EN-US.XML"
VIOLATING = f"DMC-RTPROTO-{CODE}-521A-A_001-00_EN-US.XML"
IPD = f"DMC-RTPROTO-{CODE}-941A-D_001-00_EN-US.XML"
COMREP = f"DMC-RTPROTO-{CODE}-0A3A-D_001-00_EN-US.XML"
TOOLS = f"DMC-RTPROTO-{CODE}-0A6A-D_001-00_EN-US.XML"
APPLIC = f"DMC-RTPROTO-{CODE}-040A-A_001-00_EN-US.XML"
FIGURE = f"DMC-RTPROTO-{CODE}-041A-A_001-00_EN-US.XML"
REPO_ROOT = Path(__file__).resolve().parents[2]


def html_of(fixtures_dir: Path, name: str, show_deleted: bool = True) -> str:
    return render_published(xio.load(fixtures_dir / name), show_deleted)


def shell(content: str, status: str = "") -> etree._Element:
    """A minimal data module around some content."""
    xml = (
        "<dmodule><identAndStatusSection><dmAddress><dmAddressItems><dmTitle>"
        "<techName>Unit</techName><infoName>Info</infoName></dmTitle></dmAddressItems>"
        f"</dmAddress><dmStatus>{status}</dmStatus></identAndStatusSection>"
        f"<content>{content}</content></dmodule>"
    )
    return etree.fromstring(xml)


def numbers(html: str) -> list[str]:
    return re.findall(r'<span class="rt-num">([^<]*)</span>', html)


# --- title, steps, requirements -----------------------------------------------------------


def test_the_title_comes_from_dmtitle(fixtures_dir: Path):
    html = html_of(fixtures_dir, PROCED)
    assert '<h1 class="rt-title">Prototype unit - Replace the bracket</h1>' in html


def test_main_steps_are_numbered(fixtures_dir: Path):
    html = html_of(fixtures_dir, PROCED)
    assert numbers(html) == ["1", "2", "3", "4", "5"]
    assert "Tighten the fasteners by hand." in html and "Close the access panel" in html


def test_nested_steps_get_a_multi_level_number():
    steps = (
        '<procedure><mainProcedure><proceduralStep id="a"><para>A</para>'
        '<proceduralStep id="b"><para>B</para><proceduralStep id="c"><para>C</para>'
        '</proceduralStep></proceduralStep><proceduralStep id="d"><para>D</para>'
        '</proceduralStep></proceduralStep><proceduralStep id="e"><para>E</para>'
        "</proceduralStep></mainProcedure></procedure>"
    )
    assert numbers(render_published(shell(steps))) == ["1", "1.1", "1.1.1", "1.2", "2"]


def test_preliminary_requirements_are_tables(fixtures_dir: Path):
    html = html_of(fixtures_dir, PROCED)
    for title in ("Support equipment", "Supplies", "Spares"):
        assert f"<h3>{title}</h3>" in html
    assert "<td>Torque wrench</td><td>FAKE-PN-001</td><td>1</td>" in html
    assert "<td>Contact grease</td><td>FAKE-PN-001</td><td>1</td>" in html
    assert "<td>Bracket</td><td>X2</td><td>1</td>" in html
    assert "<th>Part number</th>" in html
    assert '<p class="rt-none">None</p>' in html  # safety and close conditions


def test_close_requirements_follow_the_steps(fixtures_dir: Path):
    html = html_of(fixtures_dir, PROCED)
    assert html.index("<h2>Procedure</h2>") < html.index("<h2>Close requirements</h2>")
    assert html.index("<h2>Preliminary requirements</h2>") < html.index("<h2>Procedure</h2>")


# --- boxes, applicability -----------------------------------------------------------------


def test_warning_caution_and_note_boxes():
    content = (
        "<procedure><mainProcedure><proceduralStep id='s'>"
        "<warning><warningAndCautionPara>Hot surface</warningAndCautionPara></warning>"
        "<caution><warningAndCautionPara>Sharp edge</warningAndCautionPara></caution>"
        "<note><notePara>Keep the part</notePara></note><para>Go.</para>"
        "</proceduralStep></mainProcedure></procedure>"
    )
    html = render_published(shell(content))
    assert '<div class="rt-box rt-warning"><div class="rt-box-title">WARNING</div>' in html
    assert '<p class="rt-box-text">Hot surface</p>' in html
    assert 'class="rt-box rt-caution"' in html and "Sharp edge" in html
    assert 'class="rt-box rt-note"' in html and ">NOTE<" in html and "Keep the part" in html


def test_the_applicability_badge_shows_the_display_text(fixtures_dir: Path):
    html = html_of(fixtures_dir, APPLIC)
    assert '<span class="rt-applic">Product A or product B</span>' in html
    assert '<span class="rt-applic">All</span>' in html_of(fixtures_dir, PROCED)


def test_the_applicability_badge_falls_back_to_the_assert_values():
    status = (
        '<applic><evaluate andOr="or"><assert applicPropertyIdent="prodattr" '
        'applicPropertyValues="A"/><assert applicPropertyIdent="prodattr" '
        'applicPropertyValues="B"/></evaluate></applic>'
    )
    html = render_published(shell("<description/>", status))
    assert '<span class="rt-applic">prodattr=A / prodattr=B</span>' in html


# --- parts data ---------------------------------------------------------------------------


def test_the_illustrated_parts_data_is_a_table(fixtures_dir: Path):
    html = html_of(fixtures_dir, IPD)
    for header in ("Item", "Part number", "Quantity", "Description"):
        assert f"<th>{header}</th>" in html
    assert "<td>001</td><td>LRU1010</td><td>1</td><td>Line replaceable unit</td>" in html
    assert "<td>002</td><td>X2</td><td>1</td><td>Bracket</td>" in html


def test_the_common_repositories_are_tables(fixtures_dir: Path):
    parts = html_of(fixtures_dir, COMREP)
    assert "<h2>Parts</h2>" in parts
    assert "<td>LRU1010</td><td>FAKE1</td><td>Line replaceable unit</td>" in parts
    assert "<td>X2</td><td>FAKE1</td><td>Bracket</td>" in parts
    tools = html_of(fixtures_dir, TOOLS)
    assert "<h2>Tools</h2>" in tools
    assert "<td>FAKE-PN-001</td><td>FAKE1</td><td>Torque wrench</td>" in tools


def test_supplies_of_a_common_repository():
    content = (
        "<commonRepository><supplyRepository><supplySpec>"
        '<supplyIdent supplyNumber="SUP-1" manufacturerCodeValue="FAKE1"/>'
        "<itemIdentData><descrForPart>Grease</descrForPart></itemIdentData>"
        "</supplySpec></supplyRepository></commonRepository>"
    )
    html = render_published(shell(content))
    assert "<h2>Supplies</h2>" in html and "<td>SUP-1</td><td>FAKE1</td><td>Grease</td>" in html


# --- change marks -------------------------------------------------------------------------


def test_change_bars_follow_the_change_marks(fixtures_dir: Path):
    html = html_of(fixtures_dir, MARKED)
    assert html.count('class="rt-step rt-add"') == 1
    assert html.count('class="rt-step rt-modify"') == 1
    assert html.count('class="rt-step rt-deleted"') == 1
    assert html.count('class="rt-step"') == 1  # the unmarked step
    assert html.index("rt-add") < html.index("Step modified in the previous cycle.")


def test_deleted_elements_are_struck_through_or_hidden(fixtures_dir: Path):
    shown = html_of(fixtures_dir, MARKED, show_deleted=True)
    assert "Step marked as deleted but still present." in shown
    assert numbers(shown) == ["1", "2", "3", "4"]
    hidden = html_of(fixtures_dir, MARKED, show_deleted=False)
    assert "Step marked as deleted but still present." not in hidden
    assert "rt-deleted" not in hidden
    assert numbers(hidden) == ["1", "2", "3"]  # the numbering has no gap
    assert "Step added in the previous cycle." in hidden


def test_deleted_table_rows_follow_the_same_rule():
    content = (
        "<commonRepository><partRepository>"
        '<partSpec><partIdent partNumberValue="KEEP" manufacturerCodeValue="M"/></partSpec>'
        '<partSpec changeMark="1" changeType="delete"><partIdent partNumberValue="GONE" '
        'manufacturerCodeValue="M"/></partSpec></partRepository></commonRepository>'
    )
    shown = render_published(shell(content), show_deleted=True)
    assert "<td>GONE</td>" in shown and "rt-row rt-deleted" in shown
    hidden = render_published(shell(content), show_deleted=False)
    assert "<td>GONE</td>" not in hidden and "<td>KEEP</td>" in hidden


# --- figures, unknown elements ------------------------------------------------------------


def test_graphics_are_icn_placeholders_without_any_image(fixtures_dir: Path):
    html = html_of(fixtures_dir, FIGURE)
    assert '<span class="rt-icn-id">ICN ICN-RTPROTO-A-000001-A-00001-A-001-01</span>' in html
    assert "<img" not in html and "src=" not in html and ".png" not in html


def test_unknown_elements_are_rendered_generically(fixtures_dir: Path):
    html = html_of(fixtures_dir, VIOLATING)
    assert '<span class="rt-unknown-name">unknownElement</span>' in html
    assert "This element does not exist in the schema." in html
    html = render_published(shell("<weirdThing>some text<inner>deep</inner></weirdThing>"))
    assert 'class="rt-unknown-name">weirdThing<' in html
    assert 'class="rt-unknown-name">inner<' in html
    assert "some text" in html and "deep" in html


def test_a_forbidden_note_in_a_step_is_still_shown(fixtures_dir: Path):
    html = html_of(fixtures_dir, VIOLATING)
    assert "This note breaks the project rule." in html and "rt-note" in html


# --- safety of the transform --------------------------------------------------------------


def test_the_output_has_no_script_and_text_is_escaped():
    content = (
        "<description><levelledPara><para>1 &lt; 2 &amp; &lt;b&gt;</para>"
        "</levelledPara></description>"
    )
    html = render_published(shell(content))
    assert "1 &lt; 2 &amp; &lt;b&gt;" in html and "<b>" not in html
    assert "<script" not in html.lower()


def test_the_document_is_not_changed(fixtures_dir: Path):
    doc = xio.load(fixtures_dir / MARKED)
    before = xio.canonical(doc)
    render_published(doc, show_deleted=False)
    assert xio.canonical(doc) == before


def test_the_stylesheet_is_compiled_once(fixtures_dir: Path):
    html_of(fixtures_dir, PROCED)
    first = published._stylesheet()
    html_of(fixtures_dir, MARKED)
    assert published._stylesheet() is first


def test_the_stylesheet_uses_no_extension_and_no_external_document():
    text = published.STYLESHEET.read_text(encoding="utf-8")
    assert 'version="1.0"' in text and "document(" not in text
    assert "xsl:import" not in text and "xsl:include" not in text
    assert "exslt" not in text and "msxsl" not in text


def test_every_fixture_renders(fixtures_dir: Path):
    for path in sorted(fixtures_dir.glob("DMC-*.XML")):
        html = render_published(xio.load(path))
        assert html.startswith('<div class="rt-doc">'), path.name


@pytest.mark.data41
def test_every_bike_41_data_module_renders():
    folder = REPO_ROOT / "data" / "s1000d-4.1" / "bike"
    paths = sorted(folder.glob("DMC-*.XML"))
    assert paths
    for path in paths:
        html = render_published(xio.load(path))
        assert html.startswith('<div class="rt-doc">'), path.name
        assert "<script" not in html.lower() and "<img" not in html


def test_the_transform_gets_a_copy_of_the_whole_tree_with_its_doctype(
    fixtures_dir: Path, monkeypatch
):
    """The DOCTYPE and its internal subset (ICN entities) are kept in the copy."""
    seen = []

    def fake_transform(source, **params):
        seen.append(source)
        return "<div/>"

    monkeypatch.setattr(published, "_stylesheet", lambda: fake_transform)
    doc = xio.load(fixtures_dir / FIGURE)
    before = xio.canonical(doc)
    assert published.render_published(doc, show_deleted=False) == "<div/>"
    (source,) = seen
    assert source is not doc.tree and hasattr(source, "getroot")
    assert source.getroot() is not doc.tree.getroot()
    entities = {e.name for e in source.docinfo.internalDTD.iterentities()}
    assert "ICN-RTPROTO-A-000001-A-00001-A-001-01" in entities
    assert xio.canonical(doc) == before  # the caller's tree was not touched


def test_an_element_is_wrapped_in_a_new_tree(monkeypatch):
    seen = []
    monkeypatch.setattr(published, "_stylesheet", lambda: lambda s, **p: seen.append(s) or "x")
    element = etree.fromstring("<dmodule><content/></dmodule>")
    published.render_published(element)
    assert seen[0].getroot().tag == "dmodule" and seen[0].getroot() is not element
