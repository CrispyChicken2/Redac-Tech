# RedacTech

RedacTech is a **local** assistant that updates existing S1000D technical documentation: it finds every impacted
element, proposes traced changes, checks them (XSD, BREX), lets the writer review them git-style, and writes valid
data modules.

**Status: prototype in progress.**

## Install and run

Placeholder, at most three commands (to be confirmed once the UI exists):

```bash
uv sync                      # or: pip install -e ".[dev]"
redactech --help
streamlit run src/redactech/ui/app.py
```

## Architecture

An orchestrated pipeline with a typed shared state. Product agents (`src/redactech/agents/`):

- **A0** Pipeline orchestrator: state machine, persists the run, stops at the checkpoints.
- **A1** Workspace indexer: builds the corpus index and the baseline checks.
- **A2** Request interpreter: turns a mapping or form into operations (free text with a local LLM later).
- **A4** Locator: finds every occurrence impacted by an operation.
- **A5** Change preparer: builds before/after proposals, `blocked_by_rule` when the BREX forbids a change.
- **A7** Checker: XSD, BREX, integrity, separating pre-existing from introduced problems.
- **A10** Chat assistant: message to operations or answers computed by code (later).
- **A11** Writer: writes the decided changes, the report and the questions export.

More documentation will live in [docs/](docs/). Quality requirements: [QUALITY.md](QUALITY.md). Contributing:
[CONTRIBUTING.md](CONTRIBUTING.md).
