# Journal des modifications

## 008 — Opérations et propositions

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/s1000d/ops/` : 8 opérations, fonctions pures sur une copie de l'arbre : `replace_part`, `replace_text`, `insert_step`, `delete_step`, `move_step`, `update_ref`, `add_requirement`, `remove_requirement`. Les suppressions désignent l'élément sans rien enlever (marquage à l'écriture).
- `src/redactech/agents/a2_mapping.py` : lecture des tables de correspondances CSV (`;` ou `,`, UTF-8) et XLSX (colonnes `old`, `new`, `kind`, `reason`), et des demandes structurées. Chaque opération garde la citation source de sa ligne ; une ligne incomplète fait refuser la table entière.
- `src/redactech/agents/a4_locator.py` : localisation exhaustive des occurrences d'un numéro de pièce (`certain` pour les structurées, `probable` pour le texte libre), documents en lecture seule ignorés et listés avec leur raison, illustrations liées signalées `to_check`.
- `src/redactech/agents/a5_preparer.py` : propositions avant / après sur copie en mémoire, avertissement sur les illustrations, alternatives calculées après rejet (première ou dernière mention, position voisine), plafonnées par `max_alternatives`.
- Tests : `tests/s1000d/test_ops.py`, `tests/agents/test_a2_mapping.py`, `tests/agents/test_a4_locator.py`, `tests/agents/test_a5_preparer.py`.
- `docs/ARCHITECTURE.md` : section « Demande, localisation et propositions » (opérations et paramètres, format de la table, niveaux de certitude, illustrations, alternatives).

### Tests écrits, non exécutés

Les tests ci-dessus ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- 5 genres d'opération de l'enum du modèle ne sont pas implémentés : `update_applic`, `update_value`, `write_steps`, `fix_violation`, `translate_dm`. Ils lèvent `OpError`.
- Les tables de correspondances n'acceptent que `replace_part` et `replace_text`.
- Le paramètre `max_alternatives` doit être passé par l'appelant depuis `config.toml` ; il n'est pas lu automatiquement.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 007 — Workspace, index, baseline

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/sources/workspace.py` : fichier `workspace.toml` (lecture, écriture, ajout de source, création depuis `workspace.example.toml`), balayage des dossiers source et BREX, dossier `schemas` voisin détecté par défaut.
- `src/redactech/s1000d/index.py` : `CorpusIndex` (documents, chaînes BREX, occurrences de numéros de pièce par genre, texte libre, liens internes, références de DM, figures, documents illisibles) et recherche `find_part` par mot entier.
- `src/redactech/agents/a1_indexer.py` : indexation du corpus et baseline des problèmes préexistants (`origin="pre_existing"`), un fichier défaillant ne bloque pas le reste.
- CLI : `workspace init`, `workspace add`, `workspace list`, `index`, `baseline`. Options `--workspace`, `--brex-dir`, `--id`, `--force`.
- `docs/ARCHITECTURE.md` : section « Workspace, index et baseline », avec les commandes et un exemple de `workspace.toml`.

### Tests écrits, non exécutés

Les tests du workspace, de l'index, de la baseline et de la CLI ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- Les commandes `request`, `review`, `write`, `check`, `render` et `eval` restent des squelettes (« not implemented yet », code `2`).
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 006 — Contrôles XSD/BREX

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/s1000d/validate.py` : contrôle XSD par version d'Issue (schémas plats locaux, jamais téléchargés, compilés une fois par chemin), intégrité du `dmodule`, identifiants en double, liens `internalRef`, entités ICN. Convention : un résultat `info` `ok=True` quand rien n'est trouvé ; seuls les `ok=False` sont comptés.
- `src/redactech/s1000d/brex.py` : règles BREX des flags 0, 1 et 2, avec `objectValue` (valeurs exactes, intervalles, expressions régulières) ; résolution de la chaîne de BREX via `brexDmRef` jusqu'au BREX par défaut ; index des BREX par nom de fichier ; remplacement d'un BREX dans l'index. Un XPath invalide ou un BREX inconnu donne un avertissement, jamais une exception.
- `src/redactech/s1000d/diff.py` : comparaison C14N de deux documents et liste des éléments modifiés (appariement par `@id`, sinon par position sous l'ancêtre identifié ; ancêtres d'un changement non signalés).
- `tests/fixtures/s1000d/` : fixtures rendues conformes aux schémas. Le fichier des pièces communes est scindé en trois DM (pièces, outils, fournitures) ; la structure UPF est corrigée.
- `docs/ARCHITECTURE.md` : section « Contrôles » (convention des résultats, sémantique des flags BREX, résolution de la chaîne, comparaison C14N).

### Tests écrits, non exécutés

Les tests des contrôles, des règles BREX et de la comparaison ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- Pas d'adaptateur vers un validateur BREX externe (`s1kd-brexcheck` ou équivalent) : l'évaluateur interne est la seule référence.
- La distinction « préexistant / introduit » et `blocked_by_rule` ne sont pas encore câblées (couche pipeline).
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 005 — io, identification, classifieur

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/s1000d/io.py` : lecture XML durcie avec lxml (pas d'expansion d'entités, pas de réseau, pas de DTD externe), aller-retour octet pour octet tant que l'arbre n'est pas modifié, préambule conservé (déclaration, DOCTYPE, commentaires et instructions avant la racine, fins de ligne, BOM), réécriture contrôlée après modification, écriture atomique, C14N sans commentaires.
- `src/redactech/s1000d/ident.py` : DMC (`DmCode`, `dmc_string`), `issueInfo`, langue, détection de l'Issue (`4.1` / `4.2`) à partir de l'URL de schéma de la racine, module BREX (code `022`), analyse et construction des noms de fichiers S1000D, nom d'un DM à partir de son contenu.
- `src/redactech/sources/classify.py` : classifieur de sources aux rôles `dm`, `brex`, `pm`, `ddn`, `upf`, `icn` et `other`. Les rôles `brex`, `upf` et `icn` sont en lecture seule. Ne lève jamais d'exception.
- `tests/s1000d/test_io.py`, `tests/s1000d/test_ident.py`, `tests/sources/test_classify.py` : tests des aller-retours, des fixtures de sécurité (entité externe et expansion en cascade jamais développées), de la détection de l'Issue, des noms de fichiers et des rôles.

### Tests écrits, non exécutés

Les tests ci-dessus ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- Les tests sur les données Bike réelles (`test_real_bike_41_round_trip`, `test_real_bike_42_round_trip`) dépendent de `data/` et sont sautés si les données manquent.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 022 — CI verte

**Statut :** fusionnée. **Tests exécutés uniquement par la CI GitHub** (aucun test sur ce poste). Le statut de la CI sur GitHub n'est pas vérifié depuis ce poste : pas de remote configuré.

### Modifié

- Lint corrigé : erreurs `ruff` corrigées dans le code et les tests.
- `.github/workflows/ci.yml` : les étapes sont indépendantes. Les tests tournent même si le lint échoue (`if: always()`), avec `pytest -q --maxfail=50 -rA` pour lister tous les résultats.
- `tools/setup_data.py` : durcissement de l'extraction (`tests/test_setup_data.py` étendu, 33 lignes ajoutées).
- Petites corrections dans `tools/gh_safe.py`, `tools/privacy.py`, `tools/hooks/pre_push.py` et `tests/security/test_privacy_tools.py`, `tests/test_fixtures.py`.

### Documentation

- `CONTRIBUTING.md` : section « Tests » ajoutée. Les tests sont exécutés par la CI GitHub ; en local, seulement `compileall` et le scan de confidentialité.

### Non couvert

- Pas de remote distant sur ce poste : la CI n'a pas pu être lancée depuis ce poste.

## 004 — Données Bike et fixtures

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `tools/setup_data.py` : reconstruit `data/` à partir des deux archives publiques S1000D placées à la racine du dépôt (`S1000D Issue 4.1.zip`, `S1000D Issue 4.2.zip`). Les archives ne sont ni modifiées ni suivies. Options `--dry-run`, `--archives-dir`, `--data-dir`.
  - Résultat attendu : `bike/` 152 (4.1) et 155 (4.2), `brex/` 2 et 2, `schemas/` 30 et 32.
  - Refus avant toute écriture des membres d'archive au chemin absolu, avec lettre de lecteur ou `..` (protection contre le zip-slip).
  - Idempotent : relancer ne modifie que les fichiers qui ont changé.
- `tests/fixtures/s1000d/` : fixtures synthétiques, fictives, de type Issue 4.1 (valeurs `FAKE-PN-001`, `X2`, `X3`, `LRU1010`, `LRU2020`, identifiant de modèle `RTPROTO`). Aucun fichier Bike n'est copié. Inclut deux fichiers de sécurité (entité externe, expansion d'entités) qui ne doivent jamais être développés.
- `tests/fixtures/README.md` : description de chaque fixture.
- `.gitattributes` : fixtures lues octet pour octet (pas de normalisation des fins de ligne).
- `tests/test_setup_data.py` : tests de l'extraction, du zip-slip, de l'idempotence, du `--dry-run`, de l'intégrité des archives et du cas d'une seule archive présente.
- `tests/test_fixtures.py` : tests de parsing des fixtures, de la chaîne BREX, des contenus attendus et de l'absence de données réelles.

### Tests écrits, non exécutés

Les tests `tests/test_setup_data.py` et `tests/test_fixtures.py` ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Seul le mode `--dry-run` de `tools/setup_data.py` a été lancé (bibliothèque standard, aucune écriture) ; il confirme les comptes ci-dessus. Les tests doivent être lancés par le chef de projet une fois les dépendances installées.

### Non couvert

- Les données Bike ne sont pas reproduites dans le dépôt : elles restent dans `data/`, ignoré par git.

## 003 — CI, modèles et documents qualité neutres

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `.github/workflows/ci.yml` : CI (ruff, pytest sans les marqueurs `data41`, `data42`, `ollama`, contrôle de confidentialité si le secret de liste de termes est défini) ; job Windows lancé seulement sur `main`.
- `.github/ISSUE_TEMPLATE/bug.yml`, `.github/ISSUE_TEMPLATE/task.yml`, `.github/pull_request_template.md` : modèles d'issue et de PR.
- `CONTRIBUTING.md` : déroulé du travail (une tâche = une branche, tests d'abord, revue `OK` / `KO`, fusion par le chef seulement après `OK` et CI verte) et rappel de confidentialité.
- `README.md` : squelette (présentation, statut « prototype en cours », installation à compléter) et liens vers `docs/`, `QUALITY.md`, `CONTRIBUTING.md`.
- `QUALITY.md` : exigences (REQ), objectifs (OBJ), vérifications et journal, rédigés de façon neutre : seul le jeu de données public Bike est cité. Scénario `LRU1010` décrit sous le tableau des exigences (REQ-5).
- `PLANNING.md` : planning par étapes d'une semaine, avec engagement et preuve de fin d'étape.
- `tests/test_repo_files.py` : contrôle de la présence des fichiers requis, de la forme du workflow CI et de la présence des identifiants REQ / OBJ.

### Modifié

- `pyproject.toml` : ajustements mineurs.
- `workspace.example.toml` : ajustement mineur d'un chemin.

### Tests écrits, non exécutés

Les tests de `tests/test_repo_files.py` ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils doivent être lancés par le chef de projet une fois les dépendances installées.

### Non couvert

- Pas de remote distant : la CI GitHub n'est pas exécutable pour l'instant.

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
