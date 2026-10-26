# Planning : automatisation de la rédaction de documentation technique (LGM)

8 sprints d'une semaine, répartis sur le semestre (semaines projet). Engagement pris le lundi, preuve montrée au client le vendredi.
Les exigences qualité de chaque sprint sont dans [QUALITY.md](QUALITY.md).

## Vue d'ensemble

| Sprint | Semaine | Engagement (livrable du vendredi) | Tenu ? |
|---|---|---|---|
| 1 | 14/09 | Questions de cadrage posées au client (workshop mardi + réunion du vendredi) | ✅ |
| 2 | 05/10 | Documentation technique sur l'état de l'art, restituée à l'oral | ✅ |
| 3 | 26/10 | Orientation « reprise et modification » actée + exploration des approches + premier POC (ampleur à définir) | ⏳ |
| 4 | 09/11 | ✏️ (soutenance de mi-parcours le 13/11) | |
| 5 | | | |
| 6 | | | |
| 7 | | | |
| 8 | | Livraison finale | |

## Sprint 3 : engagement

**Objectif :** explorer les approches possibles pour automatiser la reprise et modification d'un manuel S1000D, puis livrer un premier POC sur le Bike (ampleur fixée en cours de semaine).

- [x] Orientation choisie avec LGM (26/10)
- [ ] Note d'orientation + comparaison d'au moins 2 approches techniques, validée par Leny (REQ-4)
- [ ] Scénario de test écrit avant de coder : contexte de modification + liste des modifications attendues (ex. pièce `LRU1010`) (REQ-5)
- [ ] Premier POC sur ce scénario (REQ-5, REQ-6 ; REQ-7 si inclus)
- [ ] Tests automatiques des exigences mesurables (REQ-5, REQ-6)
- [ ] Appels à l'IA isolés dans un seul module (REQ-8) + README (REQ-9)
- [x] `.gitignore` + règles de données (REQ-3)

**Preuve de vendredi :** ✏️ à fixer une fois l'ampleur du POC connue. Par exemple : « on lance les tests en direct devant Leny et REQ-5 et REQ-6 passent sur le scénario `LRU1010` ».

## Indicateurs

| Indicateur | S1 | S2 | S3 |
|---|---|---|---|
| Engagements tenus / pris | 1 / 1 | 1 / 1 | |
| Exigences ✅ / total du sprint | – | 3 / 3 | |
| Exigences validées par le client | | 2 | |
