# Contributing

## Workflow

1. Pick a task file (`tasks/NNN.md`) or a ticket issue. Read `CLAUDE.md` first.
2. Create a branch from `main` (one task = one branch).
3. **Tests first**: write the tests described in the task, then the code.
4. Run `pytest -q` and `ruff check .` until both are clean.
5. Commit with an imperative English message that references the task or ticket.
6. A reviewer checks the branch and answers `OK` or `KO` with numbered findings; fix every finding on the same branch.
7. The lead merges, only after an `OK` verdict and a green CI. Do not merge or push to `main` yourself.

## Privacy

Nothing private may reach git or GitHub: see `CLAUDE.md` section 3 and `docs/PRIVACY.md`.
Use Bike data or fictitious examples only. Install the local hooks once:

```bash
python tools/install_hooks.py
```

Every `gh` write goes through `tools/gh_safe.py`.

## Commands

```bash
pip install -e ".[dev]"     # or: uv sync
pytest -q                   # tests (no network, no Ollama, no data needed)
ruff check .                # lint
python tools/privacy.py scan --tracked
```

## Tests

- Les tests (`pytest`) et le lint (`ruff check .`) sont exécutés par la CI GitHub à chaque push. C'est la référence.
- En local, sur le poste de développement, seules ces vérifications sont autorisées :

```bash
py -3 -m compileall -q src tools tests     # compilation de tout le code Python
py -3 tools/privacy.py scan --tracked      # contrôle de confidentialité
```

- Ne pas lancer `pytest`, `uv` ni `pip` en local sur ce poste, et ne rien télécharger pour les tests.

## Conventions

- Python 3.11+, `pathlib`, explicit UTF-8, Windows-safe code.
- XML is edited with lxml only, never with regex or string operations.
- LLM calls live only in `src/redactech/llm/`.
- Shared contracts (`models.py`, `config.toml`, `pyproject.toml`, `conftest.py`, `cli.py`) are owned by the lead: describe the change you need in your PR instead of editing them.
