# Confidentialité : outillage de contrôle

Ce document décrit les contrôles qui empêchent des informations privées de se retrouver dans le dépôt git ou sur GitHub. Il est la référence d'usage ; les règles complètes restent dans `CLAUDE.md` (section 3).

## Ce qui est contrôlé

Le contrôle porte sur tout ce qui peut être suivi par git ou publié sur GitHub :

- le contenu des fichiers (code, commentaires, tests, fixtures, documentation, prompts) ;
- les noms de fichiers et de dossiers ;
- les messages de commit ;
- les noms de branches et de tags, ainsi que le message des tags annotés ;
- le contenu des commits à pousser (diffs).

Un terme interdit trouvé dans l'un de ces éléments bloque l'opération (commit, push, appel `gh`). Les résultats affichés sont **masqués** : le terme trouvé est remplacé par `***`, il n'apparaît jamais dans la sortie.

## Où vit la liste de termes interdits

- Fichier : `.agents/denylist.txt`, dans le dossier principal du dépôt (et non dans un worktree).
- Ce fichier est **local** : il n'est jamais suivi par git (`.agents/` figure dans `.gitignore` et dans `.git/info/exclude`).
- Un terme par ligne ; les lignes commençant par `#` sont des commentaires. La casse est ignorée et seul le mot entier compte.
- Les exceptions exactes sont listées dans `.agents/allowlist.txt`, également local.
- Il est interdit de recopier un terme de cette liste dans la documentation, les tests, les messages de commit, les issues ou les PR. Dans un texte, décrire une catégorie (« un client », « une personne ») plutôt que le nom réel.

Variables d'environnement de remplacement (utilisées notamment par la CI) :

| Variable | Rôle |
|---|---|
| `REDACTECH_DENYLIST` | liste de termes, un par ligne |
| `REDACTECH_DENYLIST_FILE` | chemin d'un fichier de termes |
| `REDACTECH_ALLOWLIST` | liste d'exceptions, une par ligne |

Sans liste disponible, le contrôle affiche un avertissement `NOTICE` et ne bloque rien (`tools/privacy.py`). À l'inverse, `tools/gh_safe.py` **refuse** d'appeler `gh` sans liste, sauf si `GH_SAFE_ALLOW_NO_DENYLIST=1` est défini.

## Installer les hooks git

Les hooks sont installés une fois par dépôt (ils sont partagés par tous les worktrees) :

```
py -3 tools/install_hooks.py
```

Trois hooks sont posés dans `.git/hooks/` :

| Hook | Ce qu'il contrôle |
|---|---|
| `pre-commit` | le contenu indexé (les blobs « stagés ») et les noms de fichiers stagés |
| `commit-msg` | tout le message de commit, y compris les lignes commençant par `#` |
| `pre-push` | les refs poussées, les messages et diffs des nouveaux commits, les tags annotés |

La commande est idempotente. Si un hook étranger existait déjà, il est conservé sous le nom `<hook>.orig`. Chaque hook est un petit script `sh` qui appelle Python (`py -3`, puis `python3`, puis `python`) ; si aucun interpréteur n'est trouvé, le hook refuse l'opération.

Un hook qui échoue doit être corrigé, pas contourné : ne pas utiliser `--no-verify`.

## Scanner le dépôt

Scanner tous les fichiers suivis par git :

```
py -3 tools/privacy.py scan --tracked
```

Scanner uniquement ce qui est indexé pour le prochain commit :

```
py -3 tools/privacy.py scan --staged
```

Scanner un fichier texte (utile pour un brouillon avant de le copier) :

```
py -3 tools/privacy.py scan --text-file CHEMIN
```

Code de sortie : `0` si rien n'est trouvé, `1` si un terme est trouvé. Les données binaires (premiers 8 Kio contenant un octet nul) ne sont pas lues ; leur nom, lui, est toujours contrôlé.

## Publier avec `tools/gh_safe.py`

Toute écriture sur GitHub passe par le wrapper, qui analyse les arguments, le corps des fichiers passés par `--body-file` / `-F` / `--input`, et l'entrée standard quand elle est lue (`-F clé=@-`) avant d'appeler `gh` :

```
py -3 tools/gh_safe.py issue create --title "Titre" --body-file corps.md
py -3 tools/gh_safe.py pr create --title "Titre" --body-file corps.md
```

En cas de terme trouvé, `gh` n'est pas appelé, les correspondances masquées sont affichées et le code de sortie est `1`. Le binaire `gh` peut être remplacé par la variable `GH_SAFE_GH` (utilisée par les tests).

## Limites connues

- Le contrôle ne détecte que les termes de la liste locale. Une information sensible absente de la liste n'est pas repérée : garder la liste à jour.
- Les termes sont recherchés comme mots entiers, sans tenir compte de la casse. Une variante écrite autrement (abréviation, faute, autre graphie) doit être ajoutée à la liste si elle est possible.
- Les hooks ne protègent que le poste où ils sont installés. Ils ne remplacent pas la relecture humaine avant une publication.
- La CI prévoit un contrôle identique (variable `REDACTECH_DENYLIST`) ; son exécution dépend de la mise en place d'un dépôt distant.
