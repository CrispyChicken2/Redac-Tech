# Quality requirements & test policy

| Grid | What it asks | Where it lives in this file |
|---|---|---|
| **Q1** | You questioned and specified the quality requirements of your product | §1 Requirements |
| **Q2** | You defined how you'll know each requirement is met | §2 Verification |
| **Q3** | You actually ran those checks | §2 *Result* and *Evidence* columns + §3 Log |

Planning des sprints et engagements hebdomadaires : voir [PLANNING.md](PLANNING.md).

---

## 1. Requirements (Q1)

### Sprint 2 (semaine du 05/10) : livrable « état de l'art »

| ID | Requirement | Characteristic | Metric & threshold | Why it matters (client need) | Validated by client? |
|---|---|---|---|---|---|
| REQ-1 | L'état de l'art couvre les 4 pistes d'automatisation identifiées avec LGM au sprint 1 | Functional suitability | ≥ 1 approche/outil documenté (avec source) pour chacune des 4 pistes : (a) conversion Word ↔ XML, (b) compilation des données d'entrée, (c) harmonisation de la rédaction (structure, forme, langue), (d) multilingue | LGM doit pouvoir choisir où automatiser en connaissant les options | ☑ 09/10, Leny |
| REQ-2 | La restitution permet de dégager des orientations de projet concrètes | Usability | ≥ 2 pistes retenues avec le client à la fin de la restitution | Le sujet est vaste : il faut réduire le périmètre pour le semestre | ☑ 09/10, Leny (retenues : (b) compilation des données d'entrée + ✏️) |
| REQ-3 | Aucune donnée client dans le dépôt | Security & confidentiality | 0 fichier de données client versionné (contrôle du `git ls-files` + `.gitignore`) | Documents techniques LGM confidentiels | ☑ 26/10, Leny (on travaille uniquement sur S1000D public) |

### Sprint 3 (semaine du 26/10) : orientation « reprise et modification » + premier POC

Orientation actée avec LGM le 26/10 : automatiser la **rédaction des reprises et modifications** d'un manuel existant.
Aujourd'hui : ancien manuel + contexte de la modification → analyse → rédaction manuelle dans Arbortext (étape sans valeur ajoutée et la plus sujette aux erreurs : oublis, balises, blocs d'information) → nouveau manuel.
Cible : **à partir de l'ancien manuel et du contexte de la modification, l'outil rédige les reprises comme le ferait un rédacteur** et produit le nouveau manuel. Cela inclut de propager une modification partout (ex. pièce X2 → X3) sans reprise manuelle. Le rédacteur contrôle le résultat dans une **revue avant/après type git**, où il accepte ou refuse chaque changement.
Ce sprint est **exploratoire** : l'approche technique et l'architecture ne sont pas encore choisies, et l'ampleur du premier POC sera fixée en cours de semaine.
Les exigences ci-dessous ne dépendent pas de l'approche : elles reprennent la définition de la qualité donnée par LGM au workshop (**exhaustivité**, **intégrité**, homogénéité) et se mesurent sur un scénario de test du Bike (ex. la pièce `LRU1010`, 4 occurrences dans 3 data modules).

| ID | Requirement | Characteristic | Metric & threshold | Why it matters (client need) | Validated by client? |
|---|---|---|---|---|---|
| REQ-4 | L'orientation et les pistes techniques explorées sont écrites et validées par le client | Functional suitability | Note d'orientation (besoin, périmètre, hors périmètre, questions ouvertes, ≥ 2 approches techniques comparées) validée par Leny avant vendredi 30/10 | Le projet était flou : on doit viser le même besoin que LGM | ☐ |
| REQ-5 | Exhaustivité : aucune modification nécessaire n'est oubliée | Functional suitability (exhaustivité) | Pour un scénario de test sur le Bike (ex. « la pièce `LRU1010` est remplacée par … ») composé d'un **contexte de modification** et de la **liste des modifications attendues** (ce qu'un rédacteur changerait), tous deux écrits à la main **avant** d'exécuter l'outil : 100 % des modifications attendues sont faites, 0 modification hors liste | Les oublis sont l'erreur la plus fréquente de la reprise manuelle | ☐ |
| REQ-6 | Intégrité : le nouveau manuel ne contient que les changements acceptés et reste conforme | Functional suitability (intégrité) | 0 différence hors changements acceptés (diff XML ancien / nouveau) et 100 % des data modules produits valides selon les XSD S1000D 4.1 | Une modification ne doit rien casser ailleurs dans le manuel | ☐ |
| REQ-7 | Le rédacteur garde la main : il voit l'avant/après et choisit (si inclus dans le premier POC, sinon sprint 4) | Usability | Leny réalise le scénario (accepter/refuser chaque changement proposé) sans notre aide, et note l'utilité ≥ ✏️ 3/5 | Demande explicite de LGM : un fonctionnement « comme git » | ☐ |
| REQ-8 | Confidentialité à long terme : l'IA utilisée peut être remplacée par un modèle hébergé en local | Security & confidentiality | 100 % des appels à l'IA passent par un seul module ; passer d'un LLM en ligne à un modèle local ne demande qu'un changement de configuration | Chez LGM, les données client ne peuvent pas aller dans un LLM externe | ☐ |
| REQ-9 | Le POC se lance sans nous | Maintainability | Installation + exécution en ≤ 3 commandes en suivant le README, testé par un membre qui n'a pas écrit le code | Démarche PoC de LGM : des briques reprises ensuite par leur équipe | ☐ |

### Cibles du projet (seuils provisoires)

Indicateurs issus du workshop avec LGM. Ils ne dépendent pas de l'approche technique ; chacun deviendra une exigence REQ-x au sprint où le POC pourra le mesurer. Les seuils sont fixés **avant** de voir les résultats et ajustés après la première mesure.

| Indicateur | Seuil provisoire | Justification |
|---|---|---|
| Temps de rédaction d'une reprise | Gain significatif par rapport à la reprise manuelle (seuil à définir avec LGM) | Première étape : mesurer le temps d'une reprise faite à la main sur le scénario de test |
| Exhaustivité | 100 % des endroits à modifier traités | Zéro tolérance : un oubli rend le manuel de maintenance faux |
| Intégrité / véracité | 0 information inventée ou contraire au contexte de la modification | Zéro tolérance : même raison |
| Conformité | 100 % des data modules valides (XSD) et conformes au BREX par défaut | Vérification automatique, résultat binaire |
| Homogénéité du style | ≥ 80 % des passages réécrits jugés « dans le style du manuel » par Leny | À confirmer avec Leny |
| Utilité | Note ≥ 3/5 donnée par Leny | À confirmer avec Leny |

## 2. Verification (Q2 → Q3)

| ID | Verification method | Pass criterion | When (automatic / each sprint / before demo) | Owner | Result | Evidence |
|---|---|---|---|---|---|---|
| REQ-1 | Checklist : tableau pistes × approches dans le document d'état de l'art | Chacune des 4 pistes a ≥ 1 approche sourcée | Avant la restitution | ✏️ | ✅ | ✏️ lien vers le document / slides d'état de l'art |
| REQ-2 | Revue avec le client à la restitution orale | ≥ 2 orientations notées dans le compte rendu | Démo du vendredi | ✏️ | ✅ | ✏️ lien vers le compte rendu de réunion (2 sujets retenus) |
| REQ-3 | Audit : `git ls-files` + vérification du `.gitignore` | 0 fichier de données client | Chaque sprint | ✏️ | ✅ | 26/10 : `git ls-files` = code et docs seulement ; `.gitignore` ajouté (données, archives, sorties générées, secrets) |
| REQ-4 | Revue de la note d'orientation par Leny | Validation écrite (message Teams ou mail) | Avant le 30/10 | ✏️ | ⏳ | |
| REQ-5 | Test automatique : modifications faites par l'outil comparées à la liste des modifications attendues du scénario | 100 % des modifications attendues faites, 0 hors liste | Automatique (à chaque commit) + en direct à la démo | ✏️ | ⏳ | |
| REQ-6 | Test automatique : diff XML ancien/nouveau + validation XSD de chaque data module produit | 0 différence hors changements acceptés, 100 % valides | Automatique (à chaque commit) + en direct à la démo | ✏️ | ⏳ | |
| REQ-7 | Test utilisateur : Leny déroule le scénario seul, puis note l'utilité | Scénario terminé sans aide, note ≥ seuil fixé avant la démo | Démo du vendredi | ✏️ | ⏳ | |
| REQ-8 | Revue de code : recherche de tous les appels à l'IA dans le code | Tous dans le même module, modèle choisi dans la configuration | Chaque sprint | ✏️ | ⏳ | |
| REQ-9 | Test utilisateur interne : un membre suit le README sur une machine propre | ≤ 3 commandes, sans aide | Avant démo | ✏️ | ⏳ | |

> Status: ⏳ not run yet · ✅ pass · ⚠️ partial · ❌ fail (say what you'll do about it in §3)

## 3. Log (one entry per project week)

### Semaine du 14/09 (sprint 1)
- Added: pas encore d'exigences qualité (semaine de cadrage).
- Checked: workshop du mardi (le client n'a pas pu être présent tout du long) ; on a monté la liste des questions de cadrage pendant la semaine.
- Shown to client: nos questions de cadrage, à la réunion hebdomadaire du vendredi (c'était le livrable du sprint, validé comme tel par l'encadrement). Le client nous oriente vers la norme publique S1000D 4.1 (Bike data set, BREX par défaut), puisque ses propres données sont sensibles.
- Next: état de l'art des 4 pistes citées au départ.

### Semaine du 05/10 (sprint 2)
- Added: REQ-1 à REQ-3 (état de l'art, orientations, confidentialité).
- Checked: couverture de l'état de l'art (REQ-1 ✅), orientations dégagées avec le client (REQ-2 ✅).
- Shown to client: restitution orale de l'état de l'art sur les 4 pistes. Retour client : ✏️ ; 2 pistes retenues (compilation des données d'entrée + ✏️), choix pas encore acté. Le script XML → Word (`converter/`) commencé en parallèle est mis en suspens.
- Next: rendez-vous avec l'équipe rédaction le 26/10 pour acter l'orientation, puis premier POC.

### Semaine du 26/10 (sprint 3)
- Added: orientation actée avec LGM : reprise et modification de manuels existants. REQ-4 à REQ-9 (note d'orientation, exhaustivité, intégrité, revue avant/après, confidentialité, maintenabilité).
- Questions ouvertes : la notion de « conflit » évoquée par LGM (conflits d'écriture entre modifications ?) ; les « balises et blocs d'information » à traiter ; à poser à Leny sur Teams.
- Checked: REQ-3 audit du dépôt : aucune donnée client versionnée, `.gitignore` ajouté → ✅. Le POC XML → Word (`converter/`) est mis en suspens au profit de l'orientation choisie.
- Shown to client: (à remplir vendredi)
- Next:

## 4. Data & confidentiality rules

- Données de travail : uniquement des données **publiques**, à savoir la norme S1000D Issue 4.1 de l'ASD (Bike data set en XML et PDF, BREX par défaut). LGM ne nous fournit ni ses documentations, ni ses projets de rédaction passés, ni ses BREX internes (secteur défense, données sensibles).
- Data that must **never** be committed : toute donnée LGM ; les archives téléchargées (`*.zip`) et le dossier `data/` (re-téléchargeables depuis le site de l'ASD) ; les sorties générées (`output/`, `*.docx`, `*.pdf`) ; les secrets (`.env`, clés d'API).
- Where the data actually lives (who has access): sur le poste de chaque membre, téléchargée depuis le site public de l'ASD.
- Tools/services **not** allowed by the client (e.g. public AI services): pendant le projet, tous les outils sont autorisés puisqu'on travaille sur des données publiques (l'objectif est de démontrer l'intérêt à LGM). À long terme, chez LGM, aucune donnée client ne doit aller dans un LLM externe : la solution doit pouvoir fonctionner avec une IA hébergée en local, voire sans IA (voir REQ-8). Confirmé par LGM le 26/10.
- Personal data involved (GDPR) and how it is handled: aucune (documentation technique publique d'un vélo).
- Matching `.gitignore` entries are in place: ☑ (26/10)
