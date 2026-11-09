"""Sanity checks of the synthetic fixtures (stdlib only; lxml-based checks come later)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

NAME = re.compile(
    r"^(?:DMC|UPF)-[A-Z0-9]{2,14}-[A-Z0-9]{3}-[A-Z0-9]{3}-[A-Z0-9]{2}-[A-Z0-9]{2}-[A-Z0-9]{4}"
    r"-[A-Z0-9]{4}-[A-Z0-9]_\d{3}-\d{2}_[A-Z]{2}-[A-Z]{2}\.XML$"
)
CODE = "AAA-D00-00-00-00AA"


def fx(fixtures_dir: Path, model: str, info: str, loc: str, issue: str = "001-00") -> Path:
    prefix = "UPF" if info == "UPF" else "DMC"
    info = "0A3A" if info == "UPF" else info
    return fixtures_dir / f"{prefix}-{model}-{CODE}-{info}-{loc}_{issue}_EN-US.XML"


def parse(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def all_xml(fixtures_dir: Path) -> list[Path]:
    return sorted(fixtures_dir.glob("*.XML"))


def test_expected_number_of_fixtures(fixtures_dir: Path):
    assert len(all_xml(fixtures_dir)) == 10


def test_all_fixtures_parse(fixtures_dir: Path):
    for path in all_xml(fixtures_dir):
        ET.parse(path)


def test_file_names_match_the_dmc_pattern(fixtures_dir: Path):
    for path in all_xml(fixtures_dir):
        assert NAME.match(path.name), path.name


def test_security_fixtures_exist_but_are_not_parsed(fixtures_dir: Path):
    sec = fixtures_dir / "security"
    xxe = (sec / "xxe.xml").read_text(encoding="utf-8")
    assert "<!ENTITY xxe SYSTEM" in xxe
    lol = (sec / "billion_laughs.xml").read_text(encoding="utf-8")
    assert "<!ENTITY lol9" in lol and "&lol9;" in lol


def _brex_target(root: ET.Element) -> str:
    code = root.find(".//dmStatus/brexDmRef/dmRef/dmRefIdent/dmCode")
    assert code is not None
    a = code.attrib
    return (
        f"{a['modelIdentCode']}-{a['systemDiffCode']}-{a['systemCode']}-"
        f"{a['subSystemCode']}{a['subSubSystemCode']}-{a['assyCode']}-"
        f"{a['disassyCode']}{a['disassyCodeVariant']}-{a['infoCode']}{a['infoCodeVariant']}-"
        f"{a['itemLocationCode']}"
    )


def _by_dmc(fixtures_dir: Path, key: str) -> Path:
    matches = [p for p in all_xml(fixtures_dir) if p.name.startswith(f"DMC-{key}_")]
    assert len(matches) == 1, key
    return matches[0]


def test_brex_chain_applic_to_project_to_default(fixtures_dir: Path):
    applic_dm = parse(fx(fixtures_dir, "RTPROTO", "040A", "A"))
    project_key = _brex_target(applic_dm)
    assert project_key.endswith("-022A-D") and project_key.startswith("RTPROTO-")
    project = _by_dmc(fixtures_dir, project_key)
    default_key = _brex_target(parse(project))
    assert default_key.startswith("RTDEFLT-") and default_key.endswith("-022A-D")
    default = _by_dmc(fixtures_dir, default_key)
    assert _brex_target(parse(default)) == default_key  # the default-like BREX points to itself


def test_default_brex_has_flags_0_1_2_and_object_values(fixtures_dir: Path):
    root = parse(fx(fixtures_dir, "RTDEFLT", "022A", "D"))
    flags = {p.get("allowedObjectFlag") for p in root.iter("objectPath")}
    assert flags == {"0", "1", "2"}
    assert any(p.text == "//dmStatus/qualityAssurance" for p in root.iter("objectPath"))
    assert len(list(root.iter("objectValue"))) >= 2


def test_project_brex_forbids_note_in_step(fixtures_dir: Path):
    root = parse(fx(fixtures_dir, "RTPROTO", "022A", "D"))
    paths = {p.text: p.get("allowedObjectFlag") for p in root.iter("objectPath")}
    assert paths == {"//proceduralStep/note": "0"}


def test_procedure_has_five_steps_and_requirements(fixtures_dir: Path):
    root = parse(fx(fixtures_dir, "RTPROTO", "520A", "A"))
    ids = [s.get("id") for s in root.iter("proceduralStep")]
    assert ids == [f"stp-000{n}" for n in range(1, 6)]
    assert root.find(".//preliminaryRqmts/reqSupportEquips") is not None
    assert root.find(".//preliminaryRqmts/reqSupplies") is not None
    assert root.find(".//preliminaryRqmts/reqSpares//partNumber").text == "X2"
    assert root.find(".//closeRqmts") is not None
    kinds = {r.get("internalRefTargetType") for r in root.iter("internalRef")}
    assert {"irtt04", "irtt05", "irtt06"} <= kinds


def test_ipd_entries(fixtures_dir: Path):
    root = parse(fx(fixtures_dir, "RTPROTO", "941A", "D"))
    assert len(list(root.iter("catalogSeqNumber"))) == 3
    assert len(list(root.iter("itemSeqNumber"))) == 3
    refs = {r.get("partNumberValue") for r in root.iter("partRef")}
    assert {"LRU1010", "X2"} <= refs


def test_comrep_declares_parts(fixtures_dir: Path):
    root = parse(fx(fixtures_dir, "RTPROTO", "0A3A", "D"))
    parts = {p.get("partNumberValue") for p in root.findall(".//partRepository/partSpec/partIdent")}
    assert parts == {"LRU1010", "X2"}
    assert root.find(".//toolRepository") is not None
    assert root.find(".//supplyRepository") is not None


def test_upf_mentions_lru1010(fixtures_dir: Path):
    path = fx(fixtures_dir, "RTPROTO", "UPF", "D")
    assert path.name.startswith("UPF-")
    root = parse(path)
    assert root.tag == "dataUpdateFile"
    assert "LRU1010" in "".join(root.itertext())


def test_applic_fixture_has_two_asserts(fixtures_dir: Path):
    root = parse(fx(fixtures_dir, "RTPROTO", "040A", "A"))
    values = [a.get("applicPropertyValues") for a in root.iter("assert")]
    assert values == ["A", "B"]


def test_figure_fixture_has_crlf_pi_comment_and_icn_entity(fixtures_dir: Path):
    data = fx(fixtures_dir, "RTPROTO", "041A", "A").read_bytes()
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")  # no bare LF
    assert b"<?Pub Caret?>" in data
    assert b"<!--" in data
    assert re.search(rb"<!ENTITY ICN-[A-Z0-9-]+ SYSTEM", data)
    assert b'infoEntityIdent="ICN-' in data


def test_violating_fixture_has_note_in_step_and_unknown_element(fixtures_dir: Path):
    root = parse(fx(fixtures_dir, "RTPROTO", "521A", "A"))
    assert root.find(".//proceduralStep/note") is not None
    assert root.find(".//mainProcedure/unknownElement") is not None


def test_change_marks_fixture(fixtures_dir: Path):
    root = parse(fx(fixtures_dir, "RTPROTO", "520B", "A", issue="007-00"))
    info = root.find(".//dmIdent/issueInfo")
    assert (info.get("issueNumber"), info.get("inWork")) == ("007", "00")
    types = {s.get("changeType") for s in root.iter("proceduralStep") if s.get("changeMark")}
    assert types == {"add", "modify", "delete"}
    rfu_ids = {r.get("id") for r in root.iter("reasonForUpdate")}
    assert rfu_ids
    refs = {s.get("reasonForUpdateRefIds") for s in root.iter("proceduralStep")} - {None}
    assert refs <= rfu_ids


ALLOWED_PART_NUMBERS = {"LRU1010", "LRU2020", "X2", "X3", "FAKE-PN-001"}


def test_only_fictitious_part_numbers_used(fixtures_dir: Path):
    found: set[str] = set()
    for path in all_xml(fixtures_dir):
        for element in parse(path).iter():
            if element.tag == "partNumber" and element.text:
                found.add(element.text.strip())
            value = element.get("partNumberValue")
            if value:
                found.add(value)
    assert found, "no part number found in the fixtures"
    assert found <= ALLOWED_PART_NUMBERS, sorted(found - ALLOWED_PART_NUMBERS)
    assert {"LRU1010", "X2", "FAKE-PN-001"} <= found
