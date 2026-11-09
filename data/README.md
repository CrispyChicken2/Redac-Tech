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
├── s1000d-4.2/
│   ├── bike/
│   ├── brex/
│   └── schemas/
└── raw/            # contenu brut, jamais modifié
```

## Reconstruction

Placer les deux archives (Issue 4.1 et Issue 4.2) à la racine du dépôt, puis lancer
`tools/setup_data.py` (tâche 004) : le script recrée l'arborescence ci-dessus.
Les archives et le contenu de `data/` ne sont jamais committés.

## Règle

Ne jamais modifier `data/` : les traitements travaillent sur des copies dans `runs/<id>/`.
