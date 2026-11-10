"""Self-contained HTML of a delivery report: inline CSS, no script, no external resource.

Every value that comes from the run (file names, comments, XML excerpts, rule texts) goes
through ``html.escape``; the page makes no request and contains no link.
"""

from __future__ import annotations

from html import escape
from typing import Any

from redactech.report.build import CheckEntry, DocumentReport, Report, rule_text

CSS = (
    "body{font-family:sans-serif;margin:2rem;color:#222;line-height:1.4}"
    "h1{font-size:1.5rem}h2{font-size:1.2rem;margin-top:2rem;border-bottom:1px solid #ccc}"
    "table{border-collapse:collapse;width:100%;margin:.5rem 0}"
    "th,td{border:1px solid #ccc;padding:.3rem .5rem;text-align:left;vertical-align:top}"
    "th{background:#f2f2f2}code,pre{font-family:monospace;font-size:.85rem;white-space:pre-wrap}"
    ".introduced{color:#a00;font-weight:bold}.pre_existing{color:#666}"
    ".none{color:#666;font-style:italic}"
)


def e(value: Any) -> str:
    """Escaped text of any value (None is empty)."""
    return escape("" if value is None else str(value), quote=True)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """A table whose cells are already escaped HTML."""
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _none(text: str = "none") -> str:
    return f'<p class="none">{e(text)}</p>'


def _checks(entries: list[CheckEntry], css: str) -> str:
    if not entries:
        return _none()
    rows = [
        [e(c.name), e(c.severity), f'<span class="{css}">{e(c.details)}</span>',
         e(rule_text(c.rule)), f"<code>{e(c.xpath)}</code>"]
        for c in entries
    ]
    return _table(["check", "severity", "details", "rule", "where"], rows)


def _document(doc: DocumentReport) -> str:
    new = doc.new_name or "(no file written)"
    parts = [
        f"<h3>{e(doc.old_name)} &rarr; {e(new)}</h3>",
        f"<p>Policy applied: {e(doc.policy or '-')}</p>",
    ]
    rows = [
        [e(c.proposal_id), e(c.operation), e(c.change_type), e(c.status),
         "yes" if c.written else "no", f"<pre>{e(c.before)}</pre>", f"<pre>{e(c.after)}</pre>",
         e(c.comment)]
        for c in doc.changes
    ]
    parts.append(
        _table(["proposal", "operation", "type", "status", "written", "before", "after",
                "comment"], rows)
        if rows else _none("no change")
    )
    return "".join(parts)


def _issues(report: Report) -> str:
    """Per document: what the changes introduced, and what was already there."""
    parts = []
    for doc in report.documents:
        parts.append(
            f"<h3>{e(doc.old_name)}</h3>"
            "<h4>Introduced by the changes</h4>" + _checks(doc.introduced, "introduced")
            + "<h4>Already in the document</h4>" + _checks(doc.pre_existing, "pre_existing")
        )
    return "".join(parts) or _none("no document")


def _delivered(report: Report) -> str:
    """The check of the written files: the REQ-11 statement and one row per file."""
    if not report.outputs:
        return _none("no file written")
    total = report.counts.delivered_introduced_errors or 0
    rows = [
        [e(o.file), e(o.introduced_errors), e(o.introduced_warnings), e(o.pre_existing),
         e(o.error)]
        for o in report.outputs
    ]
    return (
        f"<p><b>{e(total)} introduced error(s)</b> in the {e(len(report.outputs))} "
        "delivered file(s).</p>"
        + _table(["file", "introduced errors", "introduced warnings", "pre-existing", "problem"],
                 rows)
    )


def render_html(report: Report) -> str:
    """The report as one HTML page."""
    c = report.counts
    policy = report.version_policy
    summary = _table(
        ["accepted", "edited", "rejected", "pending customer", "blocked by rule",
         "still undecided", "introduced issues", "pre-existing issues"],
        [[str(n) for n in (c.accepted, c.edited, c.rejected, c.pending_client, c.blocked,
                           c.proposed, c.introduced, c.pre_existing)]],
    )
    if policy is None:
        versioning = _none("no versioning policy chosen")
    else:
        reasons = "".join(f"<li>{e(r)}</li>" for r in policy.reasons)
        per_doc = "".join(f"<li>{e(k)}: {e(v)}</li>" for k, v in policy.per_doc.items())
        versioning = (
            f"<p>Mode: <b>{e(policy.mode)}</b> (suggested: {e(policy.suggested)})</p>"
            f"<ul>{reasons}</ul>" + (f"<p>Per document:</p><ul>{per_doc}</ul>" if per_doc else "")
        )
    documents = "".join(_document(d) for d in report.documents) or _none("no document")
    if report.skipped:
        documents += "<h3>Skipped</h3>" + _table(
            ["proposal", "reason"],
            [[e(s.get("proposal")), e(s.get("reason"))] for s in report.skipped],
        )
    blocked = (
        _table(
            ["proposal", "document", "attempts", "rule", "question"],
            [[e(b.proposal_id), e(b.document), e(b.attempts), e(rule_text(b.rule)),
              e(b.question)] for b in report.blocked],
        )
        if report.blocked else _none()
    )
    illustrations = (
        _table(
            ["proposal", "document", "figure", "reason", "status"],
            [[e(i.proposal_id), e(i.document), e(i.figure_id), e(i.reason), e(i.status)]
             for i in report.illustrations],
        )
        if report.illustrations else _none()
    )
    questions = (
        _table(
            ["id", "document", "element", "question / comment", "status", "rule"],
            [[e(q.id), e(q.document), e(q.element), e(q.text), e(q.status), e(q.rule)]
             for q in report.questions],
        )
        if report.questions else _none()
    )
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>Delivery report {e(report.run_id)}</title><style>{CSS}</style></head><body>"
        f"<h1>Delivery report</h1><p>Run <code>{e(report.run_id)}</code><br>"
        f"Workspace <code>{e(report.workspace)}</code></p>"
        f"<h2>Summary</h2>{summary}"
        f"<h2>Versioning</h2>{versioning}"
        f"<h2>Changes per document</h2>{documents}"
        f"<h2>Pre-existing and introduced issues</h2>{_issues(report)}"
        f"<h2>Check of the delivered files</h2>{_delivered(report)}"
        f"<h2>Blocked requests</h2>{blocked}"
        f"<h2>Illustrations to check</h2>{illustrations}"
        f"<h2>Pending questions</h2>{questions}"
        "</body></html>\n"
    )
