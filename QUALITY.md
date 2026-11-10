# Exigences qualité et politique de test

| Grille | Ce qu'elle demande | Où c'est dans ce fichier |
|---|---|---|
| **Q1** | Les exigences qualité du produit sont questionnées et spécifiées | §1 Exigences |
| **Q2** | On a défini comment savoir que chaque exigence est tenue | §2 Vérification |
| **Q3** | Les vérifications ont réellement été exécutées | §2 colonnes *Résultat* et *Preuve* + §3 Journal |

Planning et jalons : [PLANNING.md](PLANNING.md). Besoin, périmètre et choix de l'approche : note d'orientation du projet (à venir dans `docs/`).

**Produit visé** : l'outil prépare les reprises d'un manuel S1000D comme un rédacteur technique, selon **deux modes d'entrée** :
- **Mode « demande »** : l'ancien manuel + le contexte de la modification (phrase, bulletin, liste de correspondances), par exemple « la pièce X2 est remplacée par X3 ».
- **Mode « comparaison »** : l'ancien manuel + **une version à jour fournie à part** (deux fichiers distincts). L'outil détecte les différences et les reporte dans l'ancienne version, sans l'écraser : identifiants, applicabilité et ajouts propres à l'ancienne version sont conservés. Si l'ancienne version a aussi évolué de son côté, les modifications contradictoires apparaissent comme des conflits à arbitrer, comme dans git.

Dans les deux modes, le rédacteur contrôle chaque changement dans une revue avant / après « type git » (accepter, refuser, en attente + commentaire), puis l'outil produit le nouveau manuel, conforme S1000D et tracé. Approche retenue : **hybride**. Le code fait la recherche, la comparaison et l'application des modifications ; le LLM sert seulement à comprendre une demande et à rédiger du texte nouveau.

---

## 1. Exigences (Q1)

### Objectifs du projet (cibles, seuils provisoires)

Ils décrivent la qualité attendue : **exhaustivité, intégrité, homogénéité**. Chacun devient une exigence REQ-x dès que le prototype permet de le mesurer. Les seuils sont fixés **avant** de voir les résultats, puis soumis à l'évaluateur.

| ID | Objectif | Indicateur & seuil provisoire | Devient exigence | Exigence |
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

#### Objectifs proposés (seuils provisoires, à valider)

| ID | Objectif | Indicateur & seuil provisoire | Exigence |
|---|---|---|---|
| OBJ-21 | **Politique de versioning appliquée** | 100 % des DM modifiés portent `issueInfo` (`issueNumber` / `inWork`), un nom de fichier et une entrée de journal conformes à la politique choisie (`none`, `in_work`, `new_issue`) | à créer |
| OBJ-22 | **Erreurs préexistantes signalées comme telles** | 100 % des erreurs XSD / BREX déjà présentes avant traitement sont rapportées comme `pre_existing` et jamais imputées à l'outil ; 0 erreur `introduced` livrée | à créer |
| OBJ-23 | **Demande interdite par le BREX** | Une demande que le BREX interdit aboutit à `blocked_by_rule` en ≤ 3 essais, avec la règle citée, sans boucle | à créer |

### Exigences du prototype

| ID | Exigence | Caractéristique | Métrique & seuil | Pourquoi c'est important | Validée par l'évaluateur ? |
|---|---|---|---|---|---|
| REQ-1 | L'état de l'art couvre les 4 pistes d'automatisation identifiées | Adéquation fonctionnelle | ≥ 1 approche / outil documenté (avec source) pour chacune des 4 pistes : (a) conversion Word ↔ XML, (b) compilation des données d'entrée, (c) harmonisation de la rédaction, (d) multilingue | Choisir où automatiser en connaissant les options | ☑ |
| REQ-2 | La restitution permet de dégager des orientations de projet concrètes | Utilisabilité | ≥ 2 pistes retenues à la fin de la restitution | Le sujet est vaste : il faut réduire le périmètre | ☑ |
| REQ-3 | Aucune donnée privée dans le dépôt | Sécurité & confidentialité | 0 fichier de données privées versionné (`git ls-files` + `.gitignore` + tests `tests/security/`) ; uniquement des données S1000D publiques | Les documents techniques réels sont confidentiels | ☑ |
| REQ-4 | L'orientation et les approches techniques sont écrites et validées | Adéquation fonctionnelle | Note d'orientation (besoin, périmètre, hors périmètre, objectifs, ≥ 2 approches comparées, questions ouvertes) validée par l'évaluateur | Viser le bon besoin | ☐ |
| REQ-5 | **Exhaustivité** : aucune modification nécessaire n'est oubliée | Adéquation fonctionnelle | Scénario `LRU1010` → `LRU2020` (contexte + liste des modifications attendues écrits **avant** d'exécuter l'outil) : 100 % des modifications attendues faites (2/2), 0 hors liste, et les 2 traces historiques laissées intactes | Les oublis sont l'erreur la plus fréquente de la reprise manuelle ; à l'inverse, réécrire l'historique fausserait le manuel | ☐ |
| REQ-6 | **Intégrité** : seul ce qui est demandé change, et le manuel reste conforme | Adéquation fonctionnelle | 0 différence hors modifications attendues (diff XML canonique ancien / nouveau) ; 100 % des DM produits valides selon les XSD S1000D | Une modification ne doit rien casser ailleurs | ☐ |
| REQ-7 | Le rédacteur garde la main : il voit l'avant / après et décide | Utilisabilité | L'évaluateur réalise le scénario seul (accepter / refuser / en attente + commentaire) ; note d'utilité ≥ 3/5 ; 0 changement appliqué sans décision | Un fonctionnement « comme git » est attendu | ☐ |
| REQ-8 | Les appels à l'IA sont isolés et remplaçables par un modèle local | Sécurité & confidentialité | 100 % des appels à l'IA dans un seul module (`src/redactech/llm/`) ; changer de modèle = 1 changement de configuration | Aucune donnée documentaire ne doit aller dans un LLM hébergé | ☑ |
| REQ-9 | Le prototype se lance sans l'équipe | Maintenabilité | Installation + exécution en ≤ 3 commandes en suivant le README, testé par un membre qui n'a pas écrit le code | Les briques doivent pouvoir être reprises | ☐ |
| REQ-10 | **Traçabilité S1000D** du nouveau manuel | Compatibilité | 100 % des DM modifiés : `issueInfo` selon la politique de versioning, `changeMark="1"` + `changeType` sur chaque élément modifié, `reasonForUpdate` reprenant le contexte | Le DM doit se rouvrir dans un éditeur XML et se relire comme une reprise faite à la main | ☐ |
| REQ-11 | Le nouveau manuel respecte le BREX | Compatibilité | 100 % des DM produits sans violation du BREX (chaîne du DM, jusqu'au BREX par défaut S1000D) | Contrôle avant livraison | ☐ |

> **REQ-8** : la contrainte (« pas d'IA hébergée, cible locale ») est actée ; le seuil exact reste à confirmer.

> **Scénario `LRU1010` (REQ-5)** : `LRU1010` apparaît 4 fois dans 3 fichiers du jeu de données public Bike. 2 occurrences sont à modifier : la déclaration de la pièce dans le dépôt commun `comrep`, et la référence dans l'`IPD`. Les 2 autres sont des traces historiques dans le fichier `UPF`, à laisser intactes (« règle UPF à confirmer »).

## 2. Vérification (Q2 → Q3)

| ID | Méthode de vérification | Critère de réussite | Quand (automatique / à chaque étape / avant démo) | Responsable | Résultat | Preuve |
|---|---|---|---|---|---|---|
| REQ-1 | Checklist : tableau pistes × approches dans le document d'état de l'art | Chacune des 4 pistes a ≥ 1 approche sourcée | Avant la restitution | ✏️ | ✅ | ✏️ lien vers le document |
| REQ-2 | Revue à la restitution orale | ≥ 2 orientations notées dans le compte rendu | Démo | ✏️ | ✅ | ✏️ lien vers le compte rendu |
| REQ-3 | Audit : `git ls-files` + vérification du `.gitignore` + `py tools/privacy.py scan --tracked` | 0 fichier de données privées | Chaque étape + CI | ✏️ | ✅ | `git ls-files` = code et docs seulement ; `.gitignore` en place ; tests `tests/security/` (2 fichiers) ; hooks `pre-commit`, `commit-msg` et `pre-push` installés ; `py -3 tools/privacy.py scan --tracked` : exit 0 sur le poste de développement, le 2026-11-10 |
| REQ-4 | Revue de la note d'orientation | Validation écrite | Avant le développement | ✏️ | ⏳ | |
| REQ-5 | Test automatique (pytest) : modifications faites comparées au fichier `tests/scenarios/lru1010/attendu.yaml`, écrit avant le code (2 modifications attendues + 2 occurrences à ne pas toucher) | 2/2 modifications faites, 0 hors liste, 2/2 traces historiques identiques à l'original | À chaque commit (CI) + en direct à la démo | ✏️ | ⚠️ | vert sur fixtures en CI (scénario `tests/scenarios/lru1010`), à confirmer sur le Bike réel (tests data41 non exécutés) |
| REQ-6 | Test automatique : diff XML canonique ancien / nouveau limité aux éléments attendus + validation XSD de chaque DM produit | 0 différence hors liste ; 100 % valides | À chaque commit (CI) + en direct à la démo | ✏️ | ⚠️ | vert sur fixtures en CI (scénario `tests/scenarios/lru1010`), à confirmer sur le Bike réel (tests data41 non exécutés) |
| REQ-7 | Test utilisateur : l'évaluateur déroule le scénario seul, puis note l'utilité ; tests d'interface automatiques | Scénario terminé sans aide ; note ≥ 3/5 ; journal des décisions complet | Démo | ✏️ | ⚠️ | 0 changement écrit sans décision : prouvé par tests UI et pipeline en CI (run 42790955399, rapporté, non vérifié sur ce poste) ; test utilisateur avec l'évaluateur à faire |
| REQ-8 | Revue de code (recherche de tous les appels à l'IA) + test : le même scénario tourne avec le modèle changé dans la configuration | Tous les appels dans `src/redactech/llm/` ; changer de modèle = 1 ligne de configuration | Chaque étape | ✏️ | ⏳ | |
| REQ-9 | Test interne : un membre qui n'a pas écrit le code suit le README sur une machine propre | ≤ 3 commandes, sans aide | Avant la démo | ✏️ | ⚠️ | installation en 3 commandes documentée (README) ; test par un membre qui n'a pas écrit le code à faire |
| REQ-10 | Test automatique : relecture de chaque DM modifié (`issueInfo`, `@changeMark`, `@changeType`, `reasonForUpdate`) | 100 % des DM modifiés conformes | À chaque commit (CI) | ✏️ | ⚠️ | vert sur fixtures en CI (scénarios `tests/scenarios/delete_mark`, `tests/scenarios/versioning`), à confirmer sur le Bike réel (tests data41 non exécutés) |
| REQ-11 | Test automatique : contrôle des DM produits contre la chaîne BREX (validateur BREX externe ou vérificateur XPath interne) | 0 violation introduite | À chaque commit (CI) | ✏️ | ⚠️ | vert sur fixtures en CI (scénarios `tests/scenarios/preexisting_brex`, `tests/scenarios/lru1010`), à confirmer sur le Bike réel (tests data41 non exécutés) |
| OBJ-21 | Test automatique : 3 politiques de versioning, renommage de fichier, journal | 100 % conformes | À chaque commit (CI) | ✏️ | ⚠️ | vert sur fixtures en CI (scénario `tests/scenarios/versioning`), à confirmer sur le Bike réel (tests data41 non exécutés) |
| OBJ-22 | Test automatique : DM déjà fautif en entrée | Erreurs classées `pre_existing`, 0 `introduced` | À chaque commit (CI) | ✏️ | ⚠️ | vert sur fixtures en CI (scénario `tests/scenarios/preexisting_brex`), à confirmer sur le Bike réel (tests data41 non exécutés) |
| OBJ-23 | Test automatique : scénario de demande interdite | `blocked_by_rule` en ≤ 3 essais, sans boucle | À chaque commit (CI) | ✏️ | ⚠️ | vert sur fixtures en CI (scénario `tests/scenarios/forbidden_request`), à confirmer sur le Bike réel (tests data41 non exécutés) |
| OBJ-1 | Scénario `LRU1010`, puis scénarios variés | 100 % des modifications attendues faites, 0 hors liste | À chaque commit (CI) | ✏️ | ⚠️ | vert sur fixtures en CI (scénarios `tests/scenarios/lru1010`, `tests/scenarios/ops_steps`), à confirmer sur le Bike réel (tests data41 non exécutés) |
| OBJ-10 | Sans LLM, puis avec LLM | Propagation de 20 modifications sur le manuel complet en < 10 s (sans LLM) ; une demande traitée en < 2 min avec le LLM local, sur un portable standard | À chaque commit (CI) | ✏️ | ⚠️ | vert sur fixtures en CI (scénario `tests/scenarios/batch20`, sans LLM), à confirmer sur le Bike réel (scénario `tests/scenarios/batch20_bike41`, tests data41 non exécutés) ; la partie avec LLM n'est pas couverte |
| OBJ-19 | Revue avant / après | 100 % des illustrations (figures, légendes) liées à un élément modifié signalées au rédacteur comme « à vérifier » (l'outil ne modifie pas les images) | À chaque commit (CI) | ✏️ | ⚠️ | vert sur fixtures en CI (scénario `tests/scenarios/ops_steps`, figure `fig-0001`), à confirmer sur le Bike réel (tests data41 non exécutés) ; la revue humaine avant / après n'est pas faite |

> Statut : ⏳ pas encore exécuté · ✅ réussi · ⚠️ partiel · ❌ échec (dire quoi faire dans le §3)

## 3. Journal (une entrée par étape)

### Étape 1 : cadrage
- Ajouté : pas encore d'exigences qualité.
- Vérifié : liste des questions de cadrage établie. Le périmètre est limité à la norme publique S1000D (Bike data set, BREX par défaut).
- Suite : état de l'art des 4 pistes.

### Étape 2 : état de l'art
- Ajouté : REQ-1 à REQ-3 (état de l'art, orientations, confidentialité).
- Vérifié : REQ-1 ✅, REQ-2 ✅. En complément, deux prototypes de recherche (conversion Word → XML et contrôle multilingue) ont été évalués sur le Bike ; ils sont mis en suspens après l'orientation.
- Suite : acter l'orientation.

### Étape 3 : orientation et premier prototype
- Ajouté : orientation « reprise et modification de manuels existants » ; objectifs OBJ-1 à OBJ-14 ; REQ-4, 5, 6, 8, 9, 10 ; REQ-7 et REQ-11 planifiées ensuite ; approche hybride retenue.
- Ajouté : **mode « comparaison »** (mettre à jour l'ancienne version à partir d'une version à jour fournie à part) et objectifs OBJ-15 à OBJ-20. Le scénario `LRU1010` est précisé : 2 occurrences à modifier, 2 traces historiques à laisser intactes.
- Ajouté : objectifs proposés OBJ-21 à OBJ-23 (versioning, erreurs préexistantes, demandes interdites par le BREX).
- Vérifié : REQ-3 ✅ (audit du dépôt, tests de confidentialité). Autres résultats : à remplir quand les vérifications sont exécutées.
- Suite : faire valider la note d'orientation et les seuils des OBJ ; revue avant / après, BREX, signalement des illustrations.

### Étape M1 : clôture du premier jalon
- Ajouté : chaîne de traitement de bout en bout sur les fixtures synthétiques : hygiène et confidentialité, contrats, CI, données Bike reconstruites localement, contrôles XSD / BREX, workspace et index, baseline, opérations, traçabilité et versioning, vérification des propositions, orchestrateur et CLI, scénarios de bout en bout.
- Vérifié (rapporté, non vérifié sur ce poste) : run de CI GitHub `42757082793` sur la branche `prototype1`, indiqué comme : 690 tests réussis, lint propre. Ce poste n'a pas de dépôt distant configuré : le run n'a pas pu être consulté depuis ici.
- Vérifié sur ce poste : `py -3 tools/privacy.py scan --tracked` sans terme interdit (exit 0) ; `tests/security/` présent ; hooks `pre-commit`, `commit-msg` et `pre-push` installés.
- Non vérifié : tests `data41` et `data42`, et scénarios `lru1010_bike41` et `batch20_bike41` (données Bike absentes de ce poste) ; la partie « avec LLM » de OBJ-10 (aucun LLM branché) ; la revue humaine avant / après de OBJ-19.
- Seuils inchangés. Cellules ✏️ non remplies.
- Suite : confirmer les ⚠️ sur le Bike réel (tests `data41`), puis remplir les cellules ✏️.

### Étape M2 : interface, rapport et vues
- Ajouté : interface Streamlit en mode Document (projet, demande, propositions, livraison) ; vues XML, publiée (IETP) et côte à côte ; rapport de livraison (JSON, HTML), questions (CSV, XLSX), journal des décisions ; installation en trois commandes documentée dans le README ; feuille de route de la suite (`docs/ROADMAP_NEXT.md`).
- Vérifié (rapporté, non vérifié sur ce poste) : tests UI verts en CI (run 42790955399, 834 tests réussis), rapporté par le responsable du projet. Ce poste n'a pas de dépôt distant.
- Vérifié sur ce poste : `docs/DEMO.md` relu contre le code de l'interface (libellés, options, comportements). Corrigés : export XLSX à l'écriture, liste d'opérations du formulaire, remise à zéro du run après import ou remplacement de BREX, création du dossier de session au chargement.
- Non vérifié : le parcours de l'interface à l'écran ; le test d'installation par un membre (REQ-9) et le test utilisateur avec l'évaluateur (REQ-7).
- Suite : faire le test d'installation (REQ-9) et le test utilisateur (REQ-7) ; confirmer les résultats de CI sur le Bike réel.

## 4. Règles sur les données et la confidentialité

- Données de travail : uniquement des données **publiques**, la norme S1000D (Bike data set Issue 4.1 pour le développement ; Issue 4.2 pour vérifier la compatibilité avec les XSD 4.2 et comme paires « ancienne / à jour » du mode comparaison, les mêmes DM existant dans les deux éditions ; BREX par défaut). Aucune documentation réelle, aucun projet passé, aucun BREX interne n'entre dans le projet.
- Données qui ne doivent **jamais** être versionnées : toute donnée privée ou issue d'un usage réel ; les archives téléchargées (`*.zip`) et le dossier `data/` (retéléchargeables depuis le site public de S1000D) ; les sorties générées (`output/`, `*.docx`, `*.pdf`) ; les enregistrements (`*.mp4`) ; les secrets (`.env`, clés d'API).
- Où vivent réellement les données : sur le poste de chaque membre, téléchargées depuis le site public de S1000D.
- Outils / services **non** autorisés : à terme, aucune donnée documentaire ne doit aller dans une IA hébergée, quelle qu'elle soit : la solution doit fonctionner avec une IA locale, voire sans IA (REQ-8, OBJ-9).
- Données personnelles (RGPD) et traitement : aucune dans les données (documentation d'un vélo fictif). Les enregistrements éventuels ne sont pas versionnés.
- Entrées `.gitignore` correspondantes en place : ☑ (voir `.gitignore`, `CLAUDE.md` §3 et `docs/PRIVACY.md`).
