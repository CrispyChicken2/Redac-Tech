# Données

Ce dossier ne contient, côté dépôt, que ce fichier. Tout le reste de `data/` est ignoré par git.

## Origine des données

Seules des données **publiques S1000D** sont utilisées :

- le jeu d'exemple *Bike* en version 4.1 et en version 4.2 ;
- le BREX par défaut de chaque version ;
- les schémas XSD à plat de chaque version.

Ils se téléchargent depuis le site public de S1000D (une archive par version).

## Arborescence attendue

```
data/
├── s1000d-4.1/
│   ├── bike/
│   ├── brex/
│   └── schemas/
└── s1000d-4.2/
    ├── bike/
    ├── brex/
    └── schemas/
```

Comptes attendus après reconstruction (fichiers aplatis, nom de base seul) :

| Dossier | Issue 4.1 | Issue 4.2 |
|---|---|---|
| `bike/` | 152 | 155 |
| `brex/` | 2 | 2 |
| `schemas/` | 30 | 32 |

Le dossier `brex/` reçoit le BREX par défaut de chaque version et la copie du BREX `-022A-D` présent dans le jeu Bike (le fichier reste aussi dans `bike/`).

## Reconstruction

Placer les deux archives à la racine du dépôt :

- `S1000D Issue 4.1.zip`
- `S1000D Issue 4.2.zip`

Puis lancer, depuis la racine du dépôt :

```
py -3 tools/setup_data.py
```

Options :

| Option | Effet |
|---|---|
| `--dry-run` | liste ce qui serait extrait, sans rien écrire |
| `--archives-dir DIR` | dossier contenant les deux archives (par défaut : racine du dépôt principal) |
| `--data-dir DIR` | dossier de sortie (par défaut : `data/` du dépôt principal) |

Comportement :

- Les archives ne sont jamais modifiées ni copiées dans le dépôt.
- Les membres dont le chemin est absolu, contient une lettre de lecteur ou un `..` sont refusés avant toute écriture (la commande s'arrête sans rien écrire).
- La commande est idempotente : relancer ne change que les fichiers qui ont changé. Le résultat affiche, par dossier, le nombre de fichiers nouveaux, mis à jour et inchangés.
- Si une seule archive est présente, seule sa version est reconstruite.

Les archives et le contenu de `data/` ne sont jamais committés (voir `.gitignore`).

## Règle

Ne jamais modifier `data/` : les traitements travaillent sur des copies dans `runs/<id>/`.
