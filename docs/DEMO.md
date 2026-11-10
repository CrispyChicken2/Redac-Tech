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
redactech request --mapping lots.csv --version-policy in_work
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

**Rouvrir** une décision déjà prise :

```bash
redactech review runs/<id> --reopen <id-probable>
```

Une proposition décidée ne se décide pas une seconde fois : `--accept` ou `--reject` sur elle sont refusés. Pour la changer, il faut la rouvrir. Elle redevient à décider (`reopened <id>: proposed`), et les alternatives encore ouvertes qui la remplaçaient sont rejetées, avec le motif « superseded by reopened proposal ». La réouverture est refusée si l'une de ces alternatives est déjà acceptée ou éditée : il faut alors rouvrir celle-ci d'abord.

Une demande **bloquée par une règle** ne se rouvre pas, mais une demande mise en attente pour le client revient à l'état bloqué si elle l'était avant : elle ne reçoit jamais une nouvelle tentative.

## 6. Écrire

```bash
redactech write runs/<id>
```

Écrit les propositions `accepted` ou `edited` dans `runs/<id>/out/`, sous leur nouveau nom de fichier. Les propositions `rejected` et `pending_client` ne sont pas écrites, et ne sont pas listées non plus. Les documents en lecture seule sont ignorés et affichés avec leur raison. Les illustrations, signalées sans changement, ne sont pas écrites.

La commande refuse tant qu'une proposition est encore `proposed` (hors illustrations) : le rédacteur doit décider de toutes.

Deux propositions appliquées ne peuvent pas être de la même famille : même zone et même demande, l'une étant une variante de l'autre. Dans ce cas, `write` refuse et demande d'en garder une seule (« mutually exclusive »).

Si des propositions sont **mises en attente pour le client**, l'écriture a lieu, mais la commande affiche un avertissement suivi de la liste des questions ouvertes :

```text
warning: 2 questions client ouvertes (en attente)
  - prop-op-0001-2 (DMC-…): Faut-il traiter cette mention ?
```

Il ne bloque pas l'écriture : il rappelle seulement que ces points restent ouverts. La commande `request` ne l'affiche que si elle écrit elle-même (option cachée `--auto-accept`, réservée aux tests).

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

## 10. Parcours dans l'interface

Ce parcours reprend le scénario de la section 4 à 6, sur le workspace des fixtures, mais dans l'interface graphique. Les libellés ci-dessous sont ceux de `src/redactech/ui/`. Ne pas le lancer depuis un poste sans les dépendances installées.

### Lancer

Depuis la racine du dépôt :

```bash
streamlit run src/redactech/ui/app.py
```

L'interface s'ouvre dans le navigateur. Elle n'a aucune logique métier : elle appelle l'orchestrateur, les vues et les fichiers de livraison. Le dossier de session est créé sous `runs/_ui/` au chargement du projet, avant tout téléversement.

### Panneau « Projet » (barre latérale)

1. Le champ **Fichier workspace** est prérempli avec `workspace.toml` s'il existe, sinon `workspace.example.toml`. Cliquer sur **Charger le projet**. Choisir le workspace des fixtures, comme dans la section 1 de ce guide.
2. **Sources** : pour chaque source, son identifiant, son mode (`modifiable` ou `lecture seule`), son dossier et le nombre de fichiers par rôle.
3. **Ajouter des fichiers** : déposer des DM, des BREX ou des ICN dans **Déposer des DM, BREX ou ICN**, puis cliquer sur **Importer**. Chaque fichier est affiché avec son rôle, ou refusé avec sa raison. Importer des fichiers remet à zéro le run en cours, s'il y en a un : ses propositions seraient périmées, et il faut relancer la demande.
4. **Changer de BREX** : déposer un fichier de BREX (022) dans **Déposer un BREX (022)**, puis cliquer sur **Remplacer le BREX**. Les chaînes de BREX sont résolues à nouveau, et l'état initial est recalculé. Le run en cours est remis à zéro, comme après un import : il faut relancer la demande. Le fichier de BREX d'origine n'est pas modifié.
5. **Problèmes préexistants** : une ligne par DM, avec le nombre d'erreurs et d'avertissements. Un clic ouvre le détail.

**Charger le projet** et chaque import réindexent et revérifient tout le workspace. C'est lent sur le jeu Bike complet ; sur les fixtures, la durée est négligeable.

### Onglet « Demande »

1. Choisir le mode **Tableau CSV/XLSX** (ou **Formulaire**, qui construit une liste d'opérations). Avec le tableau, déposer le fichier dans **Tableau de correspondance (colonnes old, new, kind, reason)**. Avec `lots.csv` de la section 4, c'est la ligne `LRU1010;LRU2020`. En mode **Formulaire**, chaque opération se remplit (type, document, élément, champs, motif), puis se place dans la liste avec **Ajouter l'opération** ; **Retirer** enlève une ligne. Plusieurs opérations peuvent ainsi être demandées ensemble.
2. Cliquer sur **Préparer**. Si la demande est refusée, le message donne la raison ; aucun run n'est créé.
3. Le run apparaît avec son tableau d'opérations. Le panneau **Politique de versionnement** affiche la **Suggestion** et ses motifs, un par ligne.
4. Choisir la politique parmi les trois options libellées (**Aucune (le fichier garde son numéro)**, **Travail en cours (inWork + 1)**, **Nouvelle issue (consolidation)**), puis cliquer sur **Confirmer et préparer les propositions**. Cette étape calcule les zones, les propositions et les contrôles, et ouvre les décisions.

Le choix de la politique est un panneau de l'onglet, pas une fenêtre modale. Aucune proposition n'existe avant ce choix.

Cliquer sur **Nouvelle demande** pour quitter le run en cours et revenir au formulaire. Le dossier du run reste sur le disque, dans `runs/`.

### Onglet « Document et propositions »

1. Choisir le **Document** dans la liste, puis une **Vue** parmi **XML**, **Publiée (IETP)** et **Côte à côte**.
2. Cocher **Masquer les suppressions** pour ne pas afficher les éléments marqués supprimés dans la vue publiée.
3. La colonne de droite liste les propositions. Par défaut, seules celles du document choisi apparaissent (case **Seulement ce document**, cochée).
4. Chaque proposition est un volet titré `<identifiant> — <statut>`, avec les badges de contrôle (**Préexistant : …** en gris, **Introduit : …** en rouge, **À vérifier (illustration)**), l'extrait avant / après, et les boutons de décision :
   - **Accepter** ;
   - **Éditer** : modifie le texte **Édition du XML** puis valide ; le XML est revérifié, et refusé s'il introduit une erreur ;
   - **Rejeter** : exige un **Motif du rejet**. L'interface affiche alors `<id> rejetée : alternative <id> proposée.` ou `<id> rejetée : édition manuelle nécessaire.` ;
   - **En attente** : exige un **Commentaire pour le client** ; la proposition passe **En attente du client**.
5. **Bloquées par une règle (n)** : panneau replié, ouvert s'il y a des demandes bloquées. Chaque demande montre la règle et la question pré-remplie. **Poser la question au client** la met en attente.
6. **Tout accepter** n'accepte que les propositions que le pipeline juge certaines et sans problème. Il ne décide rien d'autre. Le message indique combien ont été acceptées et combien restent à décider.

Pour une illustration signalée, l'interface n'offre ni édition ni rejet : seulement **Accepter** (acquittement) et **En attente**.

**Rouvrir** : une proposition déjà décidée (accepter, éditer, rejeter, en attente) affiche un bouton **Rouvrir** sous son volet. Il la remet à décider. Les alternatives encore ouvertes qui la remplaçaient sont rejetées ; le bouton est refusé si l'une d'elles est déjà acceptée ou éditée. Une demande bloquée par une règle n'a pas de bouton **Rouvrir**.

### Onglet « Livraison »

1. Six compteurs, un par statut : **À décider**, **Acceptée**, **Éditée**, **Rejetée**, **En attente du client**, **Bloquée par une règle**.
2. La politique choisie est affichée. Tant qu'une proposition reste à décider, un avertissement l'indique.
3. **Écrire les DM** n'est actif que si une politique est choisie et qu'aucune décision n'est en attente. Un message de succès indique le dossier `out/`.
4. Une fois écrit, le panneau **Téléchargements** propose :
   - **DM écrits (zip)** ;
   - **Rapport (HTML)** et **Rapport (JSON)** ;
   - **Questions (CSV)** et **Questions (XLSX)** ;
   - **Décisions (JSONL)**.

Les rapports et exports sont ceux décrits dans « Livrables d'un run » de `docs/ARCHITECTURE.md`. Le fichier XLSX des questions (`questions.xlsx`) est écrit une fois, à l'écriture des DM, dans le dossier du run. La page ne le régénère que s'il manque, par exemple pour un run repris depuis une écriture plus ancienne.

## 11. Demande en texte libre (modèle local)

Cette section est optionnelle. Elle demande un modèle local : Ollama doit tourner sur ce poste, et le modèle indiqué dans `config.toml` doit être disponible. Les tests n'ont pas besoin d'Ollama : ils rejouent des réponses enregistrées.

### Prérequis

Dans `config.toml`, section `[llm]` :

```toml
[llm]
provider = "ollama"
model = "ministral-3:8b"
```

Sans ce réglage (`provider = "none"`, valeur par défaut), la demande en texte libre n'est pas disponible. La commande le signale, et l'interface affiche : « Le texte libre nécessite le modèle local ([llm] provider dans config.toml). »

### Ligne de commande

```bash
redactech request --text "Remplacer la pièce LRU1010 par LRU2020 dans toute la documentation." --version-policy in_work
```

L'option `--text` remplace `--mapping` : il faut l'une ou l'autre, pas les deux. Le reste est identique à la section 4 : la commande s'arrête au point de décision, puis `review`, `write` et `check`. Les questions soulevées par la lecture de la demande sont affichées avec le préfixe `question (free text)`.

### Interface

Dans l'onglet **Demande**, un panneau **Texte libre** apparaît seulement si `[llm] provider` n'est pas `none`. Il contient la zone **Décrivez la modification (français ou anglais)** et le bouton **Préparer (texte libre)**.

### Ce qui se passe

1. Le modèle propose des opérations au format JSON, avec pour chacune la citation exacte de la demande qui la justifie.
2. Le code vérifie chaque proposition, et rien de ce que dit le modèle n'est cru sur parole :
   - chaque citation doit être un passage exact de la demande ;
   - chaque valeur écrite (numéro de pièce, texte, identifiant, quantité) doit figurer dans la demande ;
   - l'ancienne valeur d'un remplacement doit exister dans la documentation ;
   - le document visé doit appartenir au projet ;
   - le motif écrit dans le module livré est construit par le code à partir de la demande.
3. Une opération qui échoue à une vérification n'est pas appliquée : elle devient une **question**. Par exemple, si le modèle invente `LRU9999` alors que la demande ne contient que `LRU1010`, l'opération est refusée et la question demande la valeur exacte.
4. Les opérations qui passent sont traitées comme celles d'une table de correspondances : localisation, propositions, décisions du rédacteur, écriture.

### Journal des appels

Chaque appel au modèle est journalisé, sans le texte du prompt (seulement son empreinte). Pendant la demande, le journal s'écrit dans `runs/<id>.llm_calls.jsonl`, à côté des runs. Une fois le run créé, il est déplacé dans `runs/<id>/llm_calls.jsonl`. Si l'appel échoue, le journal reste à côté des runs, et l'erreur est affichée.

Voir `docs/ARCHITECTURE.md`, sections « Couche IA locale » et « Demande, localisation et propositions ».

## 12. Assistant (optionnel)

L'assistant est un panneau à droite de l'interface, toujours visible quand un projet est chargé. Il répond à deux sortes de messages. Il n'existe pas de commande en ligne de commande pour lui : c'est une fonction de l'interface.

### Questions sur l'état du run

Exemples : « récap », « erreurs », « en attente », « bloqué », « quelles pièces modifiées ? » (en anglais aussi : « recap », « errors », « pending », « blocked », « changed parts »).

La réponse est une liste à puces, **calculée par le code** à partir de l'état du run :

- les pièces modifiées, par document ;
- les erreurs introduites et les erreurs préexistantes ;
- les points mis en attente pour le client, avec leur commentaire ;
- les demandes bloquées par une règle.

Cette liste est toujours la réponse. Si un modèle local est configuré, il peut en proposer une reformulation : elle s'affiche **en dessous**, sous le titre « Reformulation du modèle (non vérifiée) ». Elle ne remplace jamais la liste.

Un message qui mélange une question et une modification reçoit la liste, suivie de la note : « La modification demandée n'a pas été traitée : envoyez-la en message séparé. »

### Demandes de modification

Exemple : « Remplacer la pièce LRU1010 par LRU2020 dans toute la documentation. »

Le message passe par la même lecture que le texte libre de la section 11 : mêmes vérifications, même refus des valeurs inventées, mêmes questions. Les opérations qui passent sont **ajoutées au run** : elles sont localisées, préparées et vérifiées comme les premières, puis attendent les décisions du rédacteur. Rien n'est appliqué par l'assistant lui-même.

Une demande de modification exige un modèle local (`[llm] provider` différent de `none`). Sinon, l'assistant répond : « Une demande en texte libre nécessite le modèle local ».

Un run déjà écrit ne reçoit plus de changement : l'assistant le signale.

### Champs et boutons

- **Votre message** : zone de saisie.
- **Envoyer** : envoie le message (inactif si la zone est vide).
- **Voir les propositions** : affiche les propositions de tous les documents, et pas seulement celles du document choisi.

Le panneau rappelle aussi l'onglet où décider : « Onglet « Document et propositions » : les propositions à décider. »
