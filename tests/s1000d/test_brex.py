"""Tests of redactech.s1000d.brex."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from redactech.s1000d import brex
from redactech.s1000d import io as xio

DEFAULT_NAME = "DMC-RTDEFLT-AAA-D00-00-00-00AA-022A-D_001-00_EN-US.XML"
PROJECT_NAME = "DMC-RTPROTO-AAA-D00-00-00-00AA-022A-D_001-00_EN-US.XML"
APPLIC_NAME = "DMC-RTPROTO-AAA-D00-00-00-00AA-040A-A_001-00_EN-US.XML"
PROCED_NAME = "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_EN-US.XML"
VIOLATING_NAME = "DMC-RTPROTO-AAA-D00-00-00-00AA-521A-A_001-00_EN-US.XML"
DEFAULT_KEY = "RTDEFLT-AAA-D00-00-00-00AA-022A-D"
PROJECT_KEY = "RTPROTO-AAA-D00-00-00-00AA-022A-D"


# --- synthetic documents --------------------------------------------------------------


def dmcode(model: str, info: str = "022") -> str:
    return (
        f'<dmCode modelIdentCode="{model}" systemDiffCode="AAA" systemCode="D00" '
        'subSystemCode="0" subSubSystemCode="0" assyCode="00" disassyCode="00" '
        f'disassyCodeVariant="AA" infoCode="{info}" infoCodeVariant="A" itemLocationCode="D"/>'
    )


def status(ref_model: str | None) -> str:
    if ref_model is None:
        return ""
    return (
        "<dmStatus><brexDmRef><dmRef><dmRefIdent>"
        f"{dmcode(ref_model)}</dmRefIdent></dmRef></brexDmRef></dmStatus>"
    )


def rule(path: str, flag: int, use: str = "", values: tuple[tuple[str, str], ...] = ()) -> str:
    objs = "".join(
        f'<objectValue valueForm="{f}" valueAllowed="{a}">{a}</objectValue>' for f, a in values
    )
    return (
        f'<structureObjectRule><objectPath allowedObjectFlag="{flag}">{path}</objectPath>'
        f"<objectUse>{use}</objectUse>{objs}</structureObjectRule>"
    )


def brex_xml(model: str, rules: str, ref_model: str | None = None) -> bytes:
    return (
        "<dmodule><identAndStatusSection><dmAddress><dmIdent>"
        f"{dmcode(model)}</dmIdent></dmAddress>{status(ref_model)}</identAndStatusSection>"
        "<content><brex><contextRules><structureObjectRuleGroup>"
        f"{rules}</structureObjectRuleGroup></contextRules></brex></content></dmodule>"
    ).encode()


def dm_xml(ref_model: str | None) -> xio.XmlDoc:
    xml = (
        f"<dmodule><identAndStatusSection>{status(ref_model)}</identAndStatusSection>"
        "<content/></dmodule>"
    )
    return xio.load_bytes(xml.encode())


def write_brex(folder: Path, model: str, ref_model: str | None, issue: str = "001-00") -> Path:
    path = folder / f"DMC-{model}-AAA-D00-00-00-00AA-022A-D_{issue}_EN-US.XML"
    path.write_bytes(brex_xml(model, "", ref_model))
    return path


def check(document: str, *rules: str):
    doc = xio.load_bytes(document.encode())
    return brex.check_brex(doc, [xio.load_bytes(brex_xml("SYNTH", "".join(rules)))])


def violations(results):
    return [r for r in results if not r.ok and r.severity == "error"]


def warnings(results):
    return [r for r in results if not r.ok and r.severity == "warning"]


def load(fixtures_dir: Path, name: str) -> xio.XmlDoc:
    return xio.load(fixtures_dir / name)


def fixture_chain(fixtures_dir: Path):
    return [load(fixtures_dir, PROJECT_NAME), load(fixtures_dir, DEFAULT_NAME)]


# --- load_rules -----------------------------------------------------------------------


def test_default_like_brex_rules(fixtures_dir: Path):
    rules = brex.load_rules(load(fixtures_dir, DEFAULT_NAME))
    assert [r.flag for r in rules] == [0, 1, 2]
    assert [r.xpath for r in rules] == [
        "//emphasis//emphasis",
        "//dmStatus/qualityAssurance",
        "//dmStatus/@issueType",
    ]
    assert rules[0].message == "Nested emphasis is forbidden."
    assert rules[0].id == f"{DEFAULT_KEY}#1"
    assert rules[0].brex == DEFAULT_KEY
    assert [(v.form, v.allowed) for v in rules[2].values] == [
        ("single", "new"),
        ("single", "changed"),
        ("single", "deleted"),
    ]


def test_project_brex_rule(fixtures_dir: Path):
    (rule_,) = brex.load_rules(load(fixtures_dir, PROJECT_NAME))
    assert (rule_.flag, rule_.xpath) == (0, "//proceduralStep/note")
    assert rule_.message == "A note is not allowed directly inside a procedural step."
    assert rule_.as_dict() == {
        "id": rule_.id,
        "xpath": "//proceduralStep/note",
        "flag": 0,
        "message": rule_.message,
        "brex": PROJECT_KEY,
    }


def test_rule_id_attribute_is_used_and_empty_paths_skipped():
    xml = (
        b"<dmodule><content><brex><contextRules><structureObjectRuleGroup>"
        b'<structureObjectRule id="r1"><objectPath>//a</objectPath></structureObjectRule>'
        b"<structureObjectRule><objectPath>  </objectPath></structureObjectRule>"
        b"</structureObjectRuleGroup></contextRules></brex></content></dmodule>"
    )
    rules = brex.load_rules(xio.load_bytes(xml))
    assert [(r.id, r.flag) for r in rules] == [("r1", 2)]  # default flag is 2


# --- check_brex on fixtures -----------------------------------------------------------


def test_note_in_step_violates_the_project_rule(fixtures_dir: Path):
    results = brex.check_brex(load(fixtures_dir, VIOLATING_NAME), fixture_chain(fixtures_dir))
    (found,) = violations(results)
    assert found.name == "brex" and found.severity == "error"
    assert found.rule["flag"] == 0 and found.rule["xpath"] == "//proceduralStep/note"
    assert found.rule["brex"] == PROJECT_KEY
    assert "A note is not allowed" in found.details
    assert found.xpath == "/dmodule/content/procedure/mainProcedure/proceduralStep/note"
    assert warnings(results) == []


def test_valid_fixture_has_no_violation(fixtures_dir: Path):
    results = brex.check_brex(load(fixtures_dir, PROCED_NAME), fixture_chain(fixtures_dir))
    assert len(results) == 1 and results[0].ok
    assert results[0].details.startswith("4 rules checked")


def test_missing_mandatory_object_flag_1(fixtures_dir: Path):
    doc = load(fixtures_dir, PROCED_NAME)
    qa = doc.root.find(".//qualityAssurance")
    qa.getparent().remove(qa)
    (found,) = violations(brex.check_brex(doc, fixture_chain(fixtures_dir)))
    assert found.rule["flag"] == 1 and found.rule["xpath"] == "//dmStatus/qualityAssurance"
    assert "mandatory" in found.details and found.xpath is None


def test_value_outside_object_values_flag_2(fixtures_dir: Path):
    doc = load(fixtures_dir, PROCED_NAME)
    doc.root.find(".//dmStatus").set("issueType", "bogus")
    (found,) = violations(brex.check_brex(doc, fixture_chain(fixtures_dir)))
    assert found.rule["flag"] == 2 and "'bogus'" in found.details
    assert found.xpath == "/dmodule/identAndStatusSection/dmStatus/@issueType"


def test_forbidden_element_flag_0_in_the_default_brex(fixtures_dir: Path):
    doc = load(fixtures_dir, PROCED_NAME)
    outer = etree.SubElement(doc.root.find(".//para"), "emphasis")
    etree.SubElement(outer, "emphasis")
    (found,) = violations(brex.check_brex(doc, fixture_chain(fixtures_dir)))
    assert found.rule["flag"] == 0 and found.rule["brex"] == DEFAULT_KEY


def test_empty_chain_is_a_warning(fixtures_dir: Path):
    results = brex.check_brex(load(fixtures_dir, PROCED_NAME), [])
    assert len(results) == 1 and (results[0].ok, results[0].severity) == (False, "warning")


# --- rule semantics on synthetic documents --------------------------------------------


def test_flag_0_with_values_only_forbids_those_values():
    results = check(
        '<r><p kind="ok"/><p kind="forbidden"/></r>',
        rule("//p/@kind", 0, "no", (("single", "forbidden"),)),
    )
    (found,) = violations(results)
    assert "forbidden value 'forbidden'" in found.details


def test_flag_0_without_values_reports_every_selected_node():
    results = check("<r><p/><p/><q/></r>", rule("//p", 0, "no p"))
    assert [r.xpath for r in violations(results)] == ["/r/p[1]", "/r/p[2]"]


def test_numeric_range():
    results = check(
        '<r><p n="3"/><p n="9"/><p n="5"/><p n="1"/></r>',
        rule("//p/@n", 2, "n in 1..5", (("range", "1~5"),)),
    )
    (found,) = violations(results)
    assert "'9'" in found.details


def test_string_range_when_not_numeric():
    results = check(
        '<r><p c="c"/><p c="e"/></r>', rule("//p/@c", 2, "b..d", (("range", "b~d"),))
    )
    (found,) = violations(results)
    assert "'e'" in found.details


def test_pattern_is_applied_to_the_value_with_a_full_match():
    results = check(
        '<r><p code="AB12"/><p code="ab12"/><p code="AB12x"/></r>',
        rule("//p/@code", 2, "code", (("pattern", "[A-Z]{2}[0-9]+"),)),
    )
    assert [("'ab12'" in v.details, "'AB12x'" in v.details) for v in violations(results)] == [
        (True, False),
        (False, True),
    ]


def test_several_single_values_and_stripped_element_text():
    results = check(
        "<r><color>red</color><color> blue </color><color>green</color></r>",
        rule("//color", 2, "colors", (("single", "red"), ("single", "green"))),
    )
    (found,) = violations(results)
    assert "'blue'" in found.details


def test_flag_1_present_absent_and_with_values():
    assert violations(check("<r><p/></r>", rule("//p", 1, "need p"))) == []
    (missing,) = violations(check("<r/>", rule("//p", 1, "need p")))
    assert "mandatory" in missing.details
    (bad,) = violations(check('<r><p k="x"/></r>', rule("//p/@k", 1, "k", (("single", "y"),))))
    assert "'x'" in bad.details


def test_flag_2_without_values_never_complains():
    assert violations(check("<r><p/></r>", rule("//p", 2, "free"))) == []


def test_bad_xpath_is_one_warning_and_other_rules_still_run():
    results = check("<r><p/></r>", rule("//p[", 0, "broken"), rule("//p", 0, "no p"))
    (warn,) = warnings(results)
    assert warn.details.startswith("rule ") and "XPath error" in warn.details
    assert warn.rule["xpath"] == "//p["
    assert len(violations(results)) == 1


def test_xpath_returning_a_number_is_a_warning():
    (warn,) = warnings(check("<r><p/></r>", rule("count(//p)", 0, "count")))
    assert "does not select nodes" in warn.details


def test_invalid_pattern_is_a_warning():
    results = check('<r><p k="x"/></r>', rule("//p/@k", 2, "k", (("pattern", "("),)))
    (warn,) = warnings(results)
    assert "invalid objectValue pattern" in warn.details


@pytest.mark.parametrize(
    "value,form,allowed,expected",
    [
        ("a", "single", "a", True),
        (" a ", "single", "a", True),
        ("b", "single", "a", False),
        ("b", "", "b", True),
        ("2", "range", "1~3", True),
        ("3.5", "range", "1~3", False),
        ("1", "range", "1~3", True),
        ("c", "range", "b~d", True),
        ("x", "range", "b~d", False),
        ("v", "range", "v", True),
        ("AB1", "pattern", "[A-Z]+[0-9]", True),
        ("AB1z", "pattern", "[A-Z]+[0-9]", False),
    ],
)
def test_value_allowed(value: str, form: str, allowed: str, expected: bool):
    assert brex.value_allowed(value, brex.BrexValue(form, allowed)) is expected


def test_violations_are_capped_with_an_explanatory_note():
    results = check("<r>" + "<p/>" * 250 + "</r>", rule("//p", 0, "no p"))
    assert len(violations(results)) == brex.MAX_VIOLATIONS_PER_RULE == 200
    (note,) = warnings(results)
    assert "50 more violations not listed" in note.details


def test_rule_xpath_keeps_inner_whitespace():
    expr = "//p[@a='x  y']"
    (loaded,) = brex.load_rules(xio.load_bytes(brex_xml("SYNTH", rule(expr, 0, "no"))))
    assert loaded.xpath == expr
    results = check('<r><p a="x  y"/><p a="x y"/></r>', rule(expr, 0, "no"))
    assert len(violations(results)) == 1


# --- index, chain, swap ---------------------------------------------------------------


def test_index_brex_lists_only_brex_files(fixtures_dir: Path):
    index = brex.index_brex([fixtures_dir])
    assert set(index) == {DEFAULT_KEY, PROJECT_KEY}
    assert index[PROJECT_KEY].name == PROJECT_NAME


def test_index_brex_keeps_the_latest_issue_and_skips_noise(tmp_path: Path):
    write_brex(tmp_path, "AAAA", None, "001-00")
    newest = write_brex(tmp_path, "AAAA", None, "002-00")
    (tmp_path / "DMC-AAAA-AAA-D00-00-00-00AA-040A-A_001-00_EN-US.XML").write_bytes(b"<x/>")
    (tmp_path / "DMC-AAAA-AAA-D00-00-00-00AA-022A-D_001-00_EN-US.pdf").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    index = brex.index_brex([tmp_path, tmp_path / "missing-folder"])
    assert index == {"AAAA-AAA-D00-00-00-00AA-022A-D": newest}


def test_chain_follows_project_then_default(fixtures_dir: Path):
    index = brex.index_brex([fixtures_dir])
    notes: list = []
    chain = brex.resolve_chain(load(fixtures_dir, APPLIC_NAME), index, notes)
    assert [brex.brex_key(c) for c in chain] == [PROJECT_KEY, DEFAULT_KEY]
    assert notes == []


def test_chain_of_brex_documents(fixtures_dir: Path):
    index = brex.index_brex([fixtures_dir])
    project_chain = brex.resolve_chain(load(fixtures_dir, PROJECT_NAME), index)
    assert [brex.brex_key(c) for c in project_chain] == [DEFAULT_KEY]
    default_chain = brex.resolve_chain(load(fixtures_dir, DEFAULT_NAME), index)
    assert [brex.brex_key(c) for c in default_chain] == [DEFAULT_KEY]  # refers to itself


def test_brex_ref_of(fixtures_dir: Path):
    assert brex.brex_ref_of(load(fixtures_dir, APPLIC_NAME)) == PROJECT_KEY
    assert brex.brex_ref_of(xio.load_bytes(b"<dmodule/>")) is None


def test_cycle_is_cut_with_a_warning(tmp_path: Path):
    write_brex(tmp_path, "CYCLEA", "CYCLEB")
    write_brex(tmp_path, "CYCLEB", "CYCLEA")
    index = brex.index_brex([tmp_path])
    notes: list = []
    chain = brex.resolve_chain(dm_xml("CYCLEA"), index, notes)
    assert [brex.brex_key(c)[:6] for c in chain] == ["CYCLEA", "CYCLEB"]
    assert len(notes) == 1 and "cycle" in notes[0].details


def test_unknown_and_missing_references_are_warnings():
    notes: list = []
    assert brex.resolve_chain(dm_xml("NOWHERE"), {}, notes) == []
    assert len(notes) == 1 and "not found" in notes[0].details and not notes[0].ok
    notes = []
    assert brex.resolve_chain(dm_xml(None), {}, notes) == []
    assert "no brexDmRef" in notes[0].details
    assert brex.resolve_chain(dm_xml(None), {}) == []  # warnings argument is optional


def test_chain_depth_is_limited(tmp_path: Path):
    for n in range(12):
        write_brex(tmp_path, f"DEPTH{n:02d}", f"DEPTH{n + 1:02d}")
    index = brex.index_brex([tmp_path])
    notes: list = []
    chain = brex.resolve_chain(dm_xml("DEPTH00"), index, notes)
    assert len(chain) == brex.MAX_DEPTH == 10
    assert len(notes) == 1 and "longer than" in notes[0].details


def test_swap_brex_replaces_or_adds_without_touching_the_original(
    fixtures_dir: Path, tmp_path: Path
):
    index = brex.index_brex([fixtures_dir])
    replacement = tmp_path / "DMC-RTPROTO-AAA-D00-00-00-00AA-022A-D_002-00_EN-US.XML"
    replacement.write_bytes(b"<x/>")
    swapped = brex.swap_brex(index, replacement)
    assert swapped[PROJECT_KEY] == replacement and swapped[DEFAULT_KEY] == index[DEFAULT_KEY]
    assert index[PROJECT_KEY].name == PROJECT_NAME  # original index unchanged
    added = tmp_path / "DMC-NEWONE-AAA-D00-00-00-00AA-022A-D_001-00_EN-US.XML"
    added.write_bytes(b"<x/>")
    assert brex.swap_brex(swapped, added)["NEWONE-AAA-D00-00-00-00AA-022A-D"] == added


def test_swap_rejects_non_brex_file_names(tmp_path: Path):
    with pytest.raises(ValueError):
        brex.swap_brex({}, tmp_path / "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_EN-US.XML")


def test_swapped_brex_changes_the_verdict(fixtures_dir: Path, tmp_path: Path):
    """A BREX swapped into the index is the one the chain resolves to."""
    lenient = tmp_path / PROJECT_NAME
    lenient.write_bytes(brex_xml("RTPROTO", rule("//nothing", 0, "never"), "RTDEFLT"))
    index = brex.swap_brex(brex.index_brex([fixtures_dir]), lenient)
    doc = load(fixtures_dir, VIOLATING_NAME)
    chain = brex.resolve_chain(doc, index)
    assert violations(brex.check_brex(doc, chain)) == []


# --- real Bike data (skipped when data/ is absent) ------------------------------------


def _check_real_chains(repo_root: Path, version: str, default_key: str) -> None:
    data = repo_root / "data" / f"s1000d-{version}"
    index = brex.index_brex([data / "brex"])
    paths = sorted((data / "bike").glob("DMC-*.XML"))
    assert paths and default_key in index
    for path in paths:
        notes: list = []
        chain = brex.resolve_chain(xio.load(path), index, notes)
        assert chain and brex.brex_key(chain[-1]) == default_key, path.name
        assert notes == [], path.name
    results = brex.check_brex(xio.load(paths[0]), brex.resolve_chain(xio.load(paths[0]), index))
    assert results


@pytest.mark.data41
def test_real_bike_41_chains_end_at_the_default_brex(repo_root: Path):
    _check_real_chains(repo_root, "4.1", "S1000D-E-04-10-0301-00A-022A-D")


@pytest.mark.data42
def test_real_bike_42_chains_end_at_the_default_brex(repo_root: Path):
    _check_real_chains(repo_root, "4.2", "S1000D-F-04-10-0301-00A-022A-D")


# --- cache ---------------------------------------------------------------------------------


def test_load_brex_reads_a_file_once_and_again_when_it_changes(fixtures_dir: Path, tmp_path: Path):
    path = tmp_path / PROJECT_NAME
    path.write_bytes((fixtures_dir / PROJECT_NAME).read_bytes())
    brex.clear_cache()
    first = brex.load_brex(path)
    assert brex.load_brex(path) is first
    rules = brex.load_rules(first)
    assert brex.load_rules(first) == rules and brex.load_rules(first) is not rules
    changed = path.read_bytes().replace(b"//proceduralStep/note", b"//proceduralStep/para[1]")
    path.write_bytes(changed)
    second = brex.load_brex(path)
    assert second is not first
    assert [r.xpath for r in brex.load_rules(second)] == ["//proceduralStep/para[1]"]
    assert [r.xpath for r in brex.load_rules(first)] == ["//proceduralStep/note"]


def test_load_rules_of_a_document_not_read_by_load_brex_is_not_cached(fixtures_dir: Path):
    brex.clear_cache()
    doc = xio.load(fixtures_dir / PROJECT_NAME)
    assert len(brex.load_rules(doc)) == 1
    assert brex._RULES == {} and brex._DOCS == {}


def test_resolve_chain_uses_the_cache(fixtures_dir: Path):
    brex.clear_cache()
    index = brex.index_brex([fixtures_dir])
    assert len(index) == 2
    proced = xio.load(fixtures_dir / "DMC-RTPROTO-AAA-D00-00-00-00AA-520A-A_001-00_EN-US.XML")
    first = brex.resolve_chain(proced, index)
    second = brex.resolve_chain(proced, index)
    assert first and all(a is b for a, b in zip(first, second, strict=True))
