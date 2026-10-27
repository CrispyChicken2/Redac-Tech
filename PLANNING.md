# Planning : automatisation de la rédaction de documentation technique

8 sprints d'une semaine, répartis sur le semestre (semaines projet). Engagement pris le lundi, preuve montrée au client le vendredi.
Les critères qualité du projet, accordés avec le client, sont dans [QUALITY.md](QUALITY.md).

## Vue d'ensemble

| Sprint | Semaine | Engagement (livrable du vendredi) | Critères qualité (REQ) | Tenu ? |
|---|---|---|---|---|
| 1 | 14/09 | Questions de cadrage posées au client (workshop mardi + réunion du vendredi) | — | ✅ |
| 2 | 05/10 | Documentation technique sur l'état de l'art, restituée à l'oral | — | ✅ |
| 3 | 26/10 | Orientation « reprise et modification » actée + exploration des approches + premier POC (ampleur à définir) | REQ-1, REQ-2, REQ-4, REQ-5 | ⏳ |
| 4 | 09/11 | ✏️ (soutenance de mi-parcours le 13/11) | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | Livraison finale | | |

## Critères d'acceptation des livrables

Ce sont les critères d'acceptation de chaque livrable ou fonctionnalité, distincts des critères qualité du projet de [QUALITY.md](QUALITY.md).

- **Sprint 2, état de l'art**
  - (a) Chacune des 4 pistes (conversion Word ↔ XML, compilation des données d'entrée, harmonisation de la rédaction, multilingue) a ≥ 1 approche sourcée ✅
  - (b) ≥ 2 pistes retenues avec le client à la restitution ✅ (09/10)
- **Sprint 3, note d'orientation** : besoin, périmètre, hors périmètre, questions ouvertes, ≥ 2 approches techniques comparées ; validée par écrit (Teams ou mail) par le référent client avant le 30/10 ⏳
- **Sprint 3, premier POC**
  - Traite le scénario `LRU1010` de bout en bout ⏳
  - Revue avant/après : le rédacteur voit chaque changement proposé et l'accepte, le refuse ou le met en attente avec un commentaire pour le client, sans notre aide (si inclus dans le premier POC, sinon sprint 4) ⏳

## Sprint 3 : engagement

**Objectif :** explorer les approches possibles pour automatiser la reprise et modification d'un manuel S1000D, puis livrer un premier POC sur le Bike (ampleur fixée en cours de semaine).

- [x] Orientation choisie avec le client (26/10)
- [ ] Note d'orientation + comparaison d'au moins 2 approches techniques, validée par le référent client (critère d'acceptation, voir ci-dessus)
- [ ] Scénario de test écrit avant de coder : contexte de modification + liste des modifications attendues (ex. pièce `LRU1010`) ; inclut un remplacement par lot (une pièce X2 → X3 sur toutes ses occurrences, lots jusqu'à 20 pièces) (REQ-1, REQ-2)
- [ ] Premier POC sur ce scénario (REQ-1, REQ-2 ; revue avant/après si incluse)
- [ ] Tests automatiques des exigences mesurables (REQ-1, REQ-2)
- [ ] Appels à l'IA isolés dans un seul module (REQ-5) + README (P-4)
- [x] `.gitignore` + règles de données (REQ-4)
- [ ] Poser au référent client les questions ouvertes : les « balises et blocs d'information » à traiter
- [ ] Faire valider par le client les seuils de REQ-1 à REQ-3 et les propositions P-1 à P-4 (30/10)

### Propositions de critères qualité à faire valider par le client

| ID | Proposition | Metric & threshold provisoire | Pourquoi |
|---|---|---|---|
| P-1 | Conformité S1000D | 100 % des data modules produits valides selon les XSD S1000D 4.1 et conformes au BREX par défaut | Format et ponctuation font partie des erreurs de la reprise manuelle ; vérification automatique, résultat binaire |
| P-2 | Temps de rédaction d'une reprise | Gain significatif par rapport à la reprise manuelle ; seuil à définir avec le client après avoir mesuré une reprise manuelle sur le scénario de test | Une modification de 50 à 100 étapes peut prendre une journée à la main (26/10) : fort gain possible |
| P-3 | Utilité | Note ≥ 3/5 donnée par le référent client | À confirmer avec le référent client |
| P-4 | Maintenabilité | Installation + exécution en ≤ 3 commandes en suivant le README, testé par un membre qui n'a pas écrit le code | Démarche PoC du client : des briques reprises ensuite par leur équipe |

À présenter au client vendredi 30/10 ; une proposition validée devient un REQ-x.

Hors périmètre pour l'instant : la détection des contradictions entre documents du client (étape d'analyse, à automatiser en dernier selon le client).

**Preuve de vendredi :** ✏️ à fixer une fois l'ampleur du POC connue. Par exemple : « on lance les tests en direct devant le référent client et REQ-1 et REQ-2 passent sur le scénario `LRU1010` ».

## Indicateurs

| Indicateur | S1 | S2 | S3 |
|---|---|---|---|
| Engagements tenus / pris | 1 / 1 | 1 / 1 | |
| Critères d'acceptation ✅ / total | – | 2 / 2 | |
| Critères qualité accordés avec le client | | – | 5, dont 3 seuils à confirmer |
