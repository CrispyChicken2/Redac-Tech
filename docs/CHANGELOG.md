# Journal des modifications

## 002 — Contrats et squelette

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `pyproject.toml` : paquet `redactech` (Python ≥ 3.11), dépendances, extras `dev`, script `redactech`, configuration pytest (marqueurs `data41`, `data42`, `ollama`, `slow`, `ui`) et ruff.
- `config.toml` : réglages par défaut des sections `[llm]`, `[trace]` et `[workspace]`.
- `workspace.example.toml` : modèle de workspace, à copier en `workspace.toml` (ignoré par git).
- `src/redactech/models.py` : contrats pydantic partagés (sources, opérations, zones, contrôles, politique de version, critiques, propositions, conflits, état de run).
- `src/redactech/config.py` : chargement de `config.toml` avec valeurs par défaut.
- `src/redactech/cli.py` : interface Typer ; toutes les commandes sont des squelettes (« not implemented yet », code de sortie 2).
- Squelette du paquet : sous-paquets `s1000d/` (et `s1000d/ops/`), `sources/`, `render/`, `agents/`, `pipeline/`, `report/`, `ui/`, `llm/`, chacun avec un `__init__.py` de présentation.
- `tests/conftest.py` : marqueurs de tests dépendants de l'environnement (données, Ollama, Streamlit), sautés avec une raison explicite ; fixtures communes.
- `tests/test_models.py`, `tests/test_config.py`, `tests/test_cli.py` : tests des contrats, de la configuration et de la CLI.
- `docs/ARCHITECTURE.md` : organisation du paquet, contrats de données, clés de configuration, commandes CLI, marqueurs de tests.

### Tests écrits, non exécutés

Les tests de contrats, de configuration et de CLI ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils doivent être lancés par le chef de projet une fois les dépendances installées.

### Non couvert

- Aucun comportement métier : les modules `s1000d/`, `sources/`, `render/`, `agents/`, `pipeline/`, `report/`, `ui/` et `llm/` sont des squelettes.
- Les commandes de la CLI ne font rien pour l'instant.

## 001 — Hygiène et confidentialité

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `tools/privacy.py` : contrôle des termes interdits (liste locale `.agents/denylist.txt`, non suivie) sur le contenu, les noms de fichiers, les messages de commit, les noms de branches et les tags. Les résultats sont masqués. Commandes `scan --tracked`, `scan --staged`, `scan --text-file`.
- `tools/hooks/pre_commit.py`, `tools/hooks/commit_msg.py`, `tools/hooks/pre_push.py` : contrôles appelés par git avant commit et avant push.
- `tools/install_hooks.py` : installation idempotente des trois hooks dans `.git/hooks/` (partagés par tous les worktrees).
- `tools/gh_safe.py` : wrapper de `gh` qui contrôle arguments, fichiers de corps et entrée standard avant tout appel. Refuse d'agir sans liste de termes, sauf réglage explicite.
- `.gitignore` : exclusion de `.agents/`, des worktrees, des caches, des archives, des données et des sorties générées.
- `CLAUDE.md` : règles permanentes du dépôt (rôles, confidentialité, règles d'ingénierie, commandes).
- `data/README.md` : seul fichier suivi du dossier `data/`, décrit l'origine des données publiques et leur reconstruction locale.
- `tests/security/test_privacy_tools.py` : tests unitaires des fonctions de contrôle, des hooks, de l'installeur et de `gh_safe`, avec des termes fictifs.
- `tests/security/test_privacy.py` : audit du dépôt réel (aucun terme interdit dans les fichiers suivis, aucun chemin interdit suivi, aucune archive suivie, `.agents/` exclu).

### Tests écrits, non exécutés

Les tests de `tests/security/` ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. La vérification repose sur la relecture statique et sur la compilation des fichiers Python. Ils doivent être lancés par le chef de projet une fois les dépendances installées.

### Non couvert

- Pas de remote distant : la CI GitHub n'est pas exécutable pour l'instant.
- Le contrôle ne vaut que pour les termes présents dans la liste locale.
