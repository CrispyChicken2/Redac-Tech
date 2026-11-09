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

Implémentés depuis la tâche 005 : `s1000d/io.py` et `s1000d/ident.py` (voir la section « Lecture et identification S1000D » ci-dessous), `sources/classify.py`.

Prévus dans `s1000d/` (non encore créés) : `index.py`, `trace.py` et `versioning.py`, `validate.py` et `brex.py` (chaîne BREX, différence base de référence / introduit, `blocked_by_rule`), `diff.py`.

## Lecture et identification S1000D

Modules : `s1000d/io.py`, `s1000d/ident.py`, `sources/classify.py`.

### Lecture sûre (`s1000d/io.py`)

- **Pas d'expansion d'entités, pas de réseau, pas de DTD externe.** Le parseur lxml est configuré avec `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`. Une entité externe (XXE) ou une expansion en cascade reste un nœud de référence d'entité, jamais développé. Les fixtures `tests/fixtures/s1000d/security/` le vérifient.
- **Rien n'est supprimé à la lecture** : commentaires, instructions de traitement et blancs sont conservés (`remove_comments`, `remove_pis`, `remove_blank_text` à faux).
- **Aller-retour octet pour octet.** `load` garde le texte exact de la déclaration XML, du DOCTYPE (sous-ensemble interne compris), du préambule avant la racine, le style de fin de ligne (CRLF ou LF) et le BOM. Tant que l'arbre n'est pas modifié, `dumps` renvoie les octets d'origine à l'identique.
- **Après modification**, `render` reconstruit le document : préambule d'origine réémis tel quel (ou régénéré si un commentaire ou une instruction avant la racine a été modifié), racine sérialisée par lxml, style de fin de ligne et BOM restaurés. Limite : la restauration des fins de ligne ne couvre que les encodages compatibles ASCII.
- **Écriture atomique** (`save`) : fichier temporaire dans le même dossier, puis remplacement.
- **Regex uniquement sur le préambule brut** (encodage déclaré, déclaration) ; jamais sur le contenu XML. Les accès aux éléments passent par XPath ou ElementPath.
- **C14N** (`canonical`) : C14N 1.0 sans commentaires, avec repli sur la sérialisation simple si libxml2 refuse la canonicalisation.

### Identification (`s1000d/ident.py`)

- **DMC** : `DmCode` lit les attributs de `identAndStatusSection/dmAddress/dmIdent/dmCode` (un attribut absent devient une chaîne vide). `dmc_string` produit `MIC-SDC-SYSTEM-SOUSSYS+SOUSSUBSYS-ASSY-DISASSY+VAR-INFO+VAR-LOC`, avec `-LEARNCODE+LEARNEVENTCODE` pour les modules d'apprentissage.
- **issueInfo** et **langue** : `issue_info` renvoie `(issueNumber, inWork)`, `language` renvoie `(languageIsoCode, countryIsoCode)`. Absent : `None`.
- **Règle de détection de l'Issue** (`detect_issue`) : on lit `xsi:noNamespaceSchemaLocation` (à défaut `xsi:schemaLocation`) de la racine. Le segment d'URL qui commence par `S1000D_` donne l'Issue (`S1000D_4-2` → `4.2`). Seules les valeurs `4.1` et `4.2` sont reconnues ; sinon, `None`.
- **Module BREX** (`is_brex`) : code d'information `022`.
- **Noms de fichiers** (`parse_filename`, `build_filename`) : motif `PREFIXE-CODE[_III-WW[_ll-CC]].EXT`, où `III` est le numéro d'issue sur 3 chiffres, `WW` le numéro de travail (in-work) sur 2 chiffres, `ll-CC` la langue et le pays. Le préfixe est normalisé en majuscules. Un nom qui ne correspond pas renvoie `None`. `build_filename(parse_filename(n)) == n` pour les préfixes en majuscules.
- **Nom d'un DM à partir de son contenu** (`filename_for`) : `DMC-<code>_<issue>-<inWork>_<langue>-<pays>.<ext>`. La casse de la langue et de l'extension suit le nom courant du fichier s'il existe, sinon `EN-US` et `XML`.

### Classifieur de sources (`sources/classify.py`)

`classify(path, source_id)` renvoie un `SourceDoc`. Il ne lève jamais d'exception : tout cas inattendu donne le rôle `other`.

| Rôle | Critère | Modifiable |
|---|---|---|
| `icn` | extension graphique (`.cgm`, `.jpg`, `.png`, `.svg`, etc.) ou nom `ICN-` | non |
| `dm` | XML dont la racine est `dmodule`, hors BREX | oui |
| `brex` | `dmodule` avec code d'information `022` | non |
| `pm` | racine `pm`, ou nom `PMC-` si le XML ne se lit pas | oui |
| `ddn` | racine `ddn`, ou nom `DDN-` si le XML ne se lit pas | oui |
| `upf` | racine `dataUpdateFile` ou `updateFile`, ou nom `UPF-` | non |
| `other` | tout le reste, XML illisible compris | oui |

Le rôle `upf` et les rôles `brex` et `icn` sont en lecture seule. `doc_key` est le nom du fichier sans extension ; `issue` vient de `detect_issue` ; `language` vient du DM ou, à défaut, du nom du fichier.

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
