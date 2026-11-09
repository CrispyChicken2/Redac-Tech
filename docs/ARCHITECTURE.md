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

Implémentés depuis les tâches 005 et 006 : `s1000d/io.py`, `s1000d/ident.py` (voir « Lecture et identification S1000D »), `sources/classify.py`, `s1000d/validate.py`, `s1000d/brex.py` et `s1000d/diff.py` (voir « Contrôles »).

Implémentés depuis les tâches 007 à 009 : `s1000d/index.py`, `s1000d/trace.py`, `s1000d/versioning.py` et `agents/a11_writer.py` (voir « Workspace, index et baseline » et « Traçabilité, versioning et écriture »). La distinction base de référence / introduit et `blocked_by_rule` restent à câbler : le paquet `pipeline/` est encore vide.

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

## Contrôles

Modules : `s1000d/validate.py`, `s1000d/brex.py`, `s1000d/diff.py`.

### Convention des résultats

- Chaque fonction `check_*` renvoie une liste de `CheckResult`.
- **Rien à signaler : un seul résultat `ok=True`, de gravité `info`.** Il sert à montrer que le contrôle a tourné (exemple : « 152 internal references resolve »).
- **Un problème : un résultat `ok=False` par anomalie**, de gravité `error` ou `warning`. Seuls les `ok=False` sont comptés comme problèmes.
- Un contrôle qui ne peut pas s'exécuter (schéma absent, règle BREX dont le XPath est invalide, BREX inconnu) renvoie un `ok=False` de gravité `warning`, jamais une exception.

### Contrôles XSD et structurels (`validate.py`)

- **XSD** (`check_xsd`) : le schéma est lu dans le dossier local `schemas/` de l'Issue détectée (`<données>/s1000d-<issue>/schemas`). Son nom vient de `xsi:noNamespaceSchemaLocation` de la racine. Le schéma est compilé une fois par chemin, avec le parseur durci, et jamais téléchargé. Une erreur XSD donne un `ok=False`, `error`, avec la ligne et le XPath.
- **Intégrité** (`check_integrity`) : la racine doit être `dmodule`, et contenir `identAndStatusSection` et `content`.
- **Identifiants** (`check_ids`) : chaque `@id` utilisé plusieurs fois donne un `ok=False` (une fois par identifiant, au deuxième emplacement).
- **Liens** (`check_links`) : chaque `internalRef/@internalRefId` doit viser un identifiant du document. Un lien absent donne un `ok=False`.
- **ICN** (`check_icn`) : chaque `graphic/@infoEntityIdent` doit être déclaré comme entité dans le DOCTYPE, ou avoir un fichier de même nom dans le dossier source. Sinon, `ok=False` de gravité `warning`.
- **Ensemble** (`check_all`) : XSD, intégrité, identifiants, liens, ICN, dans cet ordre.

### Règles BREX (`brex.py`)

Une règle est lue dans `structureObjectRuleGroup/structureObjectRule` de chaque BREX. Le XPath de `objectPath` est évalué sur le DM. La sémantique dépend de `objectPath/@allowedObjectFlag` :

| Flag | Sens | Violation quand |
|---|---|---|
| `0` interdit | l'objet ne doit pas apparaître | le XPath sélectionne un nœud (sans `objectValue`), ou une valeur sélectionnée correspond à un `objectValue` |
| `1` obligatoire | l'objet doit apparaître | le XPath ne sélectionne rien ; les valeurs sélectionnées doivent aussi correspondre aux `objectValue` s'il y en a |
| `2` autorisé | l'objet est permis | sans `objectValue` : jamais ; avec `objectValue` : une valeur sélectionnée hors des valeurs permises |

- `objectValue/@valueForm` : `single` (valeur exacte), `range` (`a~b`, bornes incluses, numérique si les deux bornes sont des nombres, sinon ordre de chaînes), `pattern` (expression régulière appliquée à la valeur, correspondance complète). La valeur d'un nœud est son texte, espaces normalisés.
- Une violation est un `CheckResult` `ok=False`, `error`, avec `rule` = {id, xpath, flag, message, brex} et le XPath du nœud fautif. Au plus 200 violations par règle.
- **Chaîne de BREX** (`resolve_chain`) : on part du `dmStatus/brexDmRef` du DM, on charge le BREX correspondant (index par nom de fichier : DMC de code d'information `022`, la version la plus récente l'emporte), puis le BREX de ce BREX, et ainsi de suite jusqu'au BREX par défaut. La recherche s'arrête si un BREX se réfère à lui-même (fin de chaîne), si un BREX est inconnu (avertissement), s'il y a un cycle (avertissement) ou après 10 niveaux (avertissement).
- **Aucune chaîne** : un avertissement. **Chaîne sans violation** : un résultat `ok=True` informatif (« N rules checked, no violation »).
- L'évaluateur interne est la référence. Un adaptateur vers un validateur BREX externe n'est pas fourni.

### Comparaison C14N (`diff.py`)

- `c14n_equal` : égalité de la forme C14N 1.0 de deux documents (commentaires ignorés).
- `changed_elements(before, after)` : liste des XPath des éléments qui diffèrent. Les éléments sont appariés par `@id` unique, sinon par leur position sous l'ancêtre le plus proche qui a un identifiant.
- Sont signalés : les éléments dont le contenu propre diffère, ceux dont les enfants ont été réordonnés, le sommet des sous-arbres ajoutés (chemin dans `after`) et celui des sous-arbres supprimés (chemin dans `before`). Les ancêtres d'un changement ne sont pas signalés.

## Workspace, index et baseline

Modules : `sources/workspace.py`, `s1000d/index.py`, `agents/a1_indexer.py`.

### Workspace (`sources/workspace.py`)

- **Fichier** : `workspace.toml` (ignoré par git), créé par `workspace init` à partir de `workspace.example.toml`. Chaque `[[sources]]` a un `id` et un `path`, plus `brex_dirs`, `issue`, `writable` et, facultativement, `schemas_dir`.
- **Chemins relatifs** : résolus par rapport au dossier du fichier workspace. À l'écriture, ils sont enregistrés relativement à ce même dossier quand c'est possible.
- **Erreurs de lecture** : une source sans `id` ou sans `path`, ou un `id` en double, lève `ValueError`.
- **`schemas_dir`** : si absent, on prend le dossier `schemas` voisin du dossier source (par exemple `data/s1000d-4.1/schemas` pour `data/s1000d-4.1/bike`), s'il existe.
- **Ajout** (`add_source`) : identifiant déduit du nom du dossier s'il n'est pas donné, suffixé si déjà pris ; un dossier `brex` voisin est utilisé comme BREX s'il existe ; l'Issue est lue dans un segment `s1000d-4.1` ou `s1000d-4.2` du chemin.
- **Balayage** (`scan`) : lecture à plat, sans récursion. Dans un dossier BREX, seuls les fichiers de rôle `brex` sont retenus. Un même `doc_key` apparaissant deux fois dans une source n'est listé qu'une fois, le dossier source l'emportant. Une source en lecture seule force `writable=False`.
- **Création** (`init_workspace`) : refuse d'écraser un fichier existant, sauf avec `--force`.

### Index du corpus (`s1000d/index.py`)

`build_index(ws)` produit un `CorpusIndex` :

- `docs` : tous les documents classés, par clé `source:doc_key`, avec la liste `brex_chain` des BREX de chaque DM ;
- `brex_index` : index des BREX par source (DMC → fichier) ;
- `parts` : occurrences de numéros de pièce par genre (`partNumber`, `partRef`, `partSpec`, `partIdent`, `para` pour le texte libre) ;
- `texts`, `internal_refs`, `dm_refs`, `figures` : tables de texte libre, de liens internes, de références de DM et de figures ;
- `warnings` : problèmes de chaîne BREX ; `unreadable` : documents illisibles, avec l'erreur (un document illisible ne fait pas échouer l'index).

Points à connaître :

- Seuls les rôles `dm` et `upf` sont indexés en contenu ; `dm` et `brex` ont leur chaîne BREX résolue.
- Les documents en lecture seule (UPF, BREX, sources `writable=false`) sont indexés aussi ; leurs occurrences portent `writable=False`.
- `find_part(index, numéro)` renvoie d'abord les occurrences structurées, puis les occurrences dans le texte libre. Le texte libre est cherché par mot entier : lettres, chiffres, `-` et `_` sont des caractères de mot. Recherche par chaînes uniquement, sans regex sur le XML.

### Baseline (`agents/a1_indexer.py`)

`run(ws)` indexe le corpus puis calcule la **baseline** : les problèmes déjà présents avant toute modification.

- Seuls les DM (rôle `dm`) sont contrôlés : XSD (si la source a un dossier `schemas`), intégrité, identifiants, liens, ICN, puis chaîne BREX et règles BREX.
- Sans dossier `schemas`, le XSD n'est pas contrôlé et un résultat `info` `ok=True` le dit.
- Chaque résultat porte `origin="pre_existing"`. Les résultats `ok=True` sont conservés ; `problems()` ne garde que les `ok=False`.
- Un fichier qui ne se traite pas ne bloque pas le reste : son échec devient un `ok=False` d'intégrité, de gravité `error`, et le balayage continue.

### Commandes

Commandes implémentées (les autres commandes de la CLI sont encore des squelettes) :

```bash
redactech workspace init                 # crée workspace.toml depuis workspace.example.toml
redactech workspace add data/s1000d-4.1/bike --id bike41
redactech workspace list                 # liste les sources, leur Issue et leur mode
redactech index                          # nombre de fichiers par source et par rôle
redactech baseline                       # problèmes préexistants par DM
```

Options communes : `--workspace FICHIER` (`-w`) pour un autre fichier que `config.toml` → `[workspace] file`. `workspace add` accepte `--brex-dir DOSSIER` (répétable) et `--id`. `workspace init` accepte `--force`.

Sortie et codes de retour :

- Fichier workspace absent ou invalide : message d'erreur, code `1`.
- `index` : une ligne par source (nombre de fichiers par rôle), une ligne de total, puis les documents illisibles sur la sortie d'erreur.
- `baseline` : une ligne par DM (erreurs et avertissements préexistants), puis une ligne de total.

Exemple de `workspace.toml` (copie de `workspace.example.toml`, chemins relatifs au dossier du fichier) :

```toml
# Copy to workspace.toml (ignored by git), then adapt the paths.

[[sources]]
id = "bike41"
path = "data/s1000d-4.1/bike"
brex_dirs = ["data/s1000d-4.1/brex"]
issue = "4.1"
writable = true

[[sources]]
id = "bike42"
path = "data/s1000d-4.2/bike"
brex_dirs = ["data/s1000d-4.2/brex"]
issue = "4.2"
writable = true

[[sources]]
id = "fixtures"
path = "tests/fixtures/s1000d"
brex_dirs = ["tests/fixtures/s1000d"]
issue = "4.1"
writable = true
```

Ajouter `schemas_dir = "data/s1000d-4.1/schemas"` à une source la rattache explicitement à son dossier de schémas.

## Demande, localisation et propositions

Modules : `s1000d/ops/` (opérations), `agents/a2_mapping.py` (lecture des demandes), `agents/a4_locator.py` (localisation), `agents/a5_preparer.py` (propositions).

### Les 8 opérations (`s1000d/ops/`)

Chaque opération est une fonction pure `op(tree, zone, params) -> OpResult`. Elle travaille sur une **copie** de l'arbre, ne touche à aucun fichier, et n'écrit que les valeurs données dans `params` (plus des identifiants générés). Une suppression n'enlève rien : elle désigne l'élément (`change_type="delete"`) ; le marquage est fait à l'écriture, et seule une nouvelle issue consolide.

| Opération | Paramètres | Effet | `change_type` |
|---|---|---|---|
| `replace_part` | `old`, `new`, `occurrence` (facultatif : 1 = première, -1 = dernière) | remplace le numéro de pièce à la zone : `partNumber` (texte), `partRef` / `partIdent` (attribut `partNumberValue`), ou texte libre (mot entier) | `modify` |
| `replace_text` | `old`, `new`, `scope` (`descendants` par défaut, ou `element`), `whole_word` (faux par défaut), `occurrence` | remplace un texte dans les nœuds texte de la zone | `modify` |
| `insert_step` | `para` ; `after_id` ou `before_id` (exactement un) | ajoute un `proceduralStep` avec un paragraphe, id `stp-NNNN` généré | `add` |
| `delete_step` | `step_id` (ou id de la zone) | désigne l'étape ; l'arbre n'est pas modifié | `delete` |
| `move_step` | `step_id` ; `after_id` ou `before_id` | déplace l'étape ; refusé si l'étape est placée à côté d'elle-même ou dans elle-même | `modify` |
| `update_ref` | pour un `dmRef` : `dm_code` (attributs du `dmCode` à changer), `issue_info` facultatif (`issueNumber`, `inWork`) ; pour un `internalRef` : `internal_ref_id` (doit exister), `target_type` facultatif | change la cible ; un `xlink:href` contenant l'ancien code est mis à jour | `modify` |
| `add_requirement` | `requirement` (`spare`, `supply`, `tool` ou `supportEquipment`), `part_number`, `manufacturer_code`, `quantity` (obligatoires), `name` facultatif | ajoute un descripteur dans `preliminaryRqmts` ; un placeholder `noSpares`-style est remplacé par le groupe | `add` |
| `remove_requirement` | `requirement` ; `id` ou `part_number` | désigne l'exigence ; exactement une correspondance requise ; l'arbre n'est pas modifié | `delete` |

Règles communes :

- Un paramètre manquant lève `OpError` en le nommant ; rien n'est deviné.
- Une cible introuvable, ou une zone sans cible, lève `OpError`.
- `replace_*` sans correspondance lève `OpError` (« not found at the zone »).
- Les autres genres de l'enum du modèle `Operation` (`update_applic`, `update_value`, `write_steps`, `fix_violation`, `translate_dm`) ne sont **pas implémentés** : `apply` lève `OpError`.

### Fichier de correspondances (`agents/a2_mapping.py`)

Une table de correspondances, au format CSV ou XLSX, est lue par `read_mapping` :

- **Colonnes** (en-tête insensible à la casse) : `old` et `new` obligatoires ; `kind` facultatif (`replace_part` par défaut, seuls `replace_part` et `replace_text` sont admis dans une table) ; `reason` facultatif (justification ; à défaut, « old replaced by new »).
- **CSV** : séparateur `;` ou `,`, détecté d'après le nombre de `;` et de `,` dans la ligne d'en-tête (`;` l'emporte si elle en contient davantage). Encodage UTF-8, la marque d'ordre d'octets est tolérée. Une cellule entre guillemets peut couvrir plusieurs lignes.
- **XLSX** (`.xlsx`, `.xlsm`) : première feuille, première ligne = en-tête.
- Les lignes vides sont ignorées. Chaque ligne garde sa forme brute (`_raw`), qui sert de **citation source** : chaque valeur écrite par la suite se retrouve donc dans la demande.
- **Refus** : une ligne sans `old` ou sans `new`, ou dont le `kind` n'est pas admis, fait lever `MappingError` avec la liste de tous les problèmes. Aucune opération n'est produite dans ce cas.
- `from_form(form)` fait de même pour une demande structurée (dictionnaire `kind`, `params`, `target`, `reason`) ; sa citation source est le formulaire lui-même.

### Localisation (`agents/a4_locator.py`)

`locate(op, index)` transforme une opération en **zones** (`Zone`) :

- **`replace_part`** : chaque occurrence du numéro dans l'index devient une zone. Les occurrences **structurées** (`partNumber`, `partRef`, `partSpec`, `partIdent`) sont `certain` ; les mentions dans le **texte libre** sont `probable`.
- **Documents en lecture seule** (UPF, BREX, sources `writable=false`) : jamais de zone. Elles sont listées dans `skipped_readonly` avec la raison.
- **Illustrations** : si l'élément modifié est lié à une figure du même document (lien `irtt01` dans le même conteneur, ou figure du catalogue pour un article illustré), une zone de genre `illustration` est ajoutée, de certitude `to_check`. L'outil ne modifie jamais les images.
- **Autres opérations** : une seule zone, certaine, désignant la cible de l'opération ; un document en lecture seule est ignoré.

Niveaux de certitude d'une zone (`Zone.certainty`) :

| Niveau | Sens |
|---|---|
| `certain` | occurrence structurée, ou cible explicite de l'opération |
| `probable` | mention trouvée dans le texte libre (vérification recommandée) |
| `to_check` | illustration liée à une modification : l'image doit être vérifiée à la main |

`Zone.found_by` vaut `code` pour ces zones (le LLM n'intervient pas à ce stade).

### Propositions (`agents/a5_preparer.py`)

`prepare(op, zones, index)` applique l'opération à chaque zone sur une copie en mémoire (rien n'est écrit) et produit une `Proposal` avec `before_xml` et `after_xml` :

- **Zone de contenu** : la proposition contient l'élément modifié, avant et après, et `change_type` renvoyé par l'opération.
- **Zone d'illustration** : proposition sans changement (`before_xml == after_xml`) portant un avertissement `illustration` de gravité `warning` (« to check »).
- Une zone que l'opération ne sait pas appliquer est rapportée dans `errors` (« needs manual edit » côté écriture), sans bloquer les autres zones.

**Alternatives après rejet** : `prepare(..., rejection=...)` propose, par calcul et non par LLM, une autre formulation :

- `replace_part` / `replace_text` : seulement la première mention, puis seulement la dernière (`occurrence` 1, puis -1) ;
- `insert_step` / `move_step` : la position voisine (après l'étape suivante, avant l'étape précédente) puis le côté opposé de l'étape de référence.

Les candidats sont essayés sur une copie et gardés seulement s'ils diffèrent de la proposition rejetée et entre eux. Chaque alternative porte `attempt` (+1), `replaces` (id de la proposition rejetée) et l'historique `rejection_feedback`. Le nombre d'alternatives est plafonné par `max_alternatives` (par défaut 3 ; l'appelant doit passer `trace.max_alternatives` de `config.toml`). Au-delà, ou s'il n'existe pas d'alternative, la liste est vide : il faut une édition manuelle.

### Format de la demande en bref

```csv
old;new;kind;reason
LRU1010;LRU2020;replace_part;Remplacement de la pièce
```

Le même contenu en CSV séparé par des virgules (`old,new,kind,reason`) est accepté, ainsi qu'un XLSX à la même structure.

## Traçabilité, versioning et écriture

Modules : `s1000d/trace.py`, `s1000d/versioning.py`, `agents/a11_writer.py`.

### Traçabilité (`s1000d/trace.py`)

- **Motif de mise à jour** (`ensure_reason`) : écrit un `dmStatus/reasonForUpdate` avec un identifiant unique `rfu-NNNN` et un `simplePara` contenant le texte normalisé (espaces réduits). Il est placé à l'endroit attendu par le schéma S1000D 4.1 : après `qualityAssurance`, les codes d'article fonctionnel et `skillLevel`, avant `productSafety` et `remarks`. Un motif au texte identique est réutilisé.
- **Marquage** (`mark`) : pose `changeMark="1"`, `changeType` et `reasonForUpdateRefIds` (ajouté sans doublon). Certains éléments n'acceptent pas ces attributs (`internalRef`, `dmCode`, `issueInfo`, `emphasis`, etc.) : la marque va sur l'ancêtre le plus proche qui les accepte.
- **Priorité des types** : un élément déjà `add` reste `add` s'il est modifié de nouveau dans le même cycle ; `delete` l'emporte sur tout.
- **Suppression** (`consolidate`) : seul endroit où un élément est réellement supprimé. Lors d'une nouvelle issue, les éléments marqués `delete` disparaissent (les plus hauts seulement), tous les motifs de mise à jour sont retirés et tous les attributs de marquage sont effacés.

Avant consolidation, une suppression reste donc visible : l'élément est gardé et marqué `changeType="delete"`.

### Politiques de versioning (`s1000d/versioning.py`)

Trois politiques : `none` (`issueInfo` inchangé), `in_work` (`inWork` + 1) et `new_issue` (consolidation, `issueNumber` + 1, `inWork` remis à `00`). Exemples :

| Politique | Avant | Après |
|---|---|---|
| `in_work` | `007-00` | `007-01` |
| `new_issue` | `007-00` | `008-00` |

Application (`apply_policy`) : pour `in_work` et `new_issue`, la date `issueDate` prend la date du jour, et `dmStatus/@issueType` passe à `changed` s'il existe et si l'issue n'est pas `001`. Le nouveau nom de fichier est renvoyé par `ident.filename_for`. Un `inWork` ou un `issueNumber` non numérique, ou qui déborde sa largeur (2 et 3 chiffres), lève `VersioningError`.

**Suggestion** (`suggest_policy`) : chaque opération est classée ; la politique la plus forte l'emporte, et `reasons` liste chaque déclenchement. Sans opération, `none`.

| Opération | Condition | Politique suggérée |
|---|---|---|
| `update_ref` | toujours | `in_work` |
| `replace_text` | `old` et `new` sont des nombres | `new_issue` |
| `replace_text` | sinon | `in_work` |
| `replace_part` | `requirement` de type `spare` ou `supply` dans les paramètres | `new_issue` |
| `replace_part` | sinon | `in_work` |
| `add_requirement`, `remove_requirement` | `spare` ou `supply` | `new_issue` |
| `add_requirement`, `remove_requirement` | `supportEquipment` / `tool` | `in_work` |
| `insert_step`, `delete_step`, `move_step` | paramètre `warning` ou `caution` | `new_issue` |
| `insert_step`, `delete_step`, `move_step` | sinon | `in_work` |
| ensemble | plus de 3 étapes insérées ou supprimées (`insert_step` + `delete_step`) | `new_issue` |

Point d'attention : pour `replace_part`, la condition lit `params["requirement"]`, que le fichier de correspondances ne renseigne jamais. Une correspondance de pièce de rechange est donc suggérée en `in_work` aujourd'hui ; seule une demande structurée qui donne `requirement` déclenche `new_issue`.

### Écriture (`agents/a11_writer.py`)

`write(run_dir, index, proposals, policy, …)` écrit les propositions décidées dans `<run_dir>/out`.

- **Ce qui est écrit** : seulement les propositions `accepted` ou `edited`. `edited` remplace l'élément généré par le `edited_xml` du rédacteur, qui doit être bien formé. Les `rejected`, `pending_client` et `blocked_by_rule` ne sont jamais écrits.
- **Refus global** : une proposition encore `proposed` (et non exclue) bloque tout. `decided=False` refuse aussi. Rien n'est écrit en cas de refus : toutes les opérations sont préparées en mémoire avant l'écriture.
- **Ce qui n'est jamais écrit** : les zones d'illustration (signalées, sans changement) ; les documents en lecture seule (UPF, BREX, documents d'une source `writable=false`), qui sont ignorés et listés avec leur raison. Seuls les DM (`dm`) sont écrits.
- **Fichiers source** : jamais modifiés. Chaque DM est rechargé, les opérations sont rejouées sur cette copie privée (sans épissage de chaînes), les éléments modifiés sont marqués, un motif de mise à jour est ajouté à partir de la justification de l'opération, la politique est appliquée, puis le résultat est enregistré sous son nouveau nom.
- **Cibles positionnelles** : avant les opérations, chaque élément cible reçoit un attribut temporaire (`rt-target`), supprimé avant l'enregistrement. Les insertions précédentes ne décalent ainsi pas les chemins XPath des zones suivantes.
- **Consolidation** : pour une politique `new_issue`, la consolidation est faite en premier. Une cible déjà marquée `delete` dans un cycle précédent disparaît à cette consolidation : l'écriture la refuse.
- **Dossier de sortie** : doit être différent du dossier source, sinon refus.
- **Journal** : une entrée par document (ancien et nouveau nom, politique, propositions, marques posées), et une liste des propositions ignorées avec leur raison.

## Vérification des propositions et règles bloquantes

Modules : `agents/a7_checker.py` (vérification), `agents/a5_preparer.py` (boucle de reprise et `blocked_by_rule`).

### Vérification d'une proposition (`a7_checker.check_proposal`)

1. La proposition est rejouée sur une **copie en mémoire** du DM, avec ses marques de traçabilité, exactement comme le ferait l'écrivain (`apply_to_copy`, politique `none`). Rien n'est écrit.
2. Les contrôles sont lancés sur la copie : XSD (si la source a un dossier `schemas`), intégrité, identifiants, liens, ICN, chaîne de BREX et règles BREX. Seuls les échecs sont conservés.
3. Chaque échec est classé :
   - `pre_existing` si la baseline du document d'origine contient un échec équivalent ;
   - `introduced` sinon. Un échec `introduced` ne doit jamais être livré (REQ-11).
4. Si la proposition ne peut pas être rejouée, un seul échec `integrity` de gravité `error`, `introduced`, indique « the proposal cannot be applied ».

**Clé d'appariement** : les numéros de ligne et les positions ne comptent pas, car une modification peut les décaler.

| Contrôle | Clé |
|---|---|
| `xsd` | nom du contrôle + message sans le préfixe `line N:` |
| `brex` | nom du contrôle + identifiant de la règle + message (qui contient la valeur fautive) |
| autres | nom du contrôle + message |

Les correspondances se font une à une : si la baseline a deux échecs d'un genre et que le résultat en a trois, un seul est `introduced`.

**Contrôle de véracité** (`veracity_failures`) : pour chaque valeur nouvelle de l'élément modifié (valeurs d'attributs sauf `id`, et textes non vides), absente de l'élément avant modification, une erreur `introduced` est ajoutée si aucune chaîne de la demande n'est contenue dans cette valeur. Les chaînes de la demande sont les paramètres de l'opération et les citations de sa source. Une proposition `edited` (saisie par le rédacteur) est exemptée.

**Illustrations** : une zone d'illustration ne donne que son avertissement « to check », sans rejeu.

**Document de sortie** (`check_doc`) : même classement, appliqué à un document complet produit, avec la baseline de la source d'origine.

### Reprise sur règle BREX et `blocked_by_rule` (`a5_preparer.prepare_checked`)

Pour chaque zone de contenu :

1. La proposition est vérifiée. S'il n'y a pas d'échec BREX `introduced` (gravité `error`), elle est retenue telle quelle.
2. Sinon, jusqu'à `max_rule_retries` (2 par défaut) **alternatives** calculées par le code (les mêmes que pour un rejet : première ou dernière mention, position voisine). Chaque alternative est vérifiée à son tour.
3. La première alternative sans échec BREX `introduced` remplace la proposition : elle porte `replaces` et `attempt`, et son opération dérivée est ajoutée à `extra_operations` (l'écrivain en a besoin).
4. Si aucune alternative ne passe :
   - **même règle à chaque tentative** (intersection non vide des identifiants de règle) : statut `blocked_by_rule`, `attempt` = nombre de tentatives, et les tentatives échouées sont notées dans `rejection_feedback`. Une question au client, pré-remplie avec la règle et la citation de la demande, est ajoutée aux `questions` de l'opération ;
   - **règles différentes** : la proposition d'origine est gardée en `proposed`, avec ses erreurs, et laissée au rédacteur.

**Nombre de tentatives** : au plus `1 + max_rule_retries`, soit 3 par défaut. La boucle ne peut pas tourner indéfiniment, y compris quand aucune alternative n'existe : on s'arrête alors à la première tentative.

Une zone que l'opération ne sait pas appliquer est rapportée dans `errors`, sans bloquer les autres zones.

**Question pré-remplie** (`customer_question`) : le texte est en anglais dans le code : « The request '…' conflicts with business rule <id>: <message>. How should we proceed? ».

L'écrivain ne traite jamais un statut `blocked_by_rule` : il le saute (voir « Écriture »).

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
