# Données

Seul ce fichier est versionné ; le reste de `data/` est ignoré par git (voir `.gitignore`).
On n'utilise **que des données publiques** : LGM ne fournit aucune donnée (secteur défense).

## Source

Norme **S1000D Issue 4.1**, téléchargée librement (sans compte) sur le site de l'ASD :
https://s1000d.org (rubrique Downloads, Issue 4.1).

## Arborescence

```
data/
├── raw/                    archive telle que téléchargée, ne jamais modifier
│   └── S1000D Issue 4.1/
└── s1000d-4.1/             extraits utilisés par le projet
    ├── bike/               Bike data set : data modules XML (DMC-*, DDN-*, PMC-*) + illustrations (CGM, JPG…)
    ├── brex/               BREX par défaut (règles de rédaction) : DMC-S1000D-E-04-10-0301-00A-022A-D_009-00_EN-US.XML
    └── schemas/            schémas XSD « flat » pour valider les data modules
```

## Reconstruire `s1000d-4.1/` depuis `raw/`

Depuis la racine du dépôt (Git Bash) :

```bash
R="data/raw/S1000D Issue 4.1/Issue 4.1"; O=data/s1000d-4.1
mkdir -p $O/bike $O/brex $O/schemas
unzip -q "$R/Bike data set/S1000D_4-1_Bike_Samples.zip" -d /tmp/bike && cp -r /tmp/bike/S1000D_4-1_Bike_Samples/. $O/bike/
unzip -q "$R/Default BREX data module/S1000D_4.1_Default_BREX.zip" -d $O/brex
cp -r "$R/xml_schema_flat/." $O/schemas/
```

La spécification complète (PDF) est dans `raw/.../Specification/S1000D_Issue_4.1.zip`.
