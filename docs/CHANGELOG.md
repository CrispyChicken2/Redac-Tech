# Journal des modifications

## 001 — Hygiène et confidentialité

**Statut :** fusionnée. **Tests non exécutés sur ce poste.**

### Ajouté

- `tools/privacy.py` : contrôle des termes interdits (liste locale `.agents/denylist.txt`, non suivie) sur le contenu, les noms de fichiers, les messages de commit, les noms de branches et les tags. Les résultats sont masqués. Commandes `scan --tracked`, `scan --staged`, `scan --text-file`.
- `tools/hooks/pre_commit.py`, `tools/hooks/commit_msg.py`, `tools/hooks/pre_push.py` : contrôles appelés par git avant commit et avant push.
- `tools/install_hooks.py` : installation idempotente des trois hooks dans `.git/hooks/` (partagés par tous les worktrees).
- `tools/gh_safe.py` : wrapper de `gh` qui contrôle arguments, fichiers de corps et entrée standard avant tout appel. Refuse d'agir sans liste de termes, sauf réglage explicite.
- `.gitignore` : exclusion de `.agents/`, des worktrees, des caches, des archives, des données et des sorties générées.
- `CLAUDE.md` : règles permanentes du dépôt (rôles, confidentialité, règles d'ingénierie, commandes).
- `data/README.md` : seul fichier suivi du dossier `data/`, décrit l'origine des données publiques et leur reconstruction locale.
- `tests/security/test_privacy_tools.py` : tests unitaires des fonctions de contrôle, des hooks, de l'installeur et de `gh_safe`, avec des termes fictifs.
- `tests/security/test_privacy.py` : audit du dépôt réel (aucun terme interdit dans les fichiers suivis, aucun chemin interdit suivi, aucune archive suivie, `.agents/` exclu).

### Tests écrits, non exécutés

Les tests de `tests/security/` ont été écrits et relus, mais **ils n'ont pas été exécutés sur ce poste** : la règle machine interdit `pytest` et tout téléchargement de paquets. La vérification repose sur la relecture statique et sur la compilation des fichiers Python. Ils doivent être lancés par le chef de projet une fois les dépendances installées.

### Non couvert

- Pas de remote distant : la CI GitHub n'est pas exécutable pour l'instant.
- Le contrôle ne vaut que pour les termes présents dans la liste locale.
