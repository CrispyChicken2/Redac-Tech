# Planning : automatisation de la mise à jour de documentation technique S1000D

Le projet avance par étapes d'une semaine. Chaque étape a un engagement pris au départ et une preuve montrée à la fin.
Les exigences qualité de chaque étape sont dans [QUALITY.md](QUALITY.md).

## Vue d'ensemble

| Étape | Engagement (livrable de fin d'étape) | Tenu ? |
|---|---|---|
| 1 | Questions de cadrage établies | ✅ |
| 2 | Documentation technique sur l'état de l'art, restituée à l'oral | ✅ |
| 3 | Orientation « reprise et modification » actée + exploration des approches + premier prototype | ⏳ |
| 4 | Revue avant / après et conformité BREX | |
| 5 | | |
| 6 | | |
| 7 | | |
| 8 | Livraison finale | |

## Étape 3 : engagement

**Objectif :** explorer les approches possibles pour automatiser la reprise et modification d'un manuel S1000D, puis livrer un premier prototype sur le Bike.

- [x] Orientation choisie
- [ ] Note d'orientation + comparaison d'au moins 2 approches techniques, validée par l'évaluateur (REQ-4)
- [ ] Scénario de test écrit avant de coder : contexte de modification + liste des modifications attendues (ex. pièce `LRU1010`) (REQ-5)
- [ ] Premier prototype sur ce scénario (REQ-5, REQ-6 ; REQ-7 si inclus)
- [ ] Tests automatiques des exigences mesurables (REQ-5, REQ-6)
- [ ] Appels à l'IA isolés dans un seul module (REQ-8) + README (REQ-9)
- [x] `.gitignore` + règles de données (REQ-3)

**Preuve de fin d'étape :** par exemple, lancer les tests en direct et montrer que REQ-5 et REQ-6 passent sur le scénario `LRU1010`.

## Indicateurs

| Indicateur | É1 | É2 | É3 |
|---|---|---|---|
| Engagements tenus / pris | 1 / 1 | 1 / 1 | |
| Exigences ✅ / total de l'étape | – | 3 / 3 | |
| Exigences validées par l'évaluateur | | 2 | |
