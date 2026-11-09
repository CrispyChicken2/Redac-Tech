"""Identification of S1000D files: DMC, issue, language, Issue detection, file names, roles.

File names are parsed with regular expressions (names only); XML content is read through the
element helpers of ``io`` (no regex on XML content).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from redactech.s1000d import io as xio

XSI = "http://www.w3.org/2001/XMLSchema-instance"
BREX_INFO_CODE = "022"
KNOWN_ISSUES = ("4.1", "4.2")

_DM_CODE_ATTRS = (
    "modelIdentCode",
    "systemDiffCode",
    "systemCode",
    "subSystemCode",
    "subSubSystemCode",
    "assyCode",
    "disassyCode",
    "disassyCodeVariant",
    "infoCode",
    "infoCodeVariant",
    "itemLocationCode",
)
_LEARN_ATTRS = ("learnCode", "learnEventCode")


@dataclass(frozen=True)
class DmCode:
    model_ident_code: str
    system_diff_code: str
    system_code: str
    sub_system_code: str
    sub_sub_system_code: str
    assy_code: str
    disassy_code: str
    disassy_code_variant: str
    info_code: str
    info_code_variant: str
    item_location_code: str
    learn_code: str = ""
    learn_event_code: str = ""

    @classmethod
    def from_element(cls, el: Any) -> DmCode:
        """Build from a ``dmCode`` element; a missing attribute becomes an empty string."""
        values = [el.get(name, "") for name in _DM_CODE_ATTRS + _LEARN_ATTRS]
        return cls(*values)

    def dmc_string(self) -> str:
        """``MIC-SDC-SYSTEM-SUBSUB-ASSY-DISASSY+VAR-INFO+VAR-LOC``, as in S1000D file names.

        Example: ``S1000DBIKE-AAA-DA1-10-00-00AA-251A-A`` (sub and sub-sub system codes are
        written together, as are the disassembly code with its variant and the info code with
        its variant). Learning data modules end with ``-LEARNCODE+LEARNEVENTCODE``
        (for example ``...-952A-T-H31A``).
        """
        parts = [
            self.model_ident_code,
            self.system_diff_code,
            self.system_code,
            self.sub_system_code + self.sub_sub_system_code,
            self.assy_code,
            self.disassy_code + self.disassy_code_variant,
            self.info_code + self.info_code_variant,
            self.item_location_code,
        ]
        if self.learn_code or self.learn_event_code:
            parts.append(self.learn_code + self.learn_event_code)
        return "-".join(parts)


def dm_code(doc: Any) -> DmCode | None:
    """The DM code of a data module (``identAndStatusSection/dmAddress/dmIdent/dmCode``)."""
    el = xio.find(xio.root_of(doc), "identAndStatusSection/dmAddress/dmIdent/dmCode")
    return DmCode.from_element(el) if el is not None else None


def issue_info(doc: Any) -> tuple[str, str] | None:
    """``(issueNumber, inWork)`` of the data module, or None."""
    el = xio.find(xio.root_of(doc), "identAndStatusSection/dmAddress/dmIdent/issueInfo")
    if el is None:
        return None
    return el.get("issueNumber", ""), el.get("inWork", "")


def language(doc: Any) -> tuple[str, str] | None:
    """``(languageIsoCode, countryIsoCode)`` of the data module, or None."""
    el = xio.find(xio.root_of(doc), "identAndStatusSection/dmAddress/dmIdent/language")
    if el is None:
        return None
    return el.get("languageIsoCode", ""), el.get("countryIsoCode", "")


def detect_issue(doc: Any) -> str | None:
    """Detect the S1000D Issue (``"4.1"`` or ``"4.2"``), else None.

    Rule: the ``xsi:noNamespaceSchemaLocation`` (or, failing that, ``xsi:schemaLocation``)
    attribute of the root holds a URL such as
    ``http://www.s1000d.org/S1000D_4-2/xml_schema_flat/proced.xsd``; the path segment that
    starts with ``S1000D_`` gives the Issue (``4-2`` -> ``4.2``). Documents without such a URL
    (or with another Issue) give None.
    """
    root = xio.root_of(doc)
    for attribute in ("noNamespaceSchemaLocation", "schemaLocation"):
        value = root.get(f"{{{XSI}}}{attribute}")
        if not value:
            continue
        for token in value.replace("\\", "/").replace(" ", "/").split("/"):
            if token.startswith("S1000D_"):
                issue = token[len("S1000D_") :].replace("-", ".")
                if issue in KNOWN_ISSUES:
                    return issue
    return None


def is_brex(doc: Any) -> bool:
    """True for a BREX data module (info code 022)."""
    code = dm_code(doc)
    return code is not None and code.info_code == BREX_INFO_CODE


# --- file names ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class FileName:
    """Parts of an S1000D file name; case of ``language``/``country``/``extension`` is kept."""

    prefix: str
    code: str
    issue: str | None = None
    in_work: str | None = None
    language: str | None = None
    country: str | None = None
    extension: str = "XML"


_FILENAME = re.compile(
    r"^(?P<prefix>[A-Za-z]{3})-(?P<code>[^.]+?)"
    r"(?:_(?P<issue>\d{3})-(?P<in_work>\d{2}))?"
    r"(?:_(?P<language>[A-Za-z]{2,3})-(?P<country>[A-Za-z]{2,3}))?"
    r"\.(?P<extension>[A-Za-z0-9]+)$"
)


def parse_filename(name: str) -> FileName | None:
    """Parse ``PREFIX-CODE[_III-WW[_ll-CC]].EXT`` (DMC, DME, DML, DDN, PMC, UPF, ICN, IMF...).

    Tolerant to ``EN-US`` / ``en-US`` and ``.XML`` / ``.xml``. Returns None if ``name`` does not
    look like an S1000D file name. The prefix is normalised to upper case (so the round trip is
    exact for upper-case prefixes).
    """
    found = _FILENAME.match(Path(name).name)
    if not found:
        return None
    parts = found.groupdict()
    parts["prefix"] = parts["prefix"].upper()
    return FileName(**parts)


def build_filename(fn: FileName) -> str:
    """Inverse of ``parse_filename``: ``build_filename(parse_filename(n)) == n``."""
    text = f"{fn.prefix}-{fn.code}"
    if fn.issue is not None:
        text += f"_{fn.issue}-{fn.in_work}"
    if fn.language is not None:
        text += f"_{fn.language}-{fn.country}"
    return f"{text}.{fn.extension}"


def filename_for(doc: Any, issue: int | str, in_work: int | str) -> str:
    """File name of a data module for a given issue and in-work number.

    ``DMC-<code>_<issue>-<inWork>_<lang>-<country>.<ext>``. The case of the language and of the
    extension follows the current file name of ``doc`` when it has one (``en-US``/``EN-US``,
    ``.xml``/``.XML``); otherwise ``EN-US`` and ``XML``.
    """
    code = dm_code(doc)
    lang = language(doc)
    if code is None or lang is None:
        raise ValueError("not a data module: no dmCode or language")
    current = parse_filename(doc.path.name) if getattr(doc, "path", None) else None
    language_code, country_code = lang
    extension = "XML"
    if current is not None:
        extension = current.extension
        if current.language is not None and current.language.islower():
            language_code = language_code.lower()
        else:
            language_code = language_code.upper()
        country_code = country_code.upper()
    else:
        language_code, country_code = language_code.upper(), country_code.upper()
    return build_filename(
        FileName(
            prefix="DMC",
            code=code.dmc_string(),
            issue=f"{int(issue):03d}",
            in_work=f"{int(in_work):02d}",
            language=language_code,
            country=country_code,
            extension=extension,
        )
    )
