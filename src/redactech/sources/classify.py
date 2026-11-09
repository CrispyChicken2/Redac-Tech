"""Classification of workspace files into ``SourceDoc`` roles (dm, brex, pm, ddn, upf, icn)."""

from __future__ import annotations

from pathlib import Path

from redactech.models import SourceDoc, SourceRef
from redactech.s1000d import ident
from redactech.s1000d import io as xio

READ_ONLY_ROLES = {"brex", "upf", "icn", "pm", "ddn"}
GRAPHIC_EXTENSIONS = {".cgm", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".svg", ".gif"}
UPF_ROOTS = {"dataUpdateFile", "updateFile"}
PREFIX_ROLES = {"PMC": "pm", "DDN": "ddn", "UPF": "upf"}


def _language_tag(language: tuple[str, str] | None, name: ident.FileName | None) -> str | None:
    if language and language[0]:
        return f"{language[0]}-{language[1]}" if language[1] else language[0]
    if name is not None and name.language:
        country = f"-{name.country}" if name.country else ""
        return f"{name.language}{country}"
    return None


def classify(path: Path | str, source_id: str = "") -> SourceDoc:
    """Describe the file at ``path``. Never raises: anything unexpected becomes role ``other``.

    * graphic extensions or an ``ICN-`` name -> role ``icn``, kind ``graphic``, not writable;
    * XML whose root is ``dmodule`` -> ``dm``, or ``brex`` (info code 022, not writable);
    * root ``pm`` / ``ddn`` -> ``pm`` / ``ddn``, not writable (a ``PMC-`` / ``DDN-`` name is a
      fallback);
    * root ``dataUpdateFile`` (or a ``UPF-`` name) -> ``upf``, not writable;
    * anything else, unreadable or garbled -> ``other``.
    ``doc_key`` is the file name without extension; ``issue`` comes from ``detect_issue``.
    """
    p = Path(path)
    ref = SourceRef(source_id=source_id, doc_key=p.stem)
    base = {"ref": ref, "path": str(p)}
    try:
        name = ident.parse_filename(p.name)
        prefix = name.prefix if name else ""
        if p.suffix.lower() in GRAPHIC_EXTENSIONS or prefix == "ICN":
            return SourceDoc(**base, kind="graphic", role="icn", writable=False)
        if p.suffix.lower() != ".xml":
            return SourceDoc(**base, kind="other", role="other")
        try:
            doc = xio.load(p)
        except Exception:
            role = PREFIX_ROLES.get(prefix, "other")
            return SourceDoc(**base, kind="other", role=role, writable=role not in READ_ONLY_ROLES)
        root_tag = str(doc.root.tag)
        issue = ident.detect_issue(doc)
        if root_tag == "dmodule":
            lang = _language_tag(ident.language(doc), name)
            role = "brex" if ident.is_brex(doc) else "dm"
            return SourceDoc(
                **base, kind="s1000d", role=role, issue=issue, language=lang,
                writable=role != "brex",
            )
        if root_tag == "pm" or prefix == "PMC":
            return SourceDoc(**base, kind="s1000d", role="pm", issue=issue,
                             language=_language_tag(None, name), writable=False)
        if root_tag == "ddn" or prefix == "DDN":
            return SourceDoc(**base, kind="s1000d", role="ddn", issue=issue, writable=False)
        if root_tag in UPF_ROOTS or prefix == "UPF":
            return SourceDoc(**base, kind="s1000d", role="upf", issue=issue,
                             language=_language_tag(None, name), writable=False)
        return SourceDoc(**base, kind="xml", role="other", issue=issue)
    except Exception:
        return SourceDoc(ref=ref, path=str(p), kind="other", role="other")
