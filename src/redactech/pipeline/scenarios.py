"""End-to-end scenarios: run A0 on an input, compare the outputs with ``attendu.yaml``.

A scenario is a folder ``<root>/<name>/`` with

* ``scenario.yaml``: the source (copies of fixtures, or the real Bike data), the request (mapping
  rows written to a CSV, or a form), the version policy, the decisions, the time limit and the
  optional ``markers`` (``data41`` ...) a scenario needs;
* ``attendu.yaml``: what must come out, written BEFORE running from the input files (never from
  the tool's output): the expected changes, the outputs' file names, the documents that must stay
  identical, counts, blocked proposals.

``variants`` (in ``scenario.yaml``) run the same scenario several times (for instance one run per
version policy); ``attendu.yaml`` then holds ``variants: {<id>: {<key>: <override>}}``.

Metrics (``Result.metrics``, all in [0, 1] except ``seconds``): ``exhaustiveness`` (expected
changes found), ``precision`` (changed elements that were expected), ``preservation`` (documents
that had to stay untouched and did), ``validity`` (outputs valid against the XSD),
``traceability`` (changed outputs whose marks and reasons for update are consistent).
A scenario passes when every check passes.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import shutil
import time
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

from redactech.agents import a7_checker
from redactech.llm import FakeLLM
from redactech.models import SourceRef
from redactech.pipeline import orchestrator as orch
from redactech.s1000d import diff, validate
from redactech.s1000d import io as xio
from redactech.s1000d.ops._common import xml_of
from redactech.sources import workspace as wsmod

DAY = datetime.date(2025, 3, 7)  # fixed "today": the issue dates must not depend on the clock
IDENT_PREFIX = "/dmodule/identAndStatusSection"  # issueInfo, dmStatus and trace elements
MARKER_DIRS = {"data41": "data/s1000d-4.1/bike", "data42": "data/s1000d-4.2/bike"}


@dataclass
class Result:
    name: str
    variant: str | None = None
    failures: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    introduced: int = 0
    pre_existing: int = 0
    skipped: str | None = None

    @property
    def passed(self) -> bool:
        return self.skipped is None and not self.failures

    @property
    def label(self) -> str:
        return self.name if self.variant is None else f"{self.name}[{self.variant}]"


# --- loading ------------------------------------------------------------------


def discover(root: Path | str) -> list[Path]:
    """Scenario folders under ``root`` (sorted); folders starting with ``_`` are support files."""
    base = Path(root)
    return sorted(
        d for d in base.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "scenario.yaml").is_file()
    )


def _yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: a mapping was expected")
    return data


def variants_of(directory: Path | str) -> list[str | None]:
    """Variant ids of a scenario (``[None]`` when it has none)."""
    scenario = _yaml(Path(directory) / "scenario.yaml")
    found = [v["id"] for v in scenario.get("variants", [])]
    return found or [None]


def load(directory: Path | str, variant: str | None = None) -> tuple[dict, dict]:
    """The scenario and its expectations with the variant applied."""
    folder = Path(directory)
    scenario = _yaml(folder / "scenario.yaml")
    attendu = _yaml(folder / "attendu.yaml")
    overrides = attendu.pop("variants", {})
    if variant is not None:
        chosen = next((v for v in scenario.get("variants", []) if v["id"] == variant), None)
        if chosen is None:
            raise ValueError(f"{folder.name}: unknown variant {variant!r}")
        scenario = {**scenario, **{k: v for k, v in chosen.items() if k != "id"}}
        attendu = {**attendu, **overrides.get(variant, {})}
    return scenario, attendu


def missing_markers(scenario: dict, repo_root: Path | str) -> list[str]:
    """Markers of the scenario whose data is not there (the scenario is then skipped)."""
    root = Path(repo_root)
    return [m for m in scenario.get("markers", []) if not (root / MARKER_DIRS[m]).is_dir()]


# --- source, request ----------------------------------------------------------


def _digest(folder: Path) -> dict[str, str]:
    return {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(folder.iterdir()) if f.is_file()
    }


def _prepare_source(scenario: dict, directory: Path, work: Path, repo_root: Path):
    """The workspace file and the source folder (a copy for fixtures, the data itself else)."""
    spec = scenario["source"]
    if spec["kind"] == "fixtures":
        fixtures = directory.parent.parent / "fixtures" / "s1000d"
        folder = work / "src"
        folder.mkdir(parents=True)
        for name in spec["files"]:
            shutil.copy(fixtures / name, folder / Path(name).name)  # name may be in a subfolder
        patch = scenario.get("brex_patch")
        if patch:  # a modified copy of a BREX: the original fixture is never touched
            target = folder / patch["doc"]
            text = target.read_text(encoding="utf-8")
            if patch["old"] not in text:
                raise ValueError(f"brex_patch: {patch['old']!r} not found in {patch['doc']}")
            target.write_text(text.replace(patch["old"], patch["new"]), encoding="utf-8")
        brex, schemas = [folder.resolve()], None
    else:  # the real Bike data: read in place, never modified (checked by digest)
        data = repo_root / spec["path"]
        folder = data.resolve()
        brex = [(repo_root / p).resolve() for p in spec.get("brex_dirs", [])]
        schemas = (repo_root / spec["schemas_dir"]).resolve() if spec.get("schemas_dir") else None
    issue = spec.get("issue", "4.1")
    source = wsmod.Source("scenario", folder.resolve(), brex, issue, True, schemas)
    ws_file = wsmod.save_workspace(wsmod.Workspace([source], work), work / "ws.toml")
    return ws_file, folder


def _request(scenario: dict, work: Path) -> orch.RunRequest:
    spec = scenario["request"]
    auto = bool(scenario.get("decisions", {}).get("auto_accept", False))
    if "free_text" in spec:  # read by a language model (the recorded one unless one is given)
        return orch.RunRequest(free_text=spec["free_text"], auto_accept=auto)
    if "mapping" in spec:
        rows = spec["mapping"]
        columns = list(dict.fromkeys(key for row in rows for key in row))
        lines = [";".join(columns)] + [";".join(str(r.get(c, "")) for c in columns) for r in rows]
        path = work / "mapping.csv"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return orch.RunRequest(mapping=str(path), auto_accept=auto)
    form = copy.deepcopy(spec["form"])
    for item in form if isinstance(form, list) else [form]:
        target = item.get("target") or {}
        if "doc" in target:  # a file name is easier to write than a reference
            name = target.pop("doc")
            target["ref"] = {"source_id": "scenario", "doc_key": name.removesuffix(".XML")}
    return orch.RunRequest(form=form, auto_accept=auto)


# --- running ------------------------------------------------------------------


def run_scenario(
    directory: Path | str,
    work: Path | str,
    variant: str | None = None,
    repo_root: Path | str | None = None,
    provider: Any = None,
) -> Result:
    """Run one scenario (or one variant) in ``work`` and compare with ``attendu.yaml``.

    A free-text scenario is read by ``provider``; by default the recorded answers of
    ``tests/llm_cassettes/`` (no model is called).
    """
    folder, work_dir = Path(directory).resolve(), Path(work)
    root = Path(repo_root) if repo_root is not None else folder.parents[2]
    scenario, attendu = load(folder, variant)
    result = Result(folder.name, variant)
    missing = missing_markers(scenario, root)
    if missing:
        result.skipped = f"missing data ({', '.join(missing)})"
        return result
    if scenario.get("pending"):
        result.skipped = f"expectations still to write: {scenario['pending']}"
        return result
    started = time.perf_counter()
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        ws_file, source_dir = _prepare_source(scenario, folder, work_dir, root)
    except (KeyError, ValueError, OSError) as exc:
        result.failures.append(f"the source could not be prepared: {exc}")
        return result
    before_files = _digest(source_dir)
    try:
        if "free_text" in scenario["request"] and provider is None:
            provider = FakeLLM(folder.parent.parent / "llm_cassettes")
        run = orch.start(
            _request(scenario, work_dir), ws_file, work_dir / "runs", token="e000",
            provider=provider,
        )
        run.run_to_review()
        decisions = scenario.get("decisions", {})
        if decisions.get("auto_accept"):
            run.auto_accept()
        zones = {z.id: z for z in run.state.zones}
        for proposal in list(run.state.proposals):
            zone = zones.get(proposal.zone_id)
            wanted = decisions.get("accept_certainty", [])
            if proposal.status == "proposed" and zone and zone.kind == "content":
                if zone.certainty in wanted:
                    run.decide(proposal.id, "accepted", "scenario", actor="auto")
        policy = scenario.get("version_policy", "none")
        run.set_policy(run.suggestion().model_copy(update={"mode": policy}))
        written = run.write(today=DAY)
    except (orch.PipelineError, ValueError, OSError) as exc:
        result.failures.append(f"the run failed: {exc}")
        result.metrics["seconds"] = round(time.perf_counter() - started, 3)
        return result
    result.metrics["seconds"] = round(time.perf_counter() - started, 3)
    _compare(result, run, written.written, attendu, folder, source_dir, before_files)
    limit = scenario.get("max_seconds")
    if limit is not None and result.metrics["seconds"] > limit:
        result.failures.append(f"too slow: {result.metrics['seconds']}s > {limit}s")
    return result


# --- comparison ---------------------------------------------------------------


def _path(el: Any) -> str:
    return el.getroottree().getpath(el)


def _inside(path: str, scopes: list[str]) -> bool:
    return any(path == s or path.startswith(s + "/") for s in scopes)


def _text(el: Any) -> str:
    return xml_of(el)


def _ratio(done: int, total: int) -> float:
    return 1.0 if total == 0 else round(done / total, 3)


def _original_of(run: orch.Run) -> dict[str, str]:
    """Output file name -> key of its source document (from the write log)."""
    found: dict[str, str] = {}
    for event in run.state.decisions_log:
        if event.get("event") == "written":
            for entry in event.get("log", []):
                found[entry["new_name"]] = entry["doc"]
    return found


def _compare(
    result: Result,
    run: orch.Run,
    written: list[Path],
    attendu: dict,
    folder: Path,
    source_dir: Path,
    before_files: dict[str, str],
) -> None:
    fail = result.failures.append
    names = sorted(p.name for p in written)
    if "outputs" in attendu and names != sorted(attendu["outputs"]):
        fail(f"output files {names} differ from the expected {sorted(attendu['outputs'])}")
    origin = _original_of(run)
    expected_by_doc: dict[str, list[dict]] = {}
    for change in attendu.get("changes", []):
        expected_by_doc.setdefault(change["doc"], []).append(change)

    found = total_expected = 0
    in_scope = all_changed = 0
    valid = traced = changed_outputs = 0
    pairs: dict[str, tuple[Any, Any]] = {}
    for path in sorted(written):
        key = origin.get(path.name)
        doc = run.index.docs.get(key) if key else None
        if doc is None:
            fail(f"{path.name}: not produced from a known document")
            continue
        original, output = xio.load(doc.path), xio.load(path)
        name = Path(doc.path).name
        pairs[name] = (original, output)
        changed = [
            p for p in diff.changed_elements(original, output) if not p.startswith(IDENT_PREFIX)
        ]
        scopes: list[str] = []
        for expected in expected_by_doc.get(name, []):
            total_expected += 1
            ok, scope_paths = _check_change(expected, original, output, fail, name)
            found += ok
            scopes += scope_paths
        exact: set[str] = set()  # containers whose layout changes: only themselves, not below
        for extra in attendu.get("also_allowed", {}).get(name, []):
            side = original if extra.get("side") == "before" else output
            paths = [_path(e) for e in xio.xpath(side.tree, extra["xpath"])]
            if extra.get("exact"):
                exact.update(paths)
            else:
                scopes += paths
        all_changed += len(changed)
        in_scope += sum(1 for p in changed if _inside(p, scopes) or p in exact)
        for p in changed:
            if not _inside(p, scopes) and p not in exact:
                fail(f"{path.name}: unexpected change at {p}")
        for expr, count in attendu.get("output_counts", {}).get(name, {}).items():
            got = len(xio.xpath(output.tree, expr))
            if got != count:
                fail(f"{path.name}: {expr} matches {got} element(s), expected {count}")
        valid += _valid(attendu, folder, run, doc, output, fail, path.name)
        if changed:
            changed_outputs += 1
            traced += _traceable(output, fail, path.name)
        _count_checks(result, run, doc, output, path)
    for name, expected in expected_by_doc.items():
        if not any(origin.get(p.name) and Path(run.index.docs[origin[p.name]].path).name == name
                   for p in written):
            total_expected += len(expected)
            fail(f"{name}: expected changes but no output was written for it")

    preserved = _preservation(attendu, run, source_dir, before_files, fail)
    result.metrics.update(
        exhaustiveness=_ratio(found, total_expected),
        precision=_ratio(in_scope, all_changed),
        preservation=preserved,
        validity=_ratio(valid, len(written)),
        traceability=_ratio(traced, changed_outputs),
    )
    limits = attendu.get("checks", {})
    wanted = limits.get("introduced_errors", 0)
    if result.introduced != wanted:
        fail(f"{result.introduced} introduced error(s), expected {wanted}")
    least = limits.get("pre_existing_min", 0)
    if result.pre_existing < least:
        fail(f"{result.pre_existing} pre-existing problem(s), at least {least}")
    blocked = sum(1 for p in run.state.proposals if p.status == "blocked_by_rule")
    if blocked != attendu.get("blocked", 0):
        fail(f"{blocked} blocked proposal(s), expected {attendu.get('blocked', 0)}")
    _check_blocked(attendu, run, fail)
    _check_free_text(attendu, run, written, fail)
    _check_baseline(attendu, run, fail)
    _check_illustrations(attendu, run, pairs, fail)


def _check_change(
    expected: dict, original: Any, output: Any, fail, name: str
) -> tuple[int, list[str]]:
    """1 if the expected change is there, and the path(s) of its scope in the output."""
    label = f"{name}: {expected['scope_xpath']}"
    before = []
    if "before_xpath" in expected:
        before = xio.xpath(original.tree, expected["before_xpath"])
    if "before_xpath" in expected and not before:
        fail(f"{label}: the 'before' element is not in the input (attendu inconsistent)")
    for needle in expected.get("before_contains", []):
        if not any(needle in _text(e) for e in before):
            fail(f"{label}: the input element does not contain {needle!r} (attendu inconsistent)")
    scopes = xio.xpath(output.tree, expected["scope_xpath"])
    if not scopes:
        fail(f"{label}: not found in the output")
        return 0, []
    ok = True
    text = "".join(_text(e) for e in scopes)
    for needle in expected.get("after_contains", []):
        if needle not in text:
            fail(f"{label}: {needle!r} is missing from the output")
            ok = False
    for needle in expected.get("after_absent", []):
        if needle in text:
            fail(f"{label}: {needle!r} is still in the output")
            ok = False
    marks = expected.get("marks")
    if marks:
        marked = [e for s in scopes for e in s.iter() if isinstance(e.tag, str)
                  and all(e.get(k) == str(v) for k, v in marks.items())]
        if not marked:
            fail(f"{label}: no element with the marks {marks}")
            ok = False
    return int(ok), [_path(s) for s in scopes]


def _valid(
    attendu: dict, folder: Path, run: orch.Run, doc: Any, output: Any, fail, name: str
) -> int:
    mode = attendu.get("xsd", "minimal")
    if mode == "minimal":
        schema = validate.load_schema(folder.parent / "_schemas" / "dmodule.xsd")
        if schema.validate(xio.tree_of(output)):
            return 1
        fail(f"{name}: not valid against the minimal schema: {schema.error_log.last_error}")
        return 0
    source = run.index.sources[doc.ref.source_id]
    if source.schemas_dir is None:
        fail(f"{name}: no schemas folder for the XSD check")
        return 0
    results = validate.check_xsd(output, source.schemas_dir)
    errors = [r for r in results if not r.ok]
    for r in errors:
        fail(f"{name}: XSD {r.severity}: {r.details}")
    return int(not errors)


def _traceable(output: Any, fail, name: str) -> int:
    """Every change mark has a change type and references existing reasons for update."""
    ids = {e.get("id") for e in xio.xpath(output.tree, "//reasonForUpdate")}
    marked = xio.xpath(output.tree, "//*[@changeMark='1']")
    if not marked or not ids:
        fail(f"{name}: no change mark or no reasonForUpdate")
        return 0
    bad = []
    for el in marked:
        refs = set((el.get("reasonForUpdateRefIds") or "").split())
        if not el.get("changeType") or not refs or not refs <= ids:
            bad.append(el)
    for el in bad:
        fail(f"{name}: {_path(el)} has marks that do not match a reasonForUpdate")
    return int(not bad)


def _count_checks(result: Result, run: orch.Run, doc: Any, output: Any, path: Path) -> None:
    ref = SourceRef(source_id=doc.ref.source_id, doc_key=path.stem)
    for r in a7_checker.check_doc(output, run.index, run.state.baseline, original=doc.ref, ref=ref):
        if r.origin == "introduced" and r.severity == "error":
            result.introduced += 1
        elif r.origin == "pre_existing":
            result.pre_existing += 1


def _preservation(
    attendu: dict, run: orch.Run, source_dir: Path, before_files: dict[str, str], fail
) -> float:
    """Sources never change; the documents listed in ``unchanged`` are not produced either."""
    patterns = attendu.get("unchanged", [])
    now = _digest(source_dir)
    produced = {Path(run.index.docs[k].path).name for k in _original_of(run).values()}
    kept = total = 0
    for name in sorted(before_files):
        if not any(fnmatch(name, pattern) for pattern in patterns):
            continue
        total += 1
        problems = []
        if now.get(name) != before_files[name]:
            problems.append("its source file changed")
        if name in produced:  # compare SOURCE names: outputs may be renamed
            problems.append("an output was produced for it")
        if problems:
            fail(f"{name} must stay untouched: {', '.join(problems)}")
        else:
            kept += 1
    for name in before_files:  # no source may ever change
        if now.get(name) != before_files[name] and not any(fnmatch(name, p) for p in patterns):
            fail(f"{name}: a source file was modified")
    return _ratio(kept, total)


def _check_blocked(attendu: dict, run: orch.Run, fail) -> None:
    """Blocked proposals: attempts, the rule shown, the question pre-filled on the operation."""
    for spec in attendu.get("blocked_details", []):
        wanted = spec["operation"]
        found = [p for p in run.state.proposals
                 if p.status == "blocked_by_rule" and p.operation_id == wanted]
        if not found:
            fail(f"{wanted}: no blocked proposal")
            continue
        proposal = found[0]
        if "attempts" in spec and proposal.attempt != spec["attempts"]:
            fail(f"{wanted}: {proposal.attempt} attempt(s), expected {spec['attempts']}")
        rules = [c.rule for c in proposal.checks if c.rule and not c.ok]
        if "rule_xpath" in spec and not any(r.get("xpath") == spec["rule_xpath"] for r in rules):
            fail(f"{wanted}: the rule {spec['rule_xpath']} is not shown in the checks")
        questions = [q for o in run.state.operations if o.id == wanted for q in o.questions]
        for needle in spec.get("question_contains", []):
            if not any(needle in q for q in questions):
                fail(f"{wanted}: no question contains {needle!r}")


def _check_free_text(attendu: dict, run: orch.Run, written: list[Path], fail) -> None:
    """Questions raised by the interpretation, and values that must never reach an output."""
    asked = run.free_text_questions()
    least = attendu.get("questions_min", 0)
    if len(asked) < least:
        fail(f"{len(asked)} free-text question(s), at least {least} expected")
    for needle in attendu.get("question_contains", []):
        if not any(needle in question for question in asked):
            fail(f"no free-text question contains {needle!r}")
    for value in attendu.get("absent_in_outputs", []):
        for path in written:
            if value in Path(path).read_text(encoding="utf-8"):
                fail(f"{Path(path).name}: the invented value {value!r} was written")
        if any(value in str(op.params) for op in run.state.operations):
            fail(f"the invented value {value!r} is in an operation")


def _check_baseline(attendu: dict, run: orch.Run, fail) -> None:
    """Number of BREX failures found before any change (the chains were re-resolved)."""
    spec = attendu.get("baseline_brex")
    if not spec:
        return
    count = sum(1 for r in run.state.baseline if r.name == "brex" and not r.ok)
    if "min" in spec and count < spec["min"]:
        fail(f"{count} BREX failure(s) in the baseline, at least {spec['min']} expected")
    if "max" in spec and count > spec["max"]:
        fail(f"{count} BREX failure(s) in the baseline, at most {spec['max']} expected")


def _check_illustrations(attendu: dict, run: orch.Run, pairs: dict, fail) -> None:
    """A figure linked to a modified element is flagged 'to check' and left unchanged."""
    for spec in attendu.get("illustrations", []):
        figure = spec["figure_id"]
        zones = [z for z in run.state.zones if z.kind == "illustration" and z.element_id == figure]
        if not zones:
            fail(f"{figure}: no illustration zone")
            continue
        for wanted in spec.get("operations", []):
            if not any(z.operation_id == wanted for z in zones):
                fail(f"{figure}: not flagged through {wanted}")
        zone = zones[0]
        proposal = next((p for p in run.state.proposals if p.zone_id == zone.id), None)
        flagged = proposal is not None and any(
            c.name == "illustration" and c.severity == "warning" for c in proposal.checks
        )
        if zone.certainty != "to_check" or not flagged:
            fail(f"{figure}: not flagged as 'to check'")
        before, after = pairs.get(spec["doc"], (None, None))
        if before is None:
            fail(f"{figure}: no output for {spec['doc']}")
            continue
        old, new = (xio.xpath(d.tree, f"//*[@id='{figure}']") for d in (before, after))
        if not old or not new or xml_of(old[0]) != xml_of(new[0]):
            fail(f"{figure}: the figure changed")


# --- report -------------------------------------------------------------------


def report_markdown(results: list[Result], day: datetime.date) -> str:
    """The ``runs/eval_<date>.md`` table."""
    lines = [
        f"# Scenario evaluation {day.isoformat()}",
        "",
        "| scenario | status | exhaustiveness | precision | preservation | validity "
        "| traceability | introduced / pre-existing | time (s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r.skipped:
            lines.append(f"| {r.label} | skipped: {r.skipped} | | | | | | | |")
            continue
        m = r.metrics
        lines.append(
            f"| {r.label} | {'PASS' if r.passed else 'FAIL'} | {m.get('exhaustiveness', '')} "
            f"| {m.get('precision', '')} | {m.get('preservation', '')} | {m.get('validity', '')} "
            f"| {m.get('traceability', '')} | {r.introduced} / {r.pre_existing} "
            f"| {m.get('seconds', '')} |"
        )
    for r in results:
        for message in r.failures:
            lines.append(f"- {r.label}: {message}")
    return "\n".join(lines) + "\n"
