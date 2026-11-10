# Démonstration en ligne de commande

Ce guide déroule le scénario `LRU1010` → `LRU2020` sur les fixtures synthétiques (`tests/fixtures/s1000d/`), de bout en bout : indexation, demande, décisions du rédacteur, écriture, contrôle.

Les commandes ci-dessous sont celles de `src/redactech/cli.py`. Elles n'ont pas été exécutées sur le poste de développement (règle machine) : elles se lancent une fois le paquet installé par vos soins (`pip install -e ".[dev]"` ou `uv sync`), depuis la **racine du dépôt**, car `config.toml` est lu dans le dossier courant.

## 0. Avant de commencer

- Les fixtures ne contiennent aucun fichier du jeu Bike. Si `data/` contient le jeu Bike (voir `data/README.md`), le workspace créé par défaut inclut aussi les sources `bike41` et `bike42`, et `LRU1010` y apparaît aussi. Pour cette démonstration, supprimez les blocs `[[sources]]` `bike41` et `bike42` du fichier `workspace.toml`, ou utilisez un fichier dédié avec l'option `-w demo.toml` sur chaque commande.
- Chaque run est créé sous `runs/` (ignoré par git). Les sources ne sont jamais modifiées.

## 1. Créer le workspace

```bash
redactech workspace init
```

Crée `workspace.toml` à partir de `workspace.example.toml`. Options : `--workspace FICHIER` (`-w`) pour un autre fichier ; `--force` pour écraser un fichier existant (sans lui, la commande refuse).

Vérifier les sources :

```bash
redactech workspace list
```

Affiche, pour chaque source : identifiant, Issue, mode (`writable` ou `read-only`), dossier, et dossiers BREX.

## 2. Indexer le corpus

```bash
redactech index
```

Affiche le nombre de fichiers par source et par rôle (`dm`, `brex`, `upf`, etc.), le nombre de numéros de pièce et de figures, puis les documents illisibles (sur la sortie d'erreur).

## 3. Calculer la baseline

```bash
redactech baseline
```

Affiche, par DM, les erreurs et avertissements **préexistants** : ils existaient avant toute modification, et ne seront jamais imputés à l'outil. Une ligne `note` signale les sources sans dossier `schemas` : le XSD n'est pas contrôlé pour elles.

## 4. Préparer la demande

Créer `lots.csv` (deux lignes, séparateur `;`) :

```csv
old;new
LRU1010;LRU2020
```

Lancer la demande :

```bash
redactech request --mapping lots.csv --version-policy in_work --out runs/
```

- `--mapping` : table CSV ou XLSX (colonnes `old`, `new`, et facultativement `kind` et `reason`).
- `--version-policy` : `none`, `in_work` ou `new_issue`. Sans cette option, la politique devra être choisie à l'écriture.
- `--out` : dossier des runs (défaut : `runs`).
- `--workspace` / `-w` : fichier workspace (défaut : `config.toml`, section `[workspace]`).

La commande crée `runs/<AAAAMMJJ-HHMMSS>-<jeton>/`, lit les propositions et affiche :

- le dossier du run ;
- une ligne par proposition, en colonnes séparées par des tabulations : identifiant, statut, `genre/certitude` de la zone (par exemple `content/certain` ou `content/probable`), document, nombre de problèmes introduits ;
- la politique suggérée (avec ses motifs), et la politique choisie ;
- le nombre de propositions à décider, avec la commande `review` à lancer.

Attendu pour ce scénario (voir `QUALITY.md`, REQ-5) : 2 modifications structurées à faire, et les 2 traces historiques du fichier UPF laissées intactes. La démonstration propose aussi une mention en texte libre (niveau `probable`) : elle est à décider à la main. Le scénario automatique `lru1010` de `docs/SCENARIOS.md` la compte comme troisième changement. Les UPF sont en lecture seule : leurs occurrences sont ignorées et tracées dans le journal, avec la raison.

Le reste de la démonstration utilise le dossier du run, noté `runs/<id>` ci-dessous. Remplacer `<id>` par le nom affiché.

## 5. Décider

Relister les propositions sans rien changer :

```bash
redactech review runs/<id>
```

Les identifiants ont la forme `prop-op-0001-<n>`, mais l'ordre de `<n>` n'est pas garanti. **Copiez les identifiants depuis le tableau affiché par `review`**, jamais depuis les exemples de ce guide. Les exemples ci-dessous utilisent les marqueurs `<id-certain>` (une proposition de colonne `content/certain`) et `<id-probable>` (une proposition de colonne `content/probable`) : remplacez-les par les identifiants réels.

**Accepter** une proposition certaine :

```bash
redactech review runs/<id> --accept <id-certain>
```

Refusé si la proposition introduit une erreur : il faut alors la modifier ou la rejeter.

**Rejeter** avec un motif, ici la mention en texte libre (colonne `content/probable`) :

```bash
redactech review runs/<id> --reject <id-probable> --reason "Mention de description, à traiter à part"
```

Les occurrences du fichier UPF ne donnent jamais de proposition : elles sont seulement journalisées comme lues en lecture seule (`skipped_readonly`). Il n'y a donc rien à rejeter pour elles.

Le système cherche une alternative calculée par le code (autre occurrence, par exemple). Il affiche `alternative <id>` si elle existe, sinon `no alternative: needs manual edit`.

**Laisser en attente** une question au client, avec un commentaire :

```bash
redactech review runs/<id> --pending <id-probable> --comment "Faut-il traiter cette mention ?"
```

**Accepter en lot** les propositions certaines et sans problème :

```bash
redactech review runs/<id> --accept-all
```

Seules les propositions de zone certaine, de contenu, sans aucun problème introduit sont acceptées. Les autres restent `proposed`.

Les options se combinent dans un même appel. Après chaque appel, la commande affiche les propositions et le nombre restant à décider.

## 6. Écrire

```bash
redactech write runs/<id>
```

Écrit les propositions `accepted` ou `edited` dans `runs/<id>/out/`, sous leur nouveau nom de fichier. Les propositions `rejected` et `pending_client` ne sont pas écrites, et ne sont pas listées non plus. Les documents en lecture seule sont ignorés et affichés avec leur raison. Les illustrations, signalées sans changement, ne sont pas écrites.

La commande refuse tant qu'une proposition est encore `proposed` (hors illustrations) : le rédacteur doit décider de toutes.

Si la politique n'a pas été choisie à la demande, l'option `--version-policy none|in_work|new_issue` est obligatoire ici. Elle n'est enregistrée que si l'écriture réussit.

Une écriture réussie produit les fichiers suivants :

| Emplacement | Contenu |
|---|---|
| `runs/<id>/out/` | les documents écrits, sous leur nouveau nom de fichier (après versioning) |
| `runs/<id>/report.json` | le rapport complet : documents, changements, contrôles, demandes bloquées, figures à vérifier, questions, compteurs |
| `runs/<id>/report.html` | le même rapport, lisible dans un navigateur (page autonome, sans script) |
| `runs/<id>/questions.csv` | les questions ouvertes (colonnes `id`, `document`, `element`, `question/comment`, `status`, `rule`), séparateur `;` |
| `runs/<id>/decisions.jsonl` | les décisions prises, une par ligne |

La commande affiche une ligne `delivery <chemin>` pour chacun des quatre fichiers de rapport et d'exports. Détail de chaque fichier : `docs/ARCHITECTURE.md`, section « Livrables d'un run ».

## 7. Contrôler le résultat

```bash
redactech check runs/<id>/out
```

Pour chaque fichier produit, affiche les problèmes **introduits** et **préexistants**, puis le total. La commande se termine avec le code `1` s'il reste une erreur introduite, `0` sinon.

Le journal complet du run est dans `runs/<id>/state.json` (champ `decisions_log`), avec l'horodatage de chaque décision.

## 8. Évaluer les scénarios

```bash
redactech eval tests/scenarios/
```

Lance tous les scénarios de `tests/scenarios/` (et leurs variantes), affiche `PASS`, `FAIL` ou `SKIP` pour chacun, écrit le rapport `runs/eval_<date>.md` (option `--out` pour un autre dossier), et se termine avec le code `1` si un scénario échoue. Le scénario `lru1010_bike41` est sauté sans les données Bike. Le détail des scénarios, de leurs attendus et des colonnes du rapport est dans `docs/SCENARIOS.md`.

## 9. Afficher un document

```bash
redactech render tests/fixtures/s1000d/DMC-RTPROTO-AAA-D00-00-00-00AA-520B-A_007-00_EN-US.XML --view both --hide-deleted --out runs/render-520B.html
```

Produit une page HTML autonome, lisible dans un navigateur, avec la vue XML et la vue publiée côte à côte. Le fichier `520B` porte des marques `add`, `modify` et `delete` : `--hide-deleted` omet les éléments supprimés dans la vue publiée. La vue XML les montre toujours, en rouge barré.

- `--view xml` : seulement la vue XML, avec les marques de changement ;
- `--view published` : seulement la vue publiée (étapes numérotées, encadrés, tableaux) ;
- `--view both` (défaut) : les deux côte à côte ;
- sans `--out`, la page est écrite sur la sortie standard ;
- `--show-deleted` (défaut) affiche les éléments supprimés, barrés.

Aucune image n'est chargée : une figure apparaît comme une case portant son nom ICN. Détail : `docs/ARCHITECTURE.md`, section « Vues ».
