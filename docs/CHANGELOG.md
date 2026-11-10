# Journal des modifications

## 017 — Tests de l'interface

**Statut :** fusionnée. **Résultat de CI rapporté, non vérifié sur ce poste.**

### Ajouté

- `tests/ui/test_app.py` : tests de l'interface avec `streamlit.testing` (AppTest) : parcours de la page, règles des signalements et compteurs exposés par l'orchestrateur.
- `tests/pipeline/test_orchestrator.py` et `tests/render/test_published.py` : cas ajoutés pour les signalements et les compteurs.
- Ajustements mineurs dans `src/redactech/ui/app.py`, `src/redactech/ui/components.py`, `src/redactech/pipeline/orchestrator.py` et `src/redactech/render/published.py`, nécessaires aux nouveaux tests.

### Résultat de CI rapporté

- Run `42790955399` sur la branche `prototype1`, rapporté par le responsable du projet : 834 tests réussis.
- **Non vérifié** : ce poste n'a pas de dépôt distant ; `gh run view` ne peut pas consulter le run.

### Non couvert

- Le test utilisateur avec l'évaluateur (REQ-7) reste à faire : les tests automatiques ne le remplacent pas.
- Pas de remote distant sur ce poste.

## 016 — Interface Streamlit

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/ui/app.py` : interface Streamlit, mode Document : barre latérale **Projet** (sources, téléversement de fichiers, remplacement de BREX, problèmes préexistants) et trois onglets **Demande**, **Document et propositions**, **Livraison**. Aucune acceptation automatique ; **Tout accepter** est limité aux propositions certaines et sans problème.
- `src/redactech/ui/state.py` : projet et session (`runs/_ui/`), téléversements dans une source `uploads`, remplacement de BREX, confirmation de la politique.
- `src/redactech/ui/components.py` : libellés, badges de contrôle, formulaire de demande, téléchargements. Fonctions pures, sans import de Streamlit.
- `tests/ui/` : tests de l'état du projet et de l'import de l'application, sans démarrer Streamlit.
- `docs/DEMO.md` : section 10, « Parcours dans l'interface », avec les libellés exacts de l'application.
- `docs/ARCHITECTURE.md` : section « Interface » ; tableau des modules : `ui/` passe à « implémenté ».

### Tests écrits, non exécutés

Les tests de l'interface ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. L'application n'a pas été lancée (`streamlit run`). Ils tournent sur la CI GitHub uniquement.

### Non couvert

- Le versionnement est un panneau de l'onglet **Demande**, pas une fenêtre modale.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 015 — Vues XML et publiée

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/render/xml_view.py` : vue XML échappée, une balise par ligne, numéros de ligne, marques de changement (`rt-add`, `rt-modify`, `rt-delete`) et mise en évidence d'identifiants. Mise en page normalisée, document non modifié.
- `src/redactech/render/xslt/published.xsl` et `src/redactech/render/published.py` : vue publiée de type IETP (feuille XSLT 1.0 compilée une fois) : étapes numérotées, exigences, encadrés `WARNING` / `CAUTION` / `NOTE`, tableaux IPD et comrep, badges d'applicabilité, barre de changement, suppressions barrées ou masquées (`--hide-deleted`). Les figures sont des cases portant leur nom ICN ; aucune image n'est chargée. Rendu générique des éléments inconnus.
- `src/redactech/render/side_by_side.py` : deux colonnes, avant / après d'une proposition (vue `xml` ou `published`) et page HTML autonome (`both` par défaut).
- CLI : `redactech render DOC --view xml|published|both --show-deleted|--hide-deleted --out F`.
- Tests : `tests/render/` (vue XML, vue publiée, côte à côte) ; ajouts dans `tests/agents/test_a4_locator.py`, `tests/s1000d/test_brex.py`, `tests/report/`, `tests/pipeline/test_orchestrator.py` et `tests/test_cli.py`.
- `docs/ARCHITECTURE.md` : section « Vues ». La section CLI est remise à jour : toutes les commandes sont implémentées, et la liste des options est celle du code. La ligne `render/` du tableau des modules passe à « implémenté ».
- `docs/DEMO.md` : étape 9, « Afficher un document ».

### Tests écrits, non exécutés

Les tests ci-dessus ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. L'exemple `render` de `docs/DEMO.md` n'a pas été lancé. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- La mise en page XML affichée est normalisée (une balise par ligne) : elle ne reproduit pas les octets du fichier.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 014 — Rapport et exports

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/report/build.py` : rapport de livraison (`Report`) : documents avec anciens et nouveaux noms, politique, changements, contrôles séparés en préexistants et introduits, demandes bloquées, figures à vérifier, questions ouvertes, documents ignorés, compteurs.
- `src/redactech/report/html.py` : page HTML autonome (styles intégrés, aucun script, aucune ressource externe, valeurs échappées).
- `src/redactech/report/export.py` : `report.json`, `report.html`, `questions.csv` (séparateur `;`, UTF-8 avec BOM), `decisions.jsonl` (une décision par ligne).
- `redactech write` produit désormais ces quatre fichiers à la racine du run (`runs/<id>/`) et affiche une ligne `delivery` pour chacun. Rien n'est produit si l'écriture est refusée.
- Tests : `tests/report/` (construction, export, HTML) et ajout dans `tests/pipeline/test_orchestrator.py` et `tests/test_cli.py`.
- `docs/ARCHITECTURE.md` : section « Livrables d'un run » ; tableau des modules mis à jour (`report/` implémenté).
- `docs/DEMO.md` : liste des fichiers produits après l'étape d'écriture.

### Tests écrits, non exécutés

Les tests ci-dessus ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- L'export `.xlsx` des questions existe dans `export_questions`, mais la commande `write` ne produit que le CSV.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 023 — Clôture M1

**Statut :** jalon M1 clos. **Tests : résultat de CI rapporté, non vérifié sur ce poste.**

### Ajouté

- `QUALITY.md`, section 2 :
  - REQ-3 passe à ✅ avec des preuves complétées (`tests/security/`, hooks, scan local) ; REQ-5, REQ-6, REQ-10, REQ-11, OBJ-21, OBJ-22 et OBJ-23 passent à ⚠️, avec le scénario cité en preuve ;
  - lignes OBJ-1, OBJ-10 et OBJ-19 ajoutées à la section 2 (elles n'y figuraient pas), avec le critère de la section 1 recopié tel quel (⚠️) ;
  - les colonnes « Responsable » (✏️) et les seuils ne sont pas modifiés.
- `QUALITY.md`, section 3 : entrée « Étape M1 », qui distingue ce qui est rapporté (run de CI `42757082793`, 690 tests réussis, lint propre) de ce qui est vérifié sur ce poste.

### Tests : résultat rapporté

- Run de CI `42757082793` sur `prototype1`, rapporté par le responsable du projet : 690 tests réussis, lint propre. **Non vérifié** : ce poste n'a pas de dépôt distant, et `gh` ne peut pas consulter le run.
- Les tests `data41` et `data42` ne sont pas exécutés en CI ; les scénarios `lru1010_bike41` et `batch20_bike41` ne sont pas vérifiés sur le Bike réel.

### Non couvert

- Le chiffrage « avec LLM » de OBJ-10 : aucun LLM n'est branché.
- La revue humaine avant / après de OBJ-19.
- Les cellules ✏️ (responsables) restent à remplir.

## 013 — Scénarios part 2

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- Scénarios dans `tests/scenarios/` :
  - `batch20` : 20 remplacements de numéros de pièce fictifs dans 5 répertoires communs, moins de 10 s (OBJ-10) ;
  - `batch20_bike41` : 20 vrais numéros de pièce du jeu Bike 4.1 remplacés par des numéros fictifs, 34 changements attendus, sauté sans les données (OBJ-10) ;
  - `ops_steps` : six opérations sur étapes et exigences et un remplacement de pièce dans une seule demande ; figure signalée « à vérifier » (OBJ-1, OBJ-19) ;
  - `forbidden_request` : une demande que le BREX interdit finit `blocked_by_rule` après 3 tentatives, la deuxième opération est écrite (OBJ-23) ;
  - `brex_swap` : le même changement, avec le BREX du projet puis avec une copie modifiée ; le changement est livré dans les deux cas (échange de BREX, lié à OBJ-22 et REQ-11 à confirmer).
- Le lanceur de scénarios (`pipeline/scenarios.py`) accepte désormais `brex_patch`, `blocked_details`, `baseline_brex`, `illustrations`, `also_allowed` avec `exact`, et une `form` en liste d'opérations ; les fichiers de fixtures peuvent être dans un sous-dossier.
- `docs/SCENARIOS.md` : nouvelles clés, les cinq scénarios et leurs exigences.

### Corrigé

- `docs/DEMO.md` :
  - le rejet de l'exemple porte désormais sur la mention en texte libre (`content/probable`) ; les occurrences UPF ne donnent jamais de proposition ;
  - les identifiants de propositions sont à copier depuis le tableau affiché par `review`, l'ordre de `<n>` n'est pas garanti ;
  - la colonne du tableau est `genre/certitude` (par exemple `content/probable`).

### Tests écrits, non exécutés

Les scénarios et les tests du lanceur ont été écrits, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- `batch20_bike41` dépend des données Bike 4.1, absentes de ce poste.
- Le rattachement de `brex_swap` à OBJ-22 et REQ-11 est une proposition, non validée par `QUALITY.md`.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 012 — Scénarios et eval

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/pipeline/scenarios.py` : lanceur de scénarios. Lit `scenario.yaml` et `attendu.yaml`, lance l'orchestrateur, compare les sorties à l'attendu (changements, éléments intacts, comptes, problèmes, marques) et calcule cinq mesures : exhaustivité, précision, préservation, validité, traçabilité.
- Scénarios dans `tests/scenarios/`, chacun avec son `attendu.yaml` écrit avant exécution à partir des fichiers d'entrée :
  - `lru1010` : remplacement de `LRU1010` dans un répertoire commun, un catalogue et un paragraphe, UPF intact (REQ-5, REQ-6) ;
  - `lru1010_bike41` : même remplacement sur les vraies données Bike 4.1, sauté sans les données (REQ-5, REQ-6, REQ-10, REQ-11) ;
  - `delete_mark` : suppression d'étape marquée, non supprimée (REQ-10) ;
  - `versioning` : trois politiques sur le même changement (OBJ-21) ;
  - `preexisting_brex` : problèmes préexistants classés comme tels, rien d'introduit (OBJ-22, REQ-11).
- `tests/scenarios/_schemas/dmodule.xsd` : schéma minimal, utilisé par défaut pour la validité.
- `tests/scenarios/test_scenarios.py` : un test par scénario et par variante.
- CLI : `redactech eval tests/scenarios/` (option `--out`), qui écrit `runs/eval_<date>.md` et se termine avec le code `1` si un scénario échoue.
- `docs/SCENARIOS.md` (nouveau) : format des deux fichiers, mesures, liste des scénarios et exigences prouvées, variantes, procédure d'ajout, colonnes du rapport.
- `docs/DEMO.md` : étape 8, « Évaluer les scénarios ».

### Tests écrits, non exécutés

Les scénarios et le lanceur n'ont **pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets, et la commande `eval` n'a pas été lancée. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- Le scénario `lru1010` attend trois changements, dont une mention en texte libre. Le chiffre « 2/2 » de `QUALITY.md` (REQ-5) ne compte que les occurrences structurées. Les deux documents ne sont pas alignés ; à trancher par le chef de projet.
- `lru1010_bike41` n'a pas pu être exécuté : les données Bike ne sont pas sur ce poste.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 011 — Orchestrateur et CLI

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/pipeline/orchestrator.py` (agent A0) : machine à états (`indexed` → `ops_proposed` → `ops_validated` → `zones_proposed` → `zones_validated` → `proposals_ready` → `reviewed` → `written`), points d'arrêt sur les opérations et les propositions, état sauvegardé dans `runs/<id>/state.json`, reprise avec `Run.load`, journal des décisions horodaté.
- Garde-fous : aucune écriture sans décision ni politique de versioning ; `accepted` refusé si une erreur est introduite ; `edited` revérifié ; `blocked_by_rule` ne reçoit que `pending_client` ; l'acceptation en lot ne prend que les propositions certaines et sans problème.
- CLI : `request`, `review` (`--accept`, `--reject`, `--reason`, `--pending`, `--comment`, `--accept-all`), `write` (`--version-policy`), `check` (code de sortie `1` si une erreur est introduite). `--auto-accept` est une option cachée, réservée aux tests.
- `docs/DEMO.md` : démonstration pas à pas sur les fixtures (scénario `LRU1010` → `LRU2020`), à lancer une fois le paquet installé.
- `docs/ARCHITECTURE.md` : section « Orchestrateur ». Tableau des modules mis à jour pour l'état réel.

### Tests écrits, non exécutés

Les tests de l'orchestrateur et de la CLI ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Les commandes de `docs/DEMO.md` n'ont pas été lancées non plus. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- `render` et `eval` restent des squelettes (« not implemented yet », code `2`).
- L'assistant de discussion (A10) n'est pas commencé.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.
- Le paquet `pipeline/` n'est plus vide : la mention « pipeline vide » des entrées 006 à 010 est antérieure à cette tâche.

## 010 — Checker et blocked_by_rule

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/agents/a7_checker.py` : vérification d'une proposition sur copie en mémoire (XSD, intégrité, identifiants, liens, ICN, chaîne et règles BREX), classement de chaque échec en `pre_existing` ou `introduced` par rapport à la baseline, contrôle de véracité (valeurs nouvelles absentes de la demande), avertissement pour les illustrations.
- `src/redactech/agents/a5_preparer.py` : `prepare_checked`. Un échec BREX introduit déclenche au plus 2 alternatives calculées par le code (3 tentatives au total). Si toutes les tentatives échouent sur la même règle, la proposition passe en `blocked_by_rule`, avec une question client pré-remplie. Si les règles diffèrent, la proposition reste `proposed` avec ses erreurs.
- `tests/agents/test_a7_checker.py`, `tests/agents/test_blocked_by_rule.py`, `tests/agents/test_a5_preparer.py`.
- `docs/ARCHITECTURE.md` : section « Vérification des propositions et règles bloquantes ».

### Tests écrits, non exécutés

Les tests ci-dessus ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- La question client pré-remplie est en anglais, dans le code ; le reste du projet est en français.
- Le paquet `pipeline/` est toujours vide : l'enchaînement des étapes (demande, localisation, vérification, écriture) n'existe pas encore.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

## 009 — Traçabilité et versioning

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `src/redactech/s1000d/trace.py` : motif de mise à jour `reasonForUpdate` (identifiant `rfu-NNNN`, placement selon le schéma 4.1, réutilisation d'un texte identique), marquage `changeMark` / `changeType` / `reasonForUpdateRefIds` sur l'ancêtre qui accepte les attributs, consolidation lors d'une nouvelle issue (seul endroit où un élément est supprimé).
- `src/redactech/s1000d/versioning.py` : trois politiques (`none`, `in_work`, `new_issue`), application (`inWork`, `issueNumber`, date, `issueType`), nouveau nom de fichier, suggestion de politique avec motifs.
- `src/redactech/agents/a11_writer.py` : écriture des seules propositions `accepted` ou `edited` dans `<run>/out`. Refus global si une proposition est encore `proposed`. Les sources, UPF, BREX et illustrations ne sont jamais écrites. Les opérations sont rejouées sur une copie privée.
- `tests/s1000d/test_trace.py`, `tests/s1000d/test_versioning.py`, `tests/agents/test_a11_writer.py`.
- `docs/ARCHITECTURE.md` : section « Traçabilité, versioning et écriture ».

### Tests écrits, non exécutés

Les tests ci-dessus ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. Ils tournent sur la CI GitHub uniquement.

### Non couvert

- La suggestion de politique pour `replace_part` lit `params["requirement"]`, que les correspondances ne fournissent pas : une modification de pièce de rechange depuis une table reste en `in_work`.
- Les conflits et les questions au client ne sont pas traités par l'écriture.
- Pas de remote distant sur ce poste : statut de la CI non vérifié.

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
