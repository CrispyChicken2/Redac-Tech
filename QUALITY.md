# Quality requirements & test policy

| Grid | What it asks | Where it lives in this file |
|---|---|---|
| **Q1** | You questioned and specified the quality requirements of your product | §1 Requirements |
| **Q2** | You defined how you'll know each requirement is met | §2 Verification |
| **Q3** | You actually ran those checks | §2 *Result* and *Evidence* columns |

---

## 1. Requirements (Q1)

### Critères qualité du projet (accordés avec le client)

| ID | Requirement | Characteristic | Metric & threshold | Why it matters (client need) | Validated by client? |
|---|---|---|---|---|---|
| REQ-1 | Exhaustivité : aucune modification nécessaire n'est oubliée | Functional suitability | Sur un scénario de test (contexte de modification + liste des modifications attendues, écrits à la main **avant** d'exécuter l'outil) : 100 % des modifications attendues faites, 0 hors liste | Les oublis (article, numéro de pièce manquant) sont l'erreur la plus fréquente de la reprise manuelle et nuisent à l'image professionnelle du client | ☑ notion 26/10, référent client (business analyst) · seuil ☐ |
| REQ-2 | Intégrité : le nouveau manuel ne contient que les changements acceptés, rien d'inventé ni de contraire au contexte | Functional suitability | 0 différence hors changements acceptés (diff XML ancien/nouveau) et 0 information inventée ou contraire au contexte de la modification | Une modification ne doit rien casser ailleurs dans le manuel : numéro de pièce erroné ou erreur de logique rendent le manuel faux | ☑ notion 26/10, référent client (business analyst) · seuil ☐ |
| REQ-3 | Homogénéité : les passages réécrits respectent le style du manuel | Functional suitability | ≥ 80 % des passages réécrits jugés « dans le style du manuel » par le référent client | Le manuel doit rester homogène (structure, forme, langue) : la ponctuation et le format font partie des erreurs relevées en reprise manuelle | ☑ notion 26/10, référent client (business analyst) · seuil ☐ |
| REQ-4 | Confidentialité des données : aucune donnée client dans le dépôt | Security & confidentiality | 0 fichier de données client versionné (contrôle `git ls-files` + `.gitignore`) | Documents techniques du client confidentiels, dépôt public | ☑ 26/10, référent client (business analyst) |
| REQ-5 | L'IA utilisée peut être remplacée par un modèle exécuté en local | Security & confidentiality | 100 % des appels à l'IA passent par un seul module ; passer à un modèle exécuté en local (aucune IA hébergée, même interne au client) ne demande qu'un changement de configuration | Chez le client, aucune donnée ne peut aller dans une IA hébergée, même interne : un simple numéro de pièce rend la donnée sensible | ☑ 26/10, référent client (business analyst) |

### Livrables → critères qualité

| Sprint | Livrable | Critères qualité (REQ) |
|---|---|---|
| 1 | Questions de cadrage | — (livré avant la définition des critères qualité du projet) |
| 2 | État de l'art restitué à l'oral | — (livré avant la définition des critères qualité du projet) |
| 3 | Note d'orientation + ≥ 2 approches comparées | REQ-1, REQ-2, REQ-5 |
| 3 | Scénario de test (`LRU1010`) écrit avant de coder | REQ-1, REQ-2 |
| 3 | Premier POC | REQ-1, REQ-2, REQ-4, REQ-5 |

Les critères d'acceptation de chaque livrable sont dans [PLANNING.md](PLANNING.md).

## 2. Verification (Q2 → Q3)

| ID | Verification method | Pass criterion | When (automatic / each sprint / before demo) | Owner | Result | Evidence |
|---|---|---|---|---|---|---|
| REQ-1 | Test automatique : modifications faites par l'outil comparées à la liste des modifications attendues du scénario | 100 % des modifications attendues faites, 0 hors liste | Automatique (à chaque commit) + en direct à la démo | ✏️ | ⏳ | |
| REQ-2 | Test automatique : diff XML ancien/nouveau limité aux changements acceptés + relecture du contexte | 0 différence hors changements acceptés, 0 information inventée | Automatique + démo | ✏️ | ⏳ | |
| REQ-3 | Revue par le référent client des passages réécrits | ≥ 80 % jugés dans le style | Démo du vendredi | ✏️ | ⏳ | |
| REQ-4 | Audit : `git ls-files` + vérification du `.gitignore` | 0 fichier de données client | Chaque sprint | ✏️ | ✅ | 26/10 : `git ls-files` = code et docs seulement ; `.gitignore` en place (données, archives, sorties générées, secrets) |
| REQ-5 | Revue de code : recherche de tous les appels à l'IA dans le code | Tous dans le même module ; le modèle (en ligne ou local) est choisi dans la configuration | Chaque sprint | ✏️ | ⏳ | |

> Status: ⏳ not run yet · ✅ pass · ⚠️ partial · ❌ fail (say what you'll do about it in the Evidence column)

## 3. Data & confidentiality rules

- Données de travail : uniquement des données **publiques**, à savoir la norme S1000D Issue 4.1 de l'ASD (Bike data set en XML et PDF, BREX par défaut). Le client ne nous fournit ni ses documentations, ni ses projets de rédaction passés, ni ses BREX internes (données sensibles).
- Data that must **never** be committed : toute donnée du client ; les archives téléchargées (`*.zip`) et le dossier `data/` (re-téléchargeables depuis le site de l'ASD) ; les sorties générées (`output/`, `*.docx`, `*.pdf`) ; les secrets (`.env`, clés d'API).
- Where the data actually lives (who has access): sur le poste de chaque membre, téléchargée depuis le site public de l'ASD.
- Tools/services **not** allowed by the client (e.g. public AI services): pendant le projet, tous les outils sont autorisés puisqu'on travaille sur des données publiques (l'objectif est de démontrer l'intérêt au client). À long terme, chez le client, aucune donnée ne doit aller dans une IA hébergée, même interne au client (un simple numéro de pièce rend la donnée sensible) : la solution doit pouvoir fonctionner avec un modèle exécuté en local, voire sans IA (voir REQ-5). Confirmé par le client le 26/10.
- Personal data involved (GDPR) and how it is handled: aucune (documentation technique publique d'un vélo).
- Matching `.gitignore` entries are in place: ☑ (26/10)
