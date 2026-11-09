"""Tests of redactech.s1000d.diff."""

from __future__ import annotations

from pathlib import Path

from redactech.s1000d import diff
from redactech.s1000d import io as xio

BEFORE = (
    b'<r><s id="a"><p>one</p></s><s id="b"><p>two</p></s></r>'
)


def doc(xml: bytes) -> xio.XmlDoc:
    return xio.load_bytes(xml)


# --- c14n_equal -----------------------------------------------------------------------


def test_c14n_equal_ignores_syntax_differences_and_comments():
    a = doc(b"<r b='1' a=\"2\"><!-- c --><e/></r>")
    b = doc(b'<r a="2" b="1"><e></e></r>')
    assert diff.c14n_equal(a, b)
    assert diff.c14n_equal(a.root, b.root)


def test_c14n_equal_detects_real_differences():
    assert not diff.c14n_equal(doc(b"<r><e>1</e></r>"), doc(b"<r><e>2</e></r>"))
    assert not diff.c14n_equal(doc(b'<r a="1"/>'), doc(b'<r a="2"/>'))
    assert not diff.c14n_equal(doc(b"<r><a/><b/></r>"), doc(b"<r><b/><a/></r>"))


def test_fixture_equals_itself_and_not_another(fixtures_dir: Path):
    names = sorted(p.name for p in fixtures_dir.glob("DMC-*.XML"))
    first = xio.load(fixtures_dir / names[0])
    assert diff.c14n_equal(first, xio.load(fixtures_dir / names[0]))
    assert not diff.c14n_equal(first, xio.load(fixtures_dir / names[1]))


# --- changed_elements -----------------------------------------------------------------


def test_identical_documents_have_no_change():
    assert diff.changed_elements(doc(BEFORE), doc(BEFORE)) == []


def test_text_change_reports_only_the_deepest_element():
    after = b'<r><s id="a"><p>one</p></s><s id="b"><p>TWO</p></s></r>'
    assert diff.changed_elements(doc(BEFORE), doc(after)) == ["/r/s[2]/p"]


def test_attribute_change_reports_the_element():
    after = b'<r><s id="a" x="1"><p>one</p></s><s id="b"><p>two</p></s></r>'
    assert diff.changed_elements(doc(BEFORE), doc(after)) == ["/r/s[1]"]


def test_inserted_element_is_reported_once_and_siblings_stay_matched():
    after = b'<r><s id="a"><p>one</p></s><s id="n"><p>new</p></s><s id="b"><p>two</p></s></r>'
    assert diff.changed_elements(doc(BEFORE), doc(after)) == ["/r/s[2]"]


def test_removed_element_is_reported_with_its_path_in_the_old_document():
    after = b'<r><s id="a"><p>one</p></s></r>'
    assert diff.changed_elements(doc(BEFORE), doc(after)) == ["/r/s[2]"]


def test_moved_siblings_report_their_parent():
    after = b'<r><s id="b"><p>two</p></s><s id="a"><p>one</p></s></r>'
    assert diff.changed_elements(doc(BEFORE), doc(after)) == ["/r"]


def test_elements_without_id_are_matched_by_position_below_the_nearest_id():
    before = b'<r><s id="a"><p>one</p><p>two</p></s></r>'
    after = b'<r><s id="a"><p>one</p><p>2</p></s></r>'
    assert diff.changed_elements(doc(before), doc(after)) == ["/r/s/p[2]"]


def test_mixed_content_text_change_reports_the_parent():
    before = b"<r><p>Install <b/> now</p></r>"
    after = b"<r><p>Install <b/> later</p></r>"
    assert diff.changed_elements(doc(before), doc(after)) == ["/r/p"]


def test_comment_change_reports_the_parent():
    assert diff.changed_elements(doc(b"<r><!--x--><a/></r>"), doc(b"<r><!--y--><a/></r>")) == ["/r"]


def test_whitespace_is_significant_unless_asked():
    before, after = doc(b"<r><p>a  b</p></r>"), doc(b"<r><p>a b</p></r>")
    assert diff.changed_elements(before, after) == ["/r/p"]
    assert diff.changed_elements(before, after, strip_whitespace=True) == []


def test_accepts_trees_and_elements():
    after = doc(b'<r><s id="a"><p>one</p></s><s id="b"><p>TWO</p></s></r>')
    before = doc(BEFORE)
    assert diff.changed_elements(before.tree, after.tree) == ["/r/s[2]/p"]
    assert diff.changed_elements(before.root, after.root) == ["/r/s[2]/p"]


def test_edit_of_a_fixture_is_the_only_reported_change(fixtures_dir: Path):
    path = fixtures_dir / "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_EN-US.XML"
    before, after = xio.load(path), xio.load(path)
    step = next(el for el in after.root.iter("proceduralStep") if el.get("id") == "stp-0003")
    step.find("para").text = "Tighten the fasteners with the wrench."
    assert diff.changed_elements(before, after) == [
        "/dmodule/content/procedure/mainProcedure/proceduralStep[3]/para"
    ]
    assert not diff.c14n_equal(before, after)
