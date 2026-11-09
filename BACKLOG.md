# Backlog

Écris tes demandes dans « À faire », une par ligne : `- [ ] ta demande`.
Le chef les traite dans l'ordre, sans te demander de validation.
Légende : `[~]` en cours, `[x]` fait, `[!]` bloqué (raison indiquée).

## À faire

- [ ] 002 M0 Contrats : pyproject.toml, config.toml, workspace.example.toml, models.py, conftest.py, squelette du paquet et CLI
- [ ] 003 M0 CI GitHub Actions, modèles d'issue/PR, CONTRIBUTING.md, squelette README, QUALITY.md et PLANNING.md neutres
- [ ] 004 M0 Données Bike 4.1/4.2 extraites des zip dans data/ (script tools/setup_data.py, zip intacts) + fixtures S1000D synthétiques (proced, IPD, comrep, BREX 022 chaîné, UPF, applic, ICN + PI, DM en erreur, DM marqué 007-00, cas XXE)
- [ ] 005 M1 s1000d/io.py + ident.py + classifieur (aller-retour fidèle, noms de fichiers, rôles)
- [ ] 006 M1 Contrôles : validate.py (XSD, intégrité, ids, liens, ICN) + brex.py (règles 0/1/2, objectValue, chaîne, échange de BREX) + diff C14N
- [ ] 007 M1 Workspace + index + A1 + baseline pre_existing
- [ ] 008 M1 Opérations (8 ops) + A4 localisateur + A5 préparateur de propositions
- [ ] 009 M1 Traçabilité, marquage delete, versioning (3 politiques, suggestion, consolidation, renommage) + A11 writer
- [ ] 010 M1 A7 checker introduced vs pre_existing + blocked_by_rule (≤ 3 essais) + alternatives après rejet
- [ ] 011 M1 A0 orchestrateur (state.json, points d'arrêt, reprise, --auto-accept tests) + CLI typer complète
- [ ] 012 M1 Scénarios lru1010 (synthétique + Bike si données), delete_mark, versioning, preexisting_brex + redactech eval
- [ ] 013 M1 Scénarios batch20 (< 10 s), ops_steps, forbidden_request, brex_swap + docs/DEMO.md CLI
- [ ] 014 M2 RunState persisté, journal des décisions, rapport HTML/JSON, export questions CSV/XLSX
- [ ] 015 M2 Rendu : vue XML, vue Publiée (IETP) XSLT 1.0, côte à côte, masquer les suppressions
- [ ] 016 M2 Interface Streamlit mode Document (§12)
- [ ] 017 M2 Tests UI (AppTest) : modale versioning, accepter/rejeter/en attente, alternative, accept-all limité, vues
- [ ] 018 M2 README (installation ≤ 3 commandes), docs/DEMO.md parcours UI, docs/ROADMAP_NEXT.md
- [ ] 019 M3 (stretch) Couche llm/ : OllamaProvider localhost, FakeLLM + cassettes, NoLLM, garde réseau
- [ ] 020 M3 (stretch) A2 texte libre FR/EN → opérations avec citations + scénarios free_text_fr/en, hallucination_trap
- [ ] 021 M3 (stretch) A10 chat (ops + récap calculé par le code) + panneau assistant + chat_recap + docs/MODELS.md

## En cours

- [~] 001 M0 Hygiène et confidentialité : .gitignore, hooks Python (pre-commit, commit-msg, pre-push), tools/gh_safe.py, CLAUDE.md, tests de confidentialité

## Fait

## Bloqué
