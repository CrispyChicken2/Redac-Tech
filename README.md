# RedacTech

RedacTech is a **local** assistant that updates existing S1000D technical documentation: it finds every impacted
element, proposes traced changes, checks them (XSD, BREX), lets the writer review them git-style, and writes valid
data modules.

The guiding principle: **the AI proposes, the code applies, the checks verify, the writer decides.** At this stage of
the prototype, requests come from a mapping table or a structured form and every step is done by code; the local
language model is a later, optional addition (all model calls will go through `src/redactech/llm/`).

**Status: prototype, Document mode.** Everything runs on your machine, with public or fictitious data only.

## Install and run

Python 3.11 or later. Three commands, from the root of the repository:

```bash
pip install -e ".[dev]"                  # or: uv sync
py -3 tools/setup_data.py                # builds data/ from the two public S1000D archives (Issue 4.1 and 4.2)
streamlit run src/redactech/ui/app.py    # opens the interface in the browser
```

Notes:

- `py -3` is the Windows launcher; use `python` on Linux or macOS.
- `tools/setup_data.py` reads `S1000D Issue 4.1.zip` and `S1000D Issue 4.2.zip` (public archives, not part of the
  repository; `--archives-dir` and `--data-dir` change the folders, `--dry-run` only lists). It is needed for the Bike
  data sets; the synthetic fixtures in `tests/fixtures/s1000d/` work without it.
- In the interface, type the path of a workspace file in the sidebar and press **Charger le projet**. The default is
  `workspace.toml` if it exists, else `workspace.example.toml`.
- Nothing leaves the machine. `data/`, `runs/` and your workspace file are ignored by git.

## Command line quick start

The same pipeline is available without the interface (`redactech --help` lists every command):

```bash
redactech workspace init                                                    # workspace.toml from the example
redactech request --mapping lots.csv --version-policy in_work --out runs/   # prepare the proposals
redactech review runs/<id> --accept-all                                     # decide (or --accept / --reject ID ...)
redactech write runs/<id>                                                   # write the data modules into runs/<id>/out
redactech check runs/<id>/out                                               # introduced vs pre-existing problems
```

`lots.csv` has the columns `old;new` (optionally `kind` and `reason`). Other commands: `redactech index`,
`redactech baseline`, `redactech render <dm.xml> --view both`, `redactech eval tests/scenarios/`. A step-by-step
walkthrough, command line and interface, is in [docs/DEMO.md](docs/DEMO.md).

## Architecture

An orchestrated pipeline with a typed shared state (`RunState`, saved in `runs/<id>/state.json`). The interface and the
command line are thin layers on top of the orchestrator: they hold no business logic.

```text
   Streamlit UI (src/redactech/ui/)            CLI (src/redactech/cli.py)
                    \                          /
                     v                        v
        +--------------------------------------------------------+
        | A0  pipeline orchestrator (pipeline/orchestrator.py)   |
        |     state machine, checkpoints, persistence, resume    |
        +--------------------------------------------------------+
           |
           v
   A1 indexer  -->  A2 request  -->  A4 locator  -->  A5 preparer  -->  A7 checker  -->  A11 writer
   index +          mapping or       every           before / after     XSD, BREX,        decided changes
   baseline         form ->          occurrence      proposals,         integrity,        -> new data modules
   (pre-existing)   operations       (+ figures)     blocked_by_rule    pre-existing      with traceability
                                                                        vs introduced
           \_______________________________  s1000d/ (lxml I/O, ops, BREX, traceability)  ______/

   Views and delivery: render/ (XML, published via XSLT 1.0, side by side), report/ (HTML + JSON report,
   questions CSV/XLSX, decisions log)
```

Product agents (`src/redactech/agents/`):

- **A0** Pipeline orchestrator: state machine, persists the run, stops at the checkpoints (operations, then proposals).
- **A1** Workspace indexer: builds the corpus index and the baseline of pre-existing problems.
- **A2** Request interpreter: turns a mapping table or a form into typed operations with their source.
- **A4** Locator: finds every occurrence impacted by an operation, and flags linked figures to check.
- **A5** Change preparer: builds before/after proposals and alternatives; `blocked_by_rule` when the BREX forbids a change.
- **A7** Checker: XSD, BREX, integrity, ids, links, ICN; separates pre-existing from introduced problems.
- **A11** Writer: writes the decided changes with traceability (change marks, reasons for update, versioning).
- **A10** Chat assistant: not built yet (see [docs/ROADMAP_NEXT.md](docs/ROADMAP_NEXT.md)).

Rules that hold everywhere: documents are edited with lxml only (never regex or string edits on XML); the model never
rewrites a document; nothing is written without a human decision; source files, UPF files, BREX data modules and
`data/` are never modified.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): package layout, data contracts, configuration, deliverables of a run.
- [docs/DEMO.md](docs/DEMO.md): command line and interface walkthrough.
- [docs/SCENARIOS.md](docs/SCENARIOS.md): end-to-end scenarios and `redactech eval`.
- [docs/PRIVACY.md](docs/PRIVACY.md): what must never reach git or GitHub.
- [docs/ROADMAP_NEXT.md](docs/ROADMAP_NEXT.md): what is left out of the prototype and the known gaps.
- [QUALITY.md](QUALITY.md): requirements and objectives with their evidence. [CONTRIBUTING.md](CONTRIBUTING.md): how to
  contribute.
