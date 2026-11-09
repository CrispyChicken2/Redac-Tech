# Architecture

Ce document décrit l'organisation du paquet `redactech`, les contrats de données partagés, les clés de configuration, la CLI et les marqueurs de tests. Il reflète l'état après la tâche 002 : les modules métier sont encore des squelettes, et la CLI renvoie « not implemented yet ».

## Principe directeur

L'IA propose, le code applique, les contrôles vérifient, le rédacteur décide. Le LLM ne réécrit jamais un document : il produit des opérations typées en JSON, appliquées par du code.

## Organisation du paquet

Racine : `src/redactech/`. Chaque sous-paquet porte un rôle défini par la section 11 de la spécification (fichier local, non suivi).

| Module | Rôle | État |
|---|---|---|
| `__init__.py` | version du paquet (`__version__`) | implémenté |
| `models.py` | contrats de données partagés (voir ci-dessous) | implémenté |
| `config.py` | chargement de `config.toml`, valeurs par défaut si absent | implémenté |
| `cli.py` | interface en ligne de commande (Typer), point d'entrée `redactech` | squelette |
| `s1000d/` | traitement S1000D : lecture XML sûre, identification, index, opérations, traçabilité, validation, diff | squelette |
| `s1000d/ops/` | une fonction pure par type d'opération | squelette |
| `sources/` | description du workspace et classification des documents | squelette |
| `render/` | rendu : vue XML, vue publiée (XSLT), vue côte à côte | squelette |
| `agents/` | agents de proposition et de critique | squelette |
| `pipeline/` | enchaînement des étapes d'une demande | squelette |
| `report/` | rapports de run | squelette |
| `ui/` | interface Streamlit | squelette |
| `llm/` | accès au LLM local (Ollama) ; tous les appels LLM passent ici (M3) | squelette |

Prévu dans `s1000d/` (non encore créé) : `io.py` (lecture et écriture lxml durcies, DOCTYPE, entités, commentaires et fins de ligne préservés), `ident.py` (DMC, issueInfo, langue, détection de l'issue, rôle des fichiers), `index.py`, `trace.py` et `versioning.py`, `validate.py` et `brex.py` (chaîne BREX, différence base de référence / introduit, `blocked_by_rule`), `diff.py` (C14N).

## Contrats de données (`models.py`)

Modèles pydantic v2 partagés par tous les modules. Une ligne par modèle :

- `SourceRef` : référence stable d'un document (`source_id`, `doc_key`).
- `SourceDoc` : description d'un document source (genre, rôle, issue, langue, chaîne BREX, accessibilité en écriture, chemin).
- `SourceSpan` : passage source cité (document, bornes optionnelles, citation exacte) justifiant une opération.
- `Target` : cible d'une opération (référence, XPath optionnel, identifiant d'élément optionnel).
- `Operation` : opération typée proposée par le LLM ou par le code (13 genres, dont `replace_part`, `insert_step`, `update_ref`, `fix_violation`, `translate_dm`), avec justification, sources, confiance et questions.
- `Zone` : zone impactée détectée, avec certitude (`certain`, `probable`, `to_check`) et origine (`code`, `llm`, `user`).
- `CheckResult` : résultat d'un contrôle (XSD, BREX, intégrité, liens, identifiants, véracité, applicabilité, ICN, illustration, normes d'écriture), avec origine `pre_existing` ou `introduced`.
- `VersionPolicy` : politique de version (`none`, `in_work`, `new_issue`), suggérée et appliquée, globale ou par document.
- `Critique` : avis d'un critique sur une proposition (`ok`, doute éventuel).
- `Proposal` : proposition de changement XML avant/après, avec contrôles, critique, statut (`proposed`, `accepted`, `edited`, `rejected`, `pending_client`, `blocked_by_rule`) et historique de tentatives.
- `Conflict` : conflit à arbitrer (trois voies ou inter-documents), avec options et choix.
- `RunState` : état d'un run (identifiant, mode, politique de version, référence de base, étape courante, opérations, zones, propositions, conflits, journal des décisions).

## Configuration (`config.toml`)

Fichier à la racine du dépôt, suivi par git. Chargé par `config.py` ; si le fichier est absent, les valeurs par défaut s'appliquent.

Section `[llm]` (utilisée à partir de M3) :

- `provider` : fournisseur LLM ; `"none"` = repli sans IA, `"ollama"` en M3.
- `model` : nom du modèle local ; une seule ligne à changer pour en changer.
- `temperature` : température de génération (0 par défaut).
- `max_retries` : nombre de nouvelles tentatives d'un appel LLM.
- `timeout_s` : délai maximal d'un appel LLM, en secondes.

Section `[trace]` :

- `delete_mode` : mode de suppression (`"mark"` : marquer, ne pas supprimer).
- `consolidate_on_new_issue` : consolider les changements lors d'une nouvelle issue.
- `default_version_policy` : politique par défaut (`"ask"` : l'interface demande ; CLI et tests passent une valeur).
- `marks_when_none` : marquer les changements même sans politique de version (question ouverte).
- `upf_policy` : traitement des fichiers UPF (`"read_only"`).
- `max_alternatives` : nombre maximal d'alternatives proposées.
- `max_rule_retries` : nombre maximal de nouvelles tentatives sur une règle BREX avant `blocked_by_rule`.

Section `[workspace]` :

- `file` : fichier décrivant le workspace (`workspace.toml`, ignoré par git ; modèle dans `workspace.example.toml`).

## Workspace (`workspace.example.toml`)

Modèle à copier en `workspace.toml` (ignoré par git). Chaque `[[sources]]` décrit une source : `id`, `path`, `brex_dirs`, `issue`, `writable`. Le modèle référence les jeux publics S1000D et un dossier de fixtures de test.

## CLI (`cli.py`)

Point d'entrée : `redactech`. Toutes les commandes sont des squelettes qui affichent « not implemented yet » et quittent avec le code 2.

| Commande | Rôle prévu |
|---|---|
| `workspace init` | créer `workspace.toml` depuis l'exemple |
| `workspace add PATH [--id ID]` | ajouter une source |
| `workspace list` | lister les sources |
| `index` | indexer le workspace |
| `baseline` | lancer les contrôles de référence (problèmes préexistants) |
| `request [--mapping F] [--version-policy P] [--out D]` | créer un run à partir d'une demande de changement |
| `review RUN_DIR` | relire les propositions d'un run |
| `write RUN_DIR` | écrire les changements acceptés |
| `check OUT_DIR` | contrôler les documents produits |
| `render DOC [--view xml\|published\|both] [--show-deleted]` | rendre un document |
| `eval SCENARIOS` | évaluer les scénarios de `tests/scenarios/` |

## Marqueurs de tests

Déclarés dans `pyproject.toml`, appliqués par `tests/conftest.py` (les tests concernés sont sautés avec une raison explicite) :

- `data41` : nécessite les données Bike S1000D 4.1 dans `data/s1000d-4.1/bike`.
- `data42` : nécessite les données Bike S1000D 4.2 dans `data/s1000d-4.2/bike`.
- `ollama` : nécessite un serveur Ollama local et `REDACTECH_OLLAMA=1`.
- `slow` : test lent.
- `ui` : nécessite Streamlit importable.

Fixtures communes : `repo_root`, `fixtures_dir` (`tests/fixtures/s1000d`), `tmp_run_dir` (dossier `runs/test_run` temporaire).

Les tests de contrats (`tests/test_models.py`), de configuration (`tests/test_config.py`) et de CLI (`tests/test_cli.py`) sont écrits. Ils n'ont pas été exécutés sur ce poste (règle machine : pas de pytest).
