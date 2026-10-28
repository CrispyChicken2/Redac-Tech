# Quality requirements & test policy

| Grid | What it asks | Where it lives in this file |
|---|---|---|
| **Q1** | You questioned and specified the quality requirements of your product | §1 Requirements |
| **Q2** | You defined how you'll know each requirement is met | §2 Verification |
| **Q3** | You actually ran those checks | §2 *Result* and *Evidence* columns + §3 Log |

Planning des sprints et engagements hebdomadaires : [PLANNING.md](PLANNING.md). Besoin, périmètre et choix de l'approche : [docs/ORIENTATION.md](docs/ORIENTATION.md).

**Produit visé** : l'outil prépare les reprises d'un manuel S1000D comme un rédacteur, selon **deux modes d'entrée** :
- **Mode « demande »** : l'ancien manuel + le contexte de la modification (phrase, bulletin, liste de correspondances), par exemple « la pièce X2 est remplacée par X3 ».
- **Mode « comparaison »** : l'ancien manuel + **une version à jour fournie à part** (deux fichiers distincts). L'outil détecte les différences et les reporte dans l'ancienne version, sans l'écraser : identifiants, applicabilité et ajouts propres à l'entreprise client sont conservés. Si l'ancienne version a aussi évolué de son côté, les modifications contradictoires apparaissent comme des conflits à arbitrer, comme dans git.

Dans les deux modes, le rédacteur contrôle chaque changement dans une revue avant / après « type git » (accepter, refuser, en attente + commentaire client), puis l'outil produit le nouveau manuel, conforme S1000D et tracé. Approche retenue : **hybride**. Le code fait la recherche, la comparaison et l'application des modifications ; le LLM sert seulement à comprendre une demande et à rédiger du texte nouveau.

---

## 1. Requirements (Q1)

### Objectifs du projet (cibles, seuils provisoires)

Ils viennent du workshop et des réunions avec l'entreprise client (définition de la qualité : **exhaustivité, intégrité, homogénéité**). Chacun devient une exigence REQ-x au sprint où le POC permet de le mesurer. Les seuils sont fixés **avant** de voir les résultats, puis soumis au client (évaluateur du MVP).

| ID | Objectif | Indicateur & seuil provisoire | Devient exigence au sprint | Exigence |
|---|---|---|---|---|
| OBJ-1 | **Exhaustivité** : aucune modification nécessaire oubliée | 100 % des modifications attendues faites, 0 hors liste | 3 (scénario `LRU1010`), puis 5 (scénarios variés) | REQ-5 |
| OBJ-2 | **Intégrité** : rien d'autre ne change, le manuel reste conforme | 0 différence hors changements acceptés ; 100 % des DM valides XSD ; 100 % conformes au BREX par défaut | 3 (XSD), 4 (BREX) | REQ-6, REQ-11 |
| OBJ-3 | **Véracité** : rien n'est inventé | 0 valeur (référence, quantité, couple, outil) absente du contexte de la modification ou de l'ancien manuel | 5 (premier texte rédigé par le LLM) | à créer |
| OBJ-4 | **Traçabilité S1000D** | 100 % des DM modifiés : `inWork` incrémenté, `changeMark` / `changeType` sur les éléments modifiés, `reasonForUpdate` | 3 | REQ-10 |
| OBJ-5 | **Le rédacteur garde la main** (revue type git) | Le client déroule un scénario seul : accepter / refuser / en attente + commentaire ; 0 changement appliqué sans décision | 4 | REQ-7 |
| OBJ-6 | **Compréhension de la demande** | ≥ 90 % des demandes en langage naturel traduites en opérations correctes, sur ≥ 20 demandes | 5 | à créer |
| OBJ-7 | **Homogénéité du style** | ≥ 80 % des passages rédigés par l'outil jugés « dans le style du manuel » par le client, notés à l'aveugle | 6 | à créer |
| OBJ-8 | **Gain de temps** | Temps avec l'outil (revue comprise) ≤ 50 % du temps d'une reprise manuelle sur le même scénario (temps de référence mesuré par un rédacteur) | 6 | à créer |
| OBJ-9 | **Confidentialité** : fonctionne avec une IA locale | REQ-5 et REQ-6 passent avec un modèle local (Ollama), sans aucun appel réseau sortant | 3 (architecture), 5 (test réel) | REQ-8 |
| OBJ-10 | **Performance** | Propagation de 20 modifications sur le manuel complet en < 10 s (sans LLM) ; une demande traitée en < 2 min avec le LLM local, sur un portable étudiant | 4 (sans LLM), 5 (avec LLM) | à créer |
| OBJ-11 | **Généralisation** | OBJ-1, OBJ-2 et OBJ-4 tenus sur des scénarios écrits par l'entreprise client, non vus par l'équipe | 7 | à créer |
| OBJ-12 | **Maintenabilité** | Installation + exécution en ≤ 3 commandes ; schéma d'architecture dans le README | 3 (README), 4 (architecture) | REQ-9 |
| OBJ-13 | **Utilité** | Note ≥ 3/5 donnée par Leny et par les rédacteurs | 7 | à créer |
| OBJ-14 | *(V2, si le temps le permet)* **Contradictions entre documents** | ≥ 90 % des contradictions repérées sur un jeu où elles ont été injectées ; l'option choisie par le client est appliquée sans reprise manuelle | 7 | à créer |
| OBJ-15 | **Mode comparaison : exhaustivité** | 100 % des différences de contenu entre l'ancienne version et la version à jour détectées et proposées (ajout, suppression, modification, déplacement), sur des paires dont les différences sont connues | 5 | à créer |
| OBJ-16 | **Mode comparaison : conservation** | 100 % des éléments propres à l'ancienne version conservés (identifiants, applicabilité, ajouts LGM) ; la version à jour n'est jamais recopiée par-dessus l'ancienne | 5 | à créer |
| OBJ-17 | **Mode comparaison : conflits** (fusion à 3 versions) | 100 % des modifications contradictoires (même élément modifié des deux côtés depuis la base commune) présentées comme conflits, 0 résolue automatiquement | 6 | à créer |
| OBJ-18 | **Applicabilité respectée** | 0 modification appliquée à une variante de produit non concernée, sur des scénarios ciblant une seule variante (87 % des DM du Bike ont des passages d'applicabilité) | 5 | à créer |
| OBJ-19 | **Illustrations signalées** | 100 % des illustrations (figures, légendes) liées à un élément modifié signalées au rédacteur comme « à vérifier » (l'outil ne modifie pas les images) | 4 | à créer |
| OBJ-20 | **Retour sur investissement chiffré** (objectif O5 du projet) | Rapport de gain sur ≥ 3 scénarios : heures gagnées par reprise = temps manuel − temps avec l'outil (revue comprise), avec le détail du calcul | 6 | à créer |

### Sprint 2 (semaine du 05/10) : livrable « état de l'art »

| ID | Requirement | Characteristic | Metric & threshold | Why it matters (client need) | Validated by client? |
|---|---|---|---|---|---|
| REQ-1 | L'état de l'art couvre les 4 pistes d'automatisation identifiées avec LGM au sprint 1 | Functional suitability | ≥ 1 approche / outil documenté (avec source) pour chacune des 4 pistes : (a) conversion Word ↔ XML, (b) compilation des données d'entrée, (c) harmonisation de la rédaction, (d) multilingue | LGM doit pouvoir choisir où automatiser en connaissant les options | ☑ 09/10, Leny |
| REQ-2 | La restitution permet de dégager des orientations de projet concrètes | Usability | ≥ 2 pistes retenues avec le client à la fin de la restitution | Le sujet est vaste : il faut réduire le périmètre | ☑ 09/10, Leny (retenues : (b) + ✏️) |
| REQ-3 | Aucune donnée client dans le dépôt | Security & confidentiality | 0 fichier de données client versionné (`git ls-files` + `.gitignore`) | Documents techniques LGM confidentiels | ☑ 26/10, Leny (uniquement S1000D public) |

### Sprint 3 (semaine du 26/10) : orientation + premier POC « propagation d'une modification »

Livrable : la note d'orientation, puis un premier POC **sans IA** (approche A, socle de l'approche C) qui propage le remplacement d'une pièce dans tout le manuel Bike 4.1 et écrit le nouveau manuel tracé. Scénario de test : la pièce `LRU1010` est remplacée par `LRU2020`. Elle apparaît 4 fois dans 3 fichiers : **2 occurrences à modifier** (déclaration de la pièce dans le dépôt commun `comrep`, référence dans la nomenclature illustrée `IPD`) et **2 traces historiques à laisser intactes** (fichier de mise à jour `UPF-…`, qui garde la trace de la suppression de la pièce). La règle pour l'`UPF` est à confirmer avec Leny.

| ID | Requirement | Characteristic | Metric & threshold | Why it matters (client need) | Validated by client? |
|---|---|---|---|---|---|
| REQ-4 | L'orientation et les approches techniques sont écrites et validées par le client | Functional suitability | Note d'orientation (besoin, périmètre, hors périmètre, objectifs, ≥ 2 approches comparées, questions ouvertes) validée par Leny avant le 30/10 | Viser le même besoin que LGM | ☐ |
| REQ-5 | **Exhaustivité** : aucune modification nécessaire n'est oubliée | Functional suitability | Scénario `LRU1010` (contexte + liste des modifications attendues écrits **avant** d'exécuter l'outil) : 100 % des modifications attendues faites (2/2), 0 hors liste, et les 2 traces historiques laissées intactes | Les oublis sont l'erreur la plus fréquente de la reprise manuelle ; à l'inverse, réécrire l'historique fausserait le manuel | ☐ |
| REQ-6 | **Intégrité** : seul ce qui est demandé change, et le manuel reste conforme | Functional suitability | 0 différence hors modifications attendues (diff XML canonique ancien / nouveau) ; 100 % des DM produits valides selon les XSD S1000D 4.1 | Une modification ne doit rien casser ailleurs | ☐ |
| REQ-8 | Les appels à l'IA sont isolés et remplaçables par un modèle local | Security & confidentiality | 100 % des appels à l'IA dans un seul module ; passer d'un LLM en ligne à un modèle local = 1 changement de configuration | Chez LGM, aucune donnée client dans un LLM externe | ☑ 26/10, Leny (contrainte énoncée en réunion) |
| REQ-9 | Le POC se lance sans nous | Maintainability | Installation + exécution en ≤ 3 commandes en suivant le README, testé par un membre qui n'a pas écrit le code | Démarche POC de LGM : briques reprises ensuite par leur équipe | ☐ |
| REQ-10 | **Traçabilité S1000D** du nouveau manuel | Compatibility | 100 % des DM modifiés : `inWork` incrémenté, `changeMark="1"` + `changeType` sur chaque élément modifié, `reasonForUpdate` reprenant le contexte | Le DM doit se rouvrir dans Arbortext et se relire comme une reprise faite à la main | ☐ |

> **REQ-8** : la contrainte (« pas d'IA hébergée, cible locale ») est validée par Leny ; le seuil exact reste à lui faire confirmer.
> **REQ-7** (revue avant / après) est déplacée au sprint 4 (voir ci-dessous), car le premier POC n'a pas encore d'interface.

### Sprint 4 (semaine du 09/11) : revue avant / après + conformité BREX *(prévu, à confirmer lundi 09/11)*

| ID | Requirement | Characteristic | Metric & threshold | Why it matters (client need) | Validated by client? |
|---|---|---|---|---|---|
| REQ-7 | Le rédacteur garde la main : il voit l'avant / après et décide | Usability | Leny réalise le scénario seul (accepter / refuser / en attente + commentaire) ; note d'utilité ≥ 3/5 ; 0 changement appliqué sans décision | Demande explicite de LGM : un fonctionnement « comme git » | ☐ |
| REQ-11 | Le nouveau manuel respecte le BREX par défaut | Compatibility | 100 % des DM produits sans violation du BREX par défaut S1000D 4.1 | Contrôle de LGM avant envoi au client | ☐ |

## 2. Verification (Q2 → Q3)

| ID | Verification method | Pass criterion | When (automatic / each sprint / before demo) | Owner | Result | Evidence |
|---|---|---|---|---|---|---|
| REQ-1 | Checklist : tableau pistes × approches dans le document d'état de l'art | Chacune des 4 pistes a ≥ 1 approche sourcée | Avant la restitution | ✏️ | ✅ | ✏️ lien vers le document d'état de l'art |
| REQ-2 | Revue avec le client à la restitution orale | ≥ 2 orientations notées dans le compte rendu | Démo du vendredi | ✏️ | ✅ | ✏️ lien vers le compte rendu du 09/10 |
| REQ-3 | Audit : `git ls-files` + vérification du `.gitignore` | 0 fichier de données client | Chaque sprint | ✏️ | ✅ | 26/10 : `git ls-files` = code et docs seulement ; `.gitignore` en place |
| REQ-4 | Revue de [docs/ORIENTATION.md](docs/ORIENTATION.md) par Leny | Validation écrite (Teams ou mail) | Avant le 30/10 | ✏️ | ⏳ | |
| REQ-5 | Test automatique (pytest) : modifications faites comparées au fichier `tests/scenarios/lru1010/attendu.yaml`, écrit avant le code (2 modifications attendues + 2 occurrences à ne pas toucher) | 2/2 modifications faites, 0 hors liste, 2/2 traces historiques identiques à l'original | À chaque commit (CI) + en direct à la démo | ✏️ | ⏳ | |
| REQ-6 | Test automatique : diff XML canonique ancien / nouveau limité aux éléments attendus + validation XSD 4.1 de chaque DM produit | 0 différence hors liste ; 100 % valides | À chaque commit (CI) + en direct à la démo | ✏️ | ⏳ | |
| REQ-8 | Revue de code (recherche de tous les appels à l'IA) + test : le même scénario tourne avec le modèle changé dans la configuration | Tous les appels dans `llm.py` ; changer de modèle = 1 ligne de configuration | Chaque sprint | ✏️ | ⏳ | |
| REQ-9 | Test interne : un membre qui n'a pas écrit le code suit le README sur une machine propre | ≤ 3 commandes, sans aide | Avant la démo | ✏️ | ⏳ | |
| REQ-10 | Test automatique : relecture de chaque DM modifié (`issueInfo/@inWork`, `@changeMark`, `@changeType`, `reasonForUpdate`) | 100 % des DM modifiés conformes | À chaque commit (CI) | ✏️ | ⏳ | |
| REQ-7 | Test utilisateur : Leny déroule le scénario seul, puis note l'utilité | Scénario terminé sans aide ; note ≥ 3/5 ; journal des décisions complet | Démo du sprint 4 | ✏️ | ⏳ | |
| REQ-11 | Test automatique : contrôle des DM produits contre le BREX par défaut (s1kd-brexcheck ou vérificateur XPath maison) | 0 violation | À chaque commit (CI), à partir du sprint 4 | ✏️ | ⏳ | |

> Status: ⏳ not run yet · ✅ pass · ⚠️ partial · ❌ fail (say what you'll do about it in §3)

## 3. Log (one entry per project week)

### Semaine du 14/09 (sprint 1)
- Added: pas encore d'exigences qualité (semaine de cadrage).
- Checked: workshop du mardi (client présent en partie) ; liste des questions de cadrage montée pendant la semaine.
- Shown to client: nos questions de cadrage, à la réunion du vendredi (livrable du sprint, validé par l'encadrement). Le client nous oriente vers la norme publique S1000D 4.1 (Bike data set, BREX par défaut).
- Next: état de l'art des 4 pistes.

### Semaine du 05/10 (sprint 2)
- Added: REQ-1 à REQ-3 (état de l'art, orientations, confidentialité).
- Checked: REQ-1 ✅, REQ-2 ✅. En complément, deux prototypes de recherche (conversion Word → XML et contrôle multilingue) ont été évalués sur le Bike ; ils sont mis en suspens après l'orientation du 26/10.
- Shown to client: restitution orale de l'état de l'art. Retour client : ✏️ ; 2 pistes retenues ((b) + ✏️).
- Next: rendez-vous avec l'équipe rédaction le 26/10 pour acter l'orientation.

### Semaine du 26/10 (sprint 3)
- Added: orientation actée avec LGM (reprise et modification de manuels existants) ; objectifs du projet OBJ-1 à OBJ-14 ; REQ-4, 5, 6, 8, 9, 10 pour ce sprint ; REQ-7 et REQ-11 planifiées au sprint 4 ; approche hybride retenue ([docs/ORIENTATION.md](docs/ORIENTATION.md)).
- Réponse à la question ouverte sur les « conflits » : il s'agit des **contradictions entre documents du client**, tranchées avec lui en réunion (compte rendu du 26/10) ; elles sont reprises en V2 (OBJ-14).
- Added (27/10) : **mode « comparaison »** (mettre à jour l'ancienne version à partir d'une version à jour fournie à part) et objectifs OBJ-15 à OBJ-20 (exhaustivité et conservation de la comparaison, conflits à 3 versions, applicabilité, illustrations, retour sur investissement). Le scénario `LRU1010` est précisé : 2 occurrences à modifier, 2 traces historiques à laisser intactes.
- Checked: REQ-3 ✅ (audit du dépôt) ; REQ-8 validée par Leny sur le principe. Autres résultats : ✏️ à remplir avant vendredi.
- Shown to client: ✏️ à remplir vendredi 30/10.
- Next: faire valider la note d'orientation et les seuils des OBJ par Leny ; lui demander si une « version à jour » fournie par un client est en général un DM S1000D ou un Word / PDF ; sprint 4 = revue avant / après + BREX + signalement des illustrations.

## 4. Data & confidentiality rules

- Données de travail : uniquement des données **publiques**, la norme S1000D de l'ASD (Bike data set Issue 4.1 pour le développement ; Issue 4.2 pour vérifier la compatibilité avec les XSD 4.2 et comme paires « ancienne / à jour » du mode comparaison, les mêmes DM existant dans les deux éditions ; BREX par défaut). LGM ne nous fournit ni ses documentations, ni ses projets passés, ni ses BREX internes (secteur défense).
- Data that must **never** be committed : toute donnée LGM ; les archives téléchargées (`*.zip`) et le dossier `data/` (retéléchargeables depuis le site de l'ASD) ; les sorties générées (`output/`, `*.docx`, `*.pdf`) ; les enregistrements de réunion (`*.mp4`) ; les secrets (`.env`, clés d'API).
- Where the data actually lives (who has access): sur le poste de chaque membre, téléchargée depuis le site public de l'ASD ; enregistrements de réunion sur le Teams commun.
- Tools/services **not** allowed by the client : pendant le projet, tous les outils sont autorisés, puisqu'on travaille uniquement sur des données publiques. À terme, chez LGM, aucune donnée client ne doit aller dans une IA hébergée, **y compris l'IA interne de LGM** : la solution doit fonctionner avec une IA locale, voire sans IA (REQ-8, OBJ-9). Confirmé par LGM le 26/10.
- Personal data involved (GDPR) and how it is handled: aucune dans les données (documentation d'un vélo fictif). Les enregistrements de réunion (voix, noms) ne sont pas versionnés.
- Matching `.gitignore` entries are in place: ☑ (26/10)
