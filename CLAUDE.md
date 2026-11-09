# CLAUDE.md — Permanent rules of the RedacTech repo

> Read automatically by every Claude Code session. Detailed spec: `.agents/SPEC.md` in the main checkout (local, never committed). Thresholds: `QUALITY.md`.

## 1. The project
RedacTech is a **local** assistant that updates existing S1000D technical documentation: it finds every impacted element, proposes traced changes, checks them (XSD, BREX), lets the writer review them git-style, and writes valid DMs.
**Guiding principle:** the AI proposes, the code applies, the checks verify, the writer decides.

## 2. Dev team (Herdr) and work tracking
- ORCH (lead pane, autonomous) publishes milestones, `spec` and ticket issues, owns shared contracts, merges; the only agent that reads `.agents/MISSION.md`.
- CODER reads `.agents/SPEC.md` + its ticket, works in `.worktrees/t<issue#>/` on branch `t<issue#>-<slug>`, tests first, opens a PR with `Closes #<issue#>`.
- REVIEWER posts a PR review comment starting with `VERDICT: APPROVE` or `VERDICT: CHANGES_REQUESTED`; never edits code.
- DOCS (Haiku) updates README, docs/ and QUALITY.md evidence at milestone end.
- Squash-merge only after APPROVE + green CI. Commits reference their ticket. All `gh` writes go through `tools/gh_safe.py`.

## 3. Privacy (NON-NEGOTIABLE)
1. Nothing about the project's client or its people may appear anywhere tracked by git or visible on GitHub (files, file names, comments, tests, fixtures, prompts, docs, commits, branches, tags, issues, PRs, reviews, CI logs, screenshots): no company, person, sector, programme, equipment, editor or validator names, no meeting content, no requirement attributed to the client. Use Bike or fictitious examples.
2. The local denylist is enforced by pre-commit, commit-msg and pre-push hooks, `tools/gh_safe.py`, a CI secret scan and tests. `.agents/` is local only.
3. Public or fictitious data only. Local AI only (Ollama on localhost); all LLM calls through `src/redactech/llm/`; model = one config line.
4. Never commit: `data/` (except `data/README.md`), `runs/`, `.cache/`, `.agents/`, `.worktrees/`, `workspace.toml`, `output/`, `outputs/`, `*.zip`, `*.docx`, `*.pdf`, `*.mp4`, `.env`, keys, downloaded XSDs.

## 4. Engineering rules
- Python ≥ 3.11, lxml (hardened parser), pydantic v2, pytest, ruff, typer, Streamlit.
- Never edit XML with regex or strings; preserve DOCTYPE, entities, comments, processing instructions, line endings.
- The LLM never rewrites a document: typed JSON operations, applied by code; every introduced value is traceable to its source.
- No change written without a human decision (`--auto-accept` only in tests, impossible in the UI).
- Modified DMs: issueInfo + file name per the chosen versioning policy; `changeMark="1"` + `changeType`; `reasonForUpdate`. Delete = mark and keep; only a new issue consolidates.
- Checks on input and output: pre-existing vs introduced; 0 introduced error to deliver; a request the BREX forbids becomes `blocked_by_rule`, never an endless retry.
- UPF files, BREX DMs, graphics and `data/` are never modified.
- Tests first; CI without Ollama, data or network (FakeLLM). Windows-safe code (`pathlib`, UTF-8).
- QUALITY.md *Result/Evidence* updated only with evidence, using the real REQ/OBJ ids.

## 5. Commands
```bash
uv sync                      # or: pip install -e ".[dev]"
pytest -q
redactech --help
streamlit run src/redactech/ui/app.py
```
