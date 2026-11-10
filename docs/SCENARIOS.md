# Scénarios de bout en bout

Un scénario lance l'orchestrateur sur une entrée figée, puis compare les fichiers produits à ce qui était attendu. Le code est dans `src/redactech/pipeline/scenarios.py` ; les scénarios sont dans `tests/scenarios/`.

Les scénarios existent pour prouver les exigences de `QUALITY.md`. Ils complètent les tests unitaires : ils vérifient le résultat final, pas seulement les fonctions.

## Principe : l'attendu est écrit avant

`attendu.yaml` est rédigé **à partir des fichiers d'entrée**, avant toute exécution, et jamais à partir de la sortie de l'outil. Un scénario qui passe prouve donc que la sortie correspond à ce qu'un humain avait déjà identifié comme attendu.

Deux fichiers par scénario, dans un dossier `tests/scenarios/<nom>/` :

| Fichier | Rôle |
|---|---|
| `scenario.yaml` | l'entrée : source, demande, politique, décisions, limite de temps, variantes |
| `attendu.yaml` | ce qui doit sortir : fichiers, changements, éléments intacts, comptes, problèmes |

Le dossier `tests/scenarios/_schemas/` contient `dmodule.xsd`, un schéma minimal utilisé par défaut pour la validité. Les dossiers dont le nom commence par `_` ne sont pas des scénarios.

## Format de `scenario.yaml`

| Clé | Obligatoire | Sens |
|---|---|---|
| `description` | non | texte libre |
| `markers` | non | liste de marqueurs de données (`data41`, `data42`). Si les données manquent, le scénario est **sauté**, pas échoué. |
| `source` | oui | d'où viennent les documents (voir ci-dessous) |
| `request` | oui | la demande : `mapping` (liste de lignes `old`, `new`, `reason`, écrite en CSV) ou `form` (`kind`, `target`, `params`, `reason`) |
| `version_policy` | non | `none`, `in_work` ou `new_issue`. Défaut : `none`. |
| `decisions` | non | `auto_accept: true` accepte les propositions certaines et sans problème ; `accept_certainty: [probable]` accepte aussi les niveaux listés pour les zones de contenu |
| `max_seconds` | non | durée maximale du run ; dépassée, le scénario échoue |
| `pending` | non | texte : le scénario est sauté, en attendant son attendu |
| `variants` | non | liste de `{id: …, <clé>: <valeur>}` : chaque variante remplace les clés du haut du scénario et est exécutée séparément |

**`source`** :

- `kind: fixtures` et `files: [...]` : les fichiers listés sont **copiés** depuis `tests/fixtures/s1000d/` dans un dossier temporaire. Les sources d'origine ne sont jamais touchées.
- Tout autre `kind` (par exemple `bike41`) : `path` (dossier des données, relatif à la racine du dépôt), `brex_dirs` (liste), `schemas_dir` (facultatif), `issue`. Les données sont lues **sur place** ; leur empreinte SHA-256 est vérifiée après le run.

## Format de `attendu.yaml`

| Clé | Sens |
|---|---|
| `outputs` | liste exacte des noms de fichiers produits (noms après versioning) |
| `unchanged` | motifs (`*` autorisé) de **noms de fichiers source** qui doivent rester intacts : ni fichier produit, ni modification de la source |
| `changes` | liste des changements attendus (voir ci-dessous) |
| `also_allowed` | par document, des XPath d'éléments où un changement est permis en plus (`side: before` ou `after`) |
| `output_counts` | par fichier produit, des XPath avec le nombre attendu d'éléments dans la sortie |
| `checks` | `introduced_errors` (nombre exact d'erreurs introduites, en général `0`) ; `pre_existing_min` (minimum de problèmes préexistants signalés) |
| `blocked` | nombre exact de propositions `blocked_by_rule` attendues |
| `xsd` | `minimal` (défaut : `_schemas/dmodule.xsd`) ou `real` (schémas de la source ; échoue si le dossier manque) |
| `variants` | par identifiant de variante, des clés qui remplacent celles du haut (typiquement `outputs` et `output_counts`) |

**Un changement attendu** (entrée de `changes`) :

| Clé | Sens |
|---|---|
| `doc` | nom du fichier **source** concerné |
| `before_xpath` | élément de l'entrée à retrouver (sert à vérifier l'attendu lui-même) |
| `before_contains` | textes qui doivent se trouver dans l'élément d'entrée. Absents : l'attendu est incohérent et le scénario échoue. |
| `scope_xpath` | élément de la **sortie** où le changement doit être |
| `after_contains` / `after_absent` | textes qui doivent / ne doivent pas figurer dans cet élément de sortie |
| `marks` | attributs de marquage attendus sur un élément de la portée (ex. `changeMark: "1"`, `changeType: delete`) |
| `change_type` | genre de changement, documentaire |

Un changement de la sortie qui n'est couvert par aucune portée déclarée est une **erreur** (« unexpected change »).

## Mesures

Elles figurent dans `Result.metrics`, toutes entre 0 et 1 sauf le temps :

| Mesure | Sens |
|---|---|
| `exhaustiveness` | part des changements attendus effectivement trouvés |
| `precision` | part des éléments modifiés qui étaient attendus |
| `preservation` | part des documents qui devaient rester intacts, et l'étaient |
| `validity` | part des fichiers produits valides contre le schéma |
| `traceability` | part des fichiers modifiés dont les marques et motifs sont cohérents |
| `seconds` | durée du run |

Un scénario **réussit** si tous ses contrôles passent. Les mesures ne remplacent pas les contrôles : une mesure à 1 avec un contrôle en échec reste un échec.

## Liste des scénarios

| Scénario | Ce qu'il fait | Exigence prouvée |
|---|---|---|
| `lru1010` | remplace `LRU1010` par `LRU2020` dans un répertoire commun (deux déclarations), dans un catalogue de pièces (une référence) et dans un paragraphe (texte libre, `probable`, accepté). Le fichier UPF reste intact. | **REQ-5** (exhaustivité : 3 changements attendus, 0 hors liste), **REQ-6** (intégrité : rien d'autre ne change, sorties valides) |
| `lru1010_bike41` | même remplacement sur les **vraies données Bike 4.1** (marqueur `data41`). Les deux traces UPF restent intactes. Validité contre les schémas réels. | **REQ-5**, **REQ-6**, **REQ-10**, **REQ-11** ; sautée sans les données |
| `delete_mark` | `delete_step` sur l'étape `stp-0003` : l'étape reste dans le document, marquée `changeType="delete"`, et rien d'autre ne change. | **REQ-10** (traçabilité : marque `delete`, aucune suppression avant nouvelle issue) |
| `versioning` | le même changement de texte sous les trois politiques (`none`, `in_work`, `new_issue`), sur un document en issue 007-00 portant trois marques d'un cycle précédent. Une seule consolidation, lors d'une nouvelle issue. | **OBJ-21** (trois politiques, renommage, journal) |
| `preexisting_brex` | un changement de libellé sur un document qui viole déjà sa règle BREX et contient un élément inconnu du schéma. Les problèmes sont classés préexistants, rien n'est introduit, et la sortie est livrée. | **OBJ-22** (erreurs préexistantes jamais imputées à l'outil) ; **REQ-11** (aucune erreur introduite) |

Le scénario `lru1010` reprend le remplacement de `docs/DEMO.md`, mais avec décisions automatiques. Il attend **trois** changements, car il compte aussi la mention en texte libre (niveau `probable`), que `docs/DEMO.md` ne mentionne pas et que le rédacteur doit décider à la main. `QUALITY.md` (REQ-5) parle de « 2/2 modifications » : ce chiffre ne couvre que les deux occurrences structurées. Les deux documents ne comptent donc pas la même chose.

Un scénario peut prouver plusieurs exigences : la colonne « Exigence prouvée » cite d'abord celle qui motive sa présence.

## Variantes

Une variante exécute le même scénario avec d'autres valeurs. Exemple : `versioning` a trois variantes, une par politique.

- Dans `scenario.yaml` : `variants: [{id: none, version_policy: none}, …]`.
- Dans `attendu.yaml` : `variants: {none: {outputs: [...], output_counts: {...}}, …}`.

Une variante ne peut remplacer que les clés de premier niveau. Les clés remplacées le sont en entier (par exemple `output_counts` n'est pas fusionné).

## Ajouter un scénario

1. Choisir les **fichiers d'entrée** dans `tests/fixtures/s1000d/` (ou les données réelles, avec un marqueur).
2. Créer `tests/scenarios/<nom>/` avec `scenario.yaml` (source, demande, politique, décisions).
3. **Avant d'exécuter**, rédiger `attendu.yaml` à partir des fichiers d'entrée : quels éléments changent, lesquels doivent rester intacts, quels fichiers doivent sortir, combien de problèmes. Ne pas le copier depuis une sortie.
4. Lancer le scénario. S'il échoue, déterminer lequel est faux : l'outil, ou l'attendu. Ne modifier l'attendu qu'avec une raison documentée dans le fichier.
5. Ajouter le scénario à la liste ci-dessus, avec l'exigence qu'il prouve, et mettre à jour `docs/CHANGELOG.md`.

## Lancer les scénarios

Par `pytest` (CI) : `tests/scenarios/test_scenarios.py` crée un test par scénario et par variante. Un scénario sans ses données est sauté avec sa raison.

Par la CLI, depuis la racine du dépôt :

```bash
redactech eval tests/scenarios/
redactech eval tests/scenarios/ --out runs/
```

La commande affiche, pour chaque scénario, `PASS`, `FAIL` ou `SKIP` avec la raison, puis la liste des échecs. Elle écrit le rapport `runs/eval_<date>.md` et se termine avec le code `1` si un scénario échoue.

## Colonnes du rapport `eval_<date>.md`

| Colonne | Contenu |
|---|---|
| `scenario` | nom du scénario, suivi de `[variante]` si elle existe |
| `status` | `PASS`, `FAIL`, ou `skipped: <raison>` |
| `exhaustiveness`, `precision`, `preservation`, `validity`, `traceability` | les cinq mesures, entre 0 et 1 |
| `introduced / pre-existing` | nombre d'erreurs introduites / de problèmes préexistants relevés dans les sorties |
| `time (s)` | durée du run |

Sous le tableau, une ligne `- <scénario>: <message>` par échec, avec le détail.

Un scénario sauté n'a que sa ligne `skipped`, sans mesures.
