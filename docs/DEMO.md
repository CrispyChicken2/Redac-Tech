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
- une ligne par proposition : identifiant, statut, genre et certitude de la zone, document, nombre de problèmes introduits ;
- la politique suggérée (avec ses motifs), et la politique choisie ;
- le nombre de propositions à décider, avec la commande `review` à lancer.

Attendu pour ce scénario (voir `QUALITY.md`, REQ-5) : 2 modifications à faire, et les 2 traces historiques du fichier UPF laissées intactes. Les UPF sont en lecture seule : leurs occurrences sont ignorées et tracées dans le journal, avec la raison.

Le reste de la démonstration utilise le dossier du run, noté `runs/<id>` ci-dessous. Remplacer `<id>` par le nom affiché.

## 5. Décider

Relister les propositions sans rien changer :

```bash
redactech review runs/<id>
```

Les identifiants exacts sont ceux affichés à l'étape précédente. Ils suivent le modèle `prop-op-0001-<n>` pour la première ligne de la table.

**Accepter** une proposition :

```bash
redactech review runs/<id> --accept prop-op-0001-1
```

Refusé si la proposition introduit une erreur : il faut alors la modifier ou la rejeter.

**Rejeter** avec un motif :

```bash
redactech review runs/<id> --reject prop-op-0001-2 --reason "Trace historique à laisser intacte"
```

Le système cherche une alternative calculée par le code (autre occurrence, par exemple). Il affiche `alternative <id>` si elle existe, sinon `no alternative: needs manual edit`.

**Laisser en attente** une question au client, avec un commentaire :

```bash
redactech review runs/<id> --pending prop-op-0001-2 --comment "Faut-il modifier la référence de l'IPD ?"
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

## 7. Contrôler le résultat

```bash
redactech check runs/<id>/out
```

Pour chaque fichier produit, affiche les problèmes **introduits** et **préexistants**, puis le total. La commande se termine avec le code `1` s'il reste une erreur introduite, `0` sinon.

Le journal complet du run est dans `runs/<id>/state.json` (champ `decisions_log`), avec l'horodatage de chaque décision.
