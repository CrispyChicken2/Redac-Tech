# Quality requirements & test policy — RedacTech (client: LGM Group)

| Grid | What it asks | Where it lives in this file |
|---|---|---|
| **Q1** | You questioned and specified the quality requirements of your product | §1 Requirements |
| **Q2** | You defined how you'll know each requirement is met | §2 Verification |
| **Q3** | You actually ran those checks | §2 *Result* and *Evidence* columns + §3 Log |

Planning and milestones: [PLANNING.md](PLANNING.md), [ROADMAP.md](ROADMAP.md). This file is updated every project week; each past version stays reachable (§5).

**Product aimed**: a **local** assistant that prepares the update of an existing S1000D manual like a technical writer would. It reads the update directives (or an up-to-date version of the manual), finds every impacted zone, proposes traced changes, and lets the writer **verify, sort and review** them git-style (accept / edit / refuse / on hold + comment for the customer), before producing valid, traced S1000D data modules. Principle: *the AI proposes, the code applies, the checks verify, the writer decides.* Approach: hybrid (code searches, compares and applies; the LLM only understands a request and drafts new text).

**This week's deliverable (week 4, mid-term of 13/11): a PoC shown as 4 screens**: the 5-step journey, *Verify*, *Sort*, *Review*, on a fictitious scenario (bulletin `BM-042`, brake pads of a bike). It covers the **request mode** (a directive in, changes out). **There is no executable prototype.** Not covered by the PoC: the **comparison mode** (two files, old and up-to-date), the test with a real local model, the real data sets. Nothing is executable yet: the code starts at sprint 5.

**Client / evaluator**: the client contact (business analyst, LGM). **Test data**: public S1000D Bike data set and fictitious examples only, no client data.

---

## 1. Requirements (Q1)

### Project objectives (targets, provisional thresholds)

They describe the expected quality: **completeness, integrity, homogeneity**. Each one becomes a requirement (REQ-x) as soon as the product allows it to be measured. Thresholds are fixed **before** seeing the results, then submitted to the evaluator.

| ID | Objective | Indicator & provisional threshold | Becomes a requirement | Requirement |
|---|---|---|---|---|
| OBJ-1 | **Exhaustivité** : aucune modification nécessaire oubliée | 100 % des modifications attendues faites, 0 hors liste | Scénario `LRU1010`, puis scénarios variés | REQ-5 |
| OBJ-2 | **Intégrité** : rien d'autre ne change, le manuel reste conforme | 0 différence hors changements acceptés ; 100 % des DM valides XSD ; 100 % conformes au BREX par défaut | XSD, puis BREX | REQ-6, REQ-11 |
| OBJ-3 | **Véracité** : rien n'est inventé | 0 valeur (référence, quantité, couple, outil) absente du contexte de la modification ou de l'ancien manuel | Premier texte rédigé par le LLM | à créer |
| OBJ-4 | **Traçabilité S1000D** | 100 % des DM modifiés : `issueInfo` mis à jour selon la politique de versioning, `changeMark` / `changeType` sur les éléments modifiés, `reasonForUpdate` | Scénario `LRU1010` | REQ-10 |
| OBJ-5 | **Le rédacteur garde la main** (revue type git) | L'évaluateur déroule un scénario seul : accepter / refuser / en attente + commentaire ; 0 changement appliqué sans décision | Revue avant / après | REQ-7 |
| OBJ-6 | **Compréhension de la demande** | ≥ 90 % des demandes en langage naturel traduites en opérations correctes, sur ≥ 20 demandes | IA locale | à créer |
| OBJ-7 | **Homogénéité du style** | ≥ 80 % des passages rédigés par l'outil jugés « dans le style du manuel » par l'évaluateur et les rédacteurs, notés à l'aveugle | Rédaction par le LLM | à créer |
| OBJ-8 | **Gain de temps** | Temps avec l'outil (revue comprise) ≤ 50 % du temps d'une reprise manuelle sur le même scénario (temps de référence mesuré par un rédacteur) | Évaluation finale | à créer |
| OBJ-9 | **Confidentialité** : fonctionne avec une IA locale | REQ-5 et REQ-6 passent avec un modèle local (Ollama), sans aucun appel réseau sortant | Architecture, puis test réel | REQ-8 |
| OBJ-10 | **Performance** | Propagation de 20 modifications sur le manuel complet en < 10 s (sans LLM) ; une demande traitée en < 2 min avec le LLM local, sur un portable standard | Sans LLM, puis avec LLM | à créer |
| OBJ-11 | **Généralisation** | OBJ-1, OBJ-2 et OBJ-4 tenus sur des scénarios non vus par l'équipe de développement | Évaluation finale | à créer |
| OBJ-12 | **Maintenabilité** | Installation + exécution en ≤ 3 commandes ; schéma d'architecture dans le README | README, puis architecture | REQ-9 |
| OBJ-13 | **Utilité** | Note ≥ 3/5 donnée par l'évaluateur et par les rédacteurs | Évaluation finale | à créer |
| OBJ-14 | *(V2, si le temps le permet)* **Contradictions entre documents** | ≥ 90 % des contradictions repérées sur un jeu où elles ont été injectées ; l'option choisie par le rédacteur est appliquée sans reprise manuelle | Évaluation finale | à créer |
| OBJ-15 | **Mode comparaison : exhaustivité** | 100 % des différences de contenu entre l'ancienne version et la version à jour détectées et proposées (ajout, suppression, modification, déplacement), sur des paires dont les différences sont connues | Mode comparaison | à créer |
| OBJ-16 | **Mode comparaison : conservation** | 100 % des éléments propres à l'ancienne version conservés (identifiants, applicabilité, ajouts locaux) ; la version à jour n'est jamais recopiée par-dessus l'ancienne | Mode comparaison | à créer |
| OBJ-17 | **Mode comparaison : conflits** (fusion à 3 versions) | 100 % des modifications contradictoires (même élément modifié des deux côtés depuis la base commune) présentées comme conflits, 0 résolue automatiquement | Mode comparaison | à créer |
| OBJ-18 | **Applicabilité respectée** | 0 modification appliquée à une variante de produit non concernée, sur des scénarios ciblant une seule variante (87 % des DM du Bike ont des passages d'applicabilité) | Scénarios variés | à créer |
| OBJ-19 | **Illustrations signalées** | 100 % des illustrations (figures, légendes) liées à un élément modifié signalées au rédacteur comme « à vérifier » (l'outil ne modifie pas les images) | Revue avant / après | à créer |
| OBJ-20 | **Retour sur investissement chiffré** | Rapport de gain sur ≥ 3 scénarios : heures gagnées par reprise = temps manuel − temps avec l'outil (revue comprise), avec le détail du calcul | Évaluation finale | à créer |

#### Proposed objectives (provisional thresholds, to be validated)

| ID | Objective | Indicator & provisional threshold | Requirement |
|---|---|---|---|
| OBJ-21 | **Politique de versioning appliquée** | 100 % des DM modifiés portent `issueInfo` (`issueNumber` / `inWork`), un nom de fichier et une entrée de journal conformes à la politique choisie (`none`, `in_work`, `new_issue`) | à créer |
| OBJ-22 | **Erreurs préexistantes signalées comme telles** | 100 % des erreurs XSD / BREX déjà présentes avant traitement sont rapportées comme `pre_existing` et jamais imputées à l'outil ; 0 erreur `introduced` livrée | à créer |
| OBJ-23 | **Demande interdite par le BREX** | Une demande que le BREX interdit aboutit à `blocked_by_rule` en ≤ 3 essais, avec la règle citée, sans boucle | à créer |

### Requirements: week 4, PoC (current deliverable)

The PoC shows **what the tool will do and how the writer will use it**, on a fictitious scenario. It is judged on understanding, usefulness and fit with the client's need, not on computation.

| ID | Requirement | Characteristic | Metric & threshold | Why it matters (client need) | Validated by client? |
|---|---|---|---|---|---|
| REQ-12 | **Le parcours est compris sans explication** | Usability | L'évaluateur et ≥ 2 rédacteurs, devant les 4 écrans, retrouvent seuls ce que fait l'outil et ce que décide le rédacteur à chacune des 5 étapes ; ≥ 4 étapes sur 5 correctement reformulées | Un outil que le rédacteur ne comprend pas ne sera pas utilisé | Non |
| REQ-13 | **Le PoC répond au problème de départ** | Functional suitability | Pour chacun des 3 problèmes cités par les rédacteurs (oubli d'une zone, référence ou numéro de pièce erroné, reprise très longue), l'évaluateur dit si le PoC y répond (oui / en partie / non) ; ≥ 2 « oui » sur 3 ; note d'utilité ≥ 3/5 | Valeur pour le client (U1, U2) | Non |
| REQ-14 | **Les 3 points de contrôle donnent la main au rédacteur** | Usability | Sur les écrans, 100 % des décisions (valider ou corriger une modification, garder ou écarter une zone, accepter, modifier ou refuser une proposition) sont humaines ; chaque zone et chaque proposition indique sa directive d'origine et sa raison | Demande explicite de LGM : un fonctionnement « comme git » | Non |
| REQ-15 | **Le scénario `BM-042` est cohérent d'un écran à l'autre** | Functional suitability | 0 incohérence entre les 4 écrans (mêmes pièces, mêmes références, chiffres qui se recoupent), relu par 2 membres de l'équipe qui n'ont pas dessiné les écrans | Un PoC contradictoire ne convainc pas | Non |
| REQ-16 | **Le PoC est présentable sans donnée client** | Security & confidentiality | 0 donnée réelle sur les écrans et dans la présentation ; chaque écran porte la mention « exemple fictif » ; le fonctionnement local est dit explicitement | Règle de LGM : aucune donnée client en dehors de leur système | Non |
| REQ-17 | **Le PoC suit le workflow en 3 phases de l'équipe** | Functional suitability | Chaque étape des 4 écrans (Déposer, Vérifier, Trier, Relire, Livrer) correspond à une phase des 3 schémas, et chaque boucle de rejet des schémas (rejet commenté, faux positif, oubli signalé, fiche erronée, édition, rejet) a son bouton ou sa décision sur un écran | Montrer au jury que la maquette et l'architecture racontent la même chose | Non |

### Requirements: earlier weeks (kept)

| ID | Requirement | Characteristic | Metric & threshold | Why it matters (client need) | Validated by client? |
|---|---|---|---|---|---|
| REQ-1 | L'état de l'art couvre les 4 pistes d'automatisation identifiées | Functional suitability | ≥ 1 approche / outil documenté (avec source) pour chacune des 4 pistes : (a) conversion Word / XML, (b) compilation des données d'entrée, (c) harmonisation de la rédaction, (d) multilingue | Choisir où automatiser en connaissant les options | Oui 09/10, le client |
| REQ-2 | La restitution permet de dégager des orientations de projet concrètes | Usability | ≥ 2 pistes retenues à la fin de la restitution | Le sujet est vaste : il faut réduire le périmètre | Oui 09/10, le client |
| REQ-3 | Aucune donnée privée dans le dépôt | Security & confidentiality | 0 fichier de données privées versionné (`git ls-files` + `.gitignore` + tests `tests/security/`) ; uniquement des données S1000D publiques | Les documents techniques réels sont confidentiels | Oui 26/10, le client |
| REQ-4 | L'orientation et les approches techniques sont écrites et validées | Functional suitability | Note d'orientation (besoin, périmètre, hors périmètre, objectifs, ≥ 2 approches comparées, questions ouvertes) validée par l'évaluateur | Viser le bon besoin | Non |

### Requirements: next sprints (verified from sprint 5)

| ID | Requirement | Characteristic | Metric & threshold | Why it matters (client need) | Validated by client? |
|---|---|---|---|---|---|
| REQ-5 | **Exhaustivité** : aucune modification nécessaire n'est oubliée | Functional suitability | Scénario `LRU1010` → `LRU2020` (contexte + liste des modifications attendues écrits **avant** d'exécuter l'outil) : 100 % des modifications attendues faites (2/2), 0 hors liste, et les 2 traces historiques laissées intactes | Les oublis sont l'erreur la plus fréquente de la reprise manuelle ; à l'inverse, réécrire l'historique fausserait le manuel | Non |
| REQ-6 | **Intégrité** : seul ce qui est demandé change, et le manuel reste conforme | Functional suitability | 0 différence hors modifications attendues (diff XML canonique ancien / nouveau) ; 100 % des DM produits valides selon les XSD S1000D | Une modification ne doit rien casser ailleurs | Non |
| REQ-7 | Le rédacteur garde la main : il voit l'avant / après et décide | Usability | L'évaluateur réalise le scénario seul (accepter / refuser / en attente + commentaire) ; note d'utilité ≥ 3/5 ; 0 changement appliqué sans décision | Un fonctionnement « comme git » est attendu | Non |
| REQ-8 | Les appels à l'IA sont isolés et remplaçables par un modèle local | Security & confidentiality | 100 % des appels à l'IA dans un seul module (`src/redactech/llm/`) ; changer de modèle = 1 changement de configuration | Aucune donnée documentaire ne doit aller dans un LLM hébergé | Oui 26/10, le client (constraint stated in the meeting; exact threshold to confirm) |
| REQ-9 | L'outil se lance sans l'équipe | Maintainability | Installation + exécution en ≤ 3 commandes en suivant le README, testé par un membre qui n'a pas écrit le code | Les briques doivent pouvoir être reprises | Non |
| REQ-10 | **Traçabilité S1000D** du nouveau manuel | Compatibility / portability | 100 % des DM modifiés : `issueInfo` selon la politique de versioning, `changeMark="1"` + `changeType` sur chaque élément modifié, `reasonForUpdate` reprenant le contexte | Le DM doit se rouvrir dans un éditeur XML et se relire comme une reprise faite à la main | Non |
| REQ-11 | Le nouveau manuel respecte le BREX | Compatibility / portability | 100 % des DM produits sans violation du BREX (chaîne du DM, jusqu'au BREX par défaut S1000D) | Contrôle avant livraison | Non |
| REQ-18 | **Les 4 canaux de recherche retrouvent toutes les zones concernées** | Functional suitability | Sur le scénario `LRU1010` : rappel mesuré par canal (Mention, Structure, Métadonnées, Sens) puis après fusion et reranker ; seuil provisoire : 100 % des zones attendues dans la liste fusionnée, 0 zone attendue perdue au reranker | Un oubli de zone est le premier problème cité par les rédacteurs | Non |
| REQ-19 | **Toute valeur de la fiche de modification vient de la directive** | Functional suitability | 0 valeur (référence, quantité, outil, numéro de série) de la fiche absente du texte de la directive ; contrôle fait par du code avant l'affichage au rédacteur | Éviter qu'une valeur inventée par le LLM soit validée par habitude | Non |

> **REQ-8**: the constraint (« no hosted AI, local target ») is stated by the client; the exact threshold remains to be confirmed.

> **Scenario `LRU1010` (REQ-5)**: `LRU1010` appears 4 times in 3 files of the public Bike data set. 2 occurrences must be modified: the part declaration in the common repository `comrep`, and the reference in the `IPD`. The 2 others are historical traces in the `UPF` file, to be left intact (« UPF rule to be confirmed »).

> **Scenario `BM-042` (PoC)**: fictitious bulletin (brake pads `BR-PAD-01` replaced by `BR-PAD-02`, tool `T-4` replaced by `T-5`, new running-in step of 10 progressive brakings, models concerned from a serial number). The 4 screens follow it from the bulletin to the before / after review.

## 2. Verification (Q2 → Q3)

### Week 4, PoC

| ID | Verification method | Pass criterion | When (automatic / each sprint / before demo) | Owner | Result | Evidence |
|---|---|---|---|---|---|---|
| REQ-12 | Test utilisateur sur les 4 écrans : on montre le parcours (écran 1) sans explication, puis on demande à chaque personne de dire ce que fait l'outil et ce que décide le rédacteur à chaque étape | ≥ 4 étapes sur 5 correctement reformulées par l'évaluateur et par ≥ 2 rédacteurs | Session de remise (HO2, HO3) ou avant la présentation du 13/11 | à compléter | Not run | à compléter notes du test (qui, date, résultat) |
| REQ-13 | Entretien avec l'évaluateur après le déroulé du scénario `BM-042` sur les écrans : question posée pour chacun des 3 problèmes, puis note d'utilité | ≥ 2 « oui » sur 3 ; note ≥ 3/5 | Présentation du 13/11, ou retour de l'évaluateur la semaine suivante | à compléter | Not run | à compléter compte rendu |
| REQ-14 | Relecture des 4 écrans par rapport à une liste : chaque décision est-elle humaine ? chaque zone et chaque proposition cite-t-elle directive et raison ? | 0 décision automatique ; 0 zone ou proposition sans origine | Avant la présentation, puis après chaque modification des écrans | à compléter | Pass | Relu le 12/11 sur les 4 images : points de contrôle 1, 2 et 3 présents (« Valider cette modification », « Garder / Écarter », « Accepter / Modifier / Refuser ») ; chaque zone du tri porte sa raison ; chaque proposition de la relecture porte « Directive d'origine » et « Pourquoi » ; « Accepter les 6 en une fois » reste une décision du rédacteur |
| REQ-15 | Relecture croisée des 4 écrans par 2 membres de l'équipe qui n'ont pas dessiné les écrans | 0 incohérence relevée | Avant la présentation | à compléter | Partial | Relu le 12/11 : les chiffres du tri se recoupent (23 zones = 11 certaines + 8 probables + 4 à vérifier ; 9 triées + 14 à trier = 23) ; mêmes pièces et références sur les écrans 2, 3 et 4 (BR-PAD-01 → BR-PAD-02, clé T-4 → T-5, rodage de 10 freinages). **Points à lever** : « 14 zones restent à trier » (écran 3) et « 14 propositions » (écran 4) sont deux comptes différents qui portent le même nombre ; l'écran 3 montre une seule modification (n° 2) alors que l'écran 4 parle de « 14 propositions » et de la directive « § 1 à 3 » ; relecture croisée par 2 membres encore à faire |
| REQ-16 | Relecture de la présentation et des écrans par un membre de l'équipe, avec la règle de confidentialité sous les yeux | 0 donnée réelle ; mention « exemple fictif » sur chaque écran | Avant la présentation | à compléter | Partial | Relu le 12/11 : les 3 écrans d'interface portent « Exemple fictif » (projet « Vélo – manuel de maintenance », bulletin `BM-042` fictif, références `BR-PAD-xx`) ; l'écran 1 (parcours) porte « Document de travail » et dit que l'ensemble fonctionne en local ; reste à relire la présentation |
| REQ-17 | Tableau de correspondance écrans / phases / boucles, relu par un membre qui n'a pas dessiné les schémas | 0 étape ou boucle sans équivalent | Avant la présentation | à compléter | Not run | Correspondance écrite le 12/11 ; relecture à faire |

### Earlier weeks

| ID | Verification method | Pass criterion | When (automatic / each sprint / before demo) | Owner | Result | Evidence |
|---|---|---|---|---|---|---|
| REQ-1 | Checklist : tableau pistes × approches dans le document d'état de l'art | Chacune des 4 pistes a ≥ 1 approche sourcée | Avant la restitution | à compléter | Pass | à compléter lien vers le document |
| REQ-2 | Revue à la restitution orale | ≥ 2 orientations notées dans le compte rendu | Démo | à compléter | Pass | à compléter lien vers le compte rendu |
| REQ-3 | Audit : `git ls-files` + vérification du `.gitignore` + `py tools/privacy.py scan --tracked` | 0 fichier de données privées | Chaque étape + CI | à compléter | Pass | `git ls-files` = code et docs seulement ; `.gitignore` en place ; tests `tests/security/` (2 fichiers) ; hooks `pre-commit`, `commit-msg` et `pre-push` installés ; `py -3 tools/privacy.py scan --tracked` : exit 0 sur le poste de développement, le 2026-11-10 |
| REQ-4 | Revue de la note d'orientation | Validation écrite | Avant le développement | à compléter | Not run |  |

### Next sprints: requirements and objectives (not run yet)

| ID | Verification method | Pass criterion | When (automatic / each sprint / before demo) | Owner | Result | Evidence |
|---|---|---|---|---|---|---|
| REQ-5 | Test automatique (pytest) : modifications faites comparées au fichier `tests/scenarios/lru1010/attendu.yaml`, écrit avant le code (2 modifications attendues + 2 occurrences à ne pas toucher) | 2/2 modifications faites, 0 hors liste, 2/2 traces historiques identiques à l'original | À chaque commit (CI) + en direct à la démo | à compléter | Not run |  |
| REQ-6 | Test automatique : diff XML canonique ancien / nouveau limité aux éléments attendus + validation XSD de chaque DM produit | 0 différence hors liste ; 100 % valides | À chaque commit (CI) + en direct à la démo | à compléter | Not run |  |
| REQ-7 | Test utilisateur : l'évaluateur déroule le scénario seul, puis note l'utilité ; tests d'interface automatiques | Scénario terminé sans aide ; note ≥ 3/5 ; journal des décisions complet | Démo | à compléter | Not run |  |
| REQ-8 | Revue de code (recherche de tous les appels à l'IA) + test : le même scénario tourne avec le modèle changé dans la configuration | Tous les appels dans `src/redactech/llm/` ; changer de modèle = 1 ligne de configuration | Chaque étape | à compléter | Not run |  |
| REQ-9 | Test interne : un membre qui n'a pas écrit le code suit le README sur une machine propre | ≤ 3 commandes, sans aide | Avant la démo | à compléter | Not run |  |
| REQ-10 | Test automatique : relecture de chaque DM modifié (`issueInfo`, `@changeMark`, `@changeType`, `reasonForUpdate`) | 100 % des DM modifiés conformes | À chaque commit (CI) | à compléter | Not run |  |
| REQ-11 | Test automatique : contrôle des DM produits contre la chaîne BREX (validateur BREX externe ou vérificateur XPath interne) | 0 violation introduite | À chaque commit (CI) | à compléter | Not run |  |
| OBJ-21 | Test automatique : 3 politiques de versioning, renommage de fichier, journal | 100 % conformes | À chaque commit (CI) | à compléter | Not run |  |
| OBJ-22 | Test automatique : DM déjà fautif en entrée | Erreurs classées `pre_existing`, 0 `introduced` | À chaque commit (CI) | à compléter | Not run |  |
| OBJ-23 | Test automatique : scénario de demande interdite | `blocked_by_rule` en ≤ 3 essais, sans boucle | À chaque commit (CI) | à compléter | Not run |  |
| OBJ-1 | Scénario `LRU1010`, puis scénarios variés | 100 % des modifications attendues faites, 0 hors liste | À chaque commit (CI) | à compléter | Not run |  |
| OBJ-10 | Sans LLM, puis avec LLM | Propagation de 20 modifications sur le manuel complet en < 10 s (sans LLM) ; une demande traitée en < 2 min avec le LLM local, sur un portable standard | À chaque commit (CI) | à compléter | Not run |  |
| OBJ-19 | Revue avant / après | 100 % des illustrations (figures, légendes) liées à un élément modifié signalées au rédacteur comme « à vérifier » (l'outil ne modifie pas les images) | À chaque commit (CI) | à compléter | Not run |  |
| REQ-18 | Scénario `LRU1010` : zones attendues écrites avant l'exécution ; rappel mesuré par canal puis après fusion | 100 % des zones attendues, 0 perdue au reranker | Chaque sprint à partir du sprint 5 | à compléter | Not run | |
| REQ-19 | Test automatique : chaque valeur de la fiche est recherchée dans le texte de la directive ; cas piège avec une valeur inventée | 0 valeur non retrouvée affichée ; le cas piège est rejeté | À chaque commit (CI), à partir du sprint 5 | à compléter | Not run | |

> Status: Not run = not run yet · Pass · Partial · Fail (say what you'll do about it in §3)

> The rows REQ-5 to REQ-11 and OBJ-1, 10, 19, 21, 22, 23 will be run from sprint 5: nothing is presented as passed before.

## 3. Log (one entry per project week)

### Week of 14/09 — scoping
- Added : pas encore d'exigences qualité.
- Checked : liste des questions de cadrage établie. Le périmètre est limité à la norme publique S1000D (Bike data set, BREX par défaut).
- Shown to client: scoping questions (workshop and Friday meeting). LGM points the project to the public S1000D standard (Bike data set, default BREX).
- Next : état de l'art des 4 pistes.

### Week of 05/10 — state of the art
- Added : REQ-1 à REQ-3 (état de l'art, orientations, confidentialité).
- Checked : REQ-1 Pass, REQ-2 Pass. En complément, deux essais de recherche (conversion Word → XML et contrôle multilingue) ont été évalués sur le Bike ; ils sont mis en suspens après l'orientation.
- Shown to client: state of the art of the 4 tracks, presented orally (09/10); REQ-1 and REQ-2 validated by the client.
- Next : acter l'orientation.

### Week of 26/10 — orientation
- Added : orientation « reprise et modification de manuels existants » ; objectifs OBJ-1 à OBJ-14 ; REQ-4, 5, 6, 8, 9, 10 ; REQ-7 et REQ-11 planifiées ensuite ; approche hybride retenue.
- Added : **mode « comparaison »** (mettre à jour l'ancienne version à partir d'une version à jour fournie à part) et objectifs OBJ-15 à OBJ-20. Le scénario `LRU1010` est précisé : 2 occurrences à modifier, 2 traces historiques à laisser intactes.
- Added : objectifs proposés OBJ-21 à OBJ-23 (versioning, erreurs préexistantes, demandes interdites par le BREX).
- Checked : REQ-3 Pass (audit du dépôt, tests de confidentialité). Autres résultats : à remplir quand les vérifications sont exécutées.
- Shown to client: meeting of 26/10 with the client and 3 writers (process in 3 steps, pain points, scope « modify an existing XML on order », local-AI constraint); REQ-3 and REQ-8 validated. à compléter Orientation note (REQ-4) not yet validated in writing.
- Next : faire valider la note d'orientation et les seuils des OBJ ; revue avant / après, BREX, signalement des illustrations.

### Week of 09/11 — PoC on mock-ups (mid-term, 13/11)
- Added: decision to deliver **a PoC shown as 4 screens**, not an executable prototype. The screens show the 5-step journey (Deposit, Verify, Sort, Review, Deliver) and the 3 checkpoints, on the fictitious scenario `BM-042` (brake pads, tool `T-4` replaced by `T-5`, new running-in step, models from a serial number). New requirements REQ-12 to REQ-16 (journey understood, answers the starting problem, writer keeps control, coherent scenario, no client data) and their verification (§2). This file was rebuilt on the school template; all earlier IDs and entries are kept (§5).
- Checked (reading of the 4 images, 12/11): REQ-14 Pass; REQ-15 Partial (figures consistent, two points to fix: « 14 zones left to sort » vs « 14 proposals » carry the same number for two different counts; screen 3 shows a single change while screen 4 mentions 14 proposals and the directive « §1 to 3 »); REQ-16 Partial (« Exemple fictif » on the 3 interface screens, « Document de travail » on the journey screen; the presentation remains to be read).
- Not checked: **no user test has taken place yet** (REQ-12, REQ-13). à compléter Feedback of the handover session of 9/11 to be added here. REQ-5 to REQ-11 are not run yet (sprint 5).
- Shown to client: PoC (4 screens) at the mid-term presentation on 13/11. à compléter Add the feedback received.
- 12/11 (reading of the 3 workflow diagrams): REQ-17 to REQ-19 added (workflow in 3 phases, recall of the 4 search channels, truthfulness of the modification sheet). Other points to explain or fix: numbering 4.3/4.4 differs between screens 3 and 4; « 3 changes » announced for « Frein avant – Pose » but 4 shown; « 3 directives » for one bulletin of 3 pages; the diagrams and screens use different words (« fiche » / « rapport d'impact » vs « ce que l'outil a compris » / « zones concernées »).
- Next: user test with the evaluator and ≥ 2 writers (REQ-12, REQ-13); fix the two points of REQ-15 and have the screens read by 2 team members who did not draw them; read the presentation against the confidentiality rule (REQ-16); then fill the à compléter cells.

## 4. Data & confidentiality rules

- Data that must **never** be committed (paths, file types): any private or real-use data; downloaded archives (`*.zip`) and the `data/` folder (can be downloaded again from the public S1000D site); generated outputs (`output/`, `*.docx`, `*.pdf`); recordings (`*.mp4`); secrets (`.env`, API keys).
- Where the data actually lives (who has access): on each member's machine, downloaded from the public S1000D site. Only public data (S1000D Bike data set Issue 4.1 for development; Issue 4.2 for compatibility with the 4.2 XSDs and as « old / up-to-date » pairs for the comparison mode; default BREX) and fictitious examples (`BM-042`, `BR-PAD-xx`). No real documentation, no past project, no internal BREX enters the project.
- Tools/services **not** allowed by the client: in the end, no client data may go into a hosted AI, whichever it is, including LGM's own hosted AI: the solution must work with a local AI, or without AI (REQ-8, OBJ-9). During the project any tool may be used, but only on public or fictitious data. Confirmed by LGM on 26/10.
- Personal data involved (GDPR) and how it is handled: none in the data (documentation of a fictitious bike). Any recordings are not committed.
- Matching `.gitignore` entries are in place: Oui (see `.gitignore`, `CLAUDE.md` §3 and `docs/PRIVACY.md`).

## 5. Traceability with previous versions

### Previous versions of this file

| Version | Where | What it contained |
|---|---|---|
| School template | `a2e9e5ab-QUALITY.md` (empty grid) | Structure and terms reused here |
| 30/10, PR #1 | [Pull request #1](https://github.com/CrispyChicken2/Redac-Tech/pull/1) | REQ-1 to REQ-11, OBJ-1 to OBJ-20 |
| 09/11, `main` | [QUALITY.md at commit 9f3c3ae](https://github.com/CrispyChicken2/redac-tech/blob/9f3c3ae/QUALITY.md) | « Update QUALITY.md » |
| 10/11 | [QUALITY.md at commit fd06a3c](https://github.com/CrispyChicken2/redac-tech/blob/fd06a3c/QUALITY.md) | Adds OBJ-21 to OBJ-23 and milestones M1 to M3 |
| 12/11, working copy | not committed | Adds the PoC block and REQ-12 to REQ-16 on top of the 10/11 version |

### What changed in this version (13/11)

- **Kept without change**: all IDs REQ-1 to REQ-11 and OBJ-1 to OBJ-23, their metrics, thresholds and results; all earlier log entries (now under « Week of … » titles and the template's *Added / Checked / Shown to client / Next* lines); the data rules.
- **Added**: the PoC block at the top, REQ-12 to REQ-19 and their verification, the `BM-042` scenario note, the entry « Week of 09/11 », this §5.
- **Re-scoped**: REQ-5 to REQ-11 and the objectives checked by code are now labelled *next sprints (verified from sprint 5)*; none is presented as passed (results Not run, evidence emptied).
- **Renamed (terms of the school template)**: sections and column names in English; characteristics (*Functional suitability, Usability, Security & confidentiality, Maintainability, Compatibility / portability*); `Validated by client?` now carries the date and who (REQ-1 and REQ-2: 09/10, le client; REQ-3 and REQ-8: 26/10, le client); « Étape n » entries became « Week of DD/MM ».
- **Still to fill** (à compléter): the `Owner` column, the evidence of REQ-1 and REQ-2 (links), the feedback of the handover session of 9/11, the results of REQ-12, REQ-13, REQ-15 and REQ-16.
