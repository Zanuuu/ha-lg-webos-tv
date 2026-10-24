# LG webOS TV — dépôt d'apps Home Assistant

App Home Assistant qui reproduit, en français, le menu Réglages d'un
téléviseur LG OLED 65 G5 : réglages affichés à leur place dans
l'arborescence et suivis en temps réel, presets exportables, historique
des changements. Intégration par Ingress (entrée dans la barre latérale,
authentification Home Assistant).

Depuis webOS 11 (firmware 43.21.77), le téléviseur réserve l'écriture
directe des réglages aux applications signées par LG : l'app écrit alors par
le pont des alertes système (`createAlert`), et ne passe en **consultation**
que si cette voie est fermée. Détails dans
[`lg_webos_tv/docs/incidents-ecriture.md`](lg_webos_tv/docs/incidents-ecriture.md).

## Installation

Paramètres → Modules complémentaires → Boutique des modules → menu ⋮ →
Dépôts → ajouter :

```
https://github.com/Zanuuu/ha-lg-webos-tv
```

puis installer « LG webOS TV », renseigner `lg_tv_host` (adresse IP du
téléviseur) et accepter la demande d'appairage affichée par la TV.
Documentation de l'app : [`lg_webos_tv/DOCS.md`](lg_webos_tv/DOCS.md) ;
déploiement : [`lg_webos_tv/docs/deploiement.md`](lg_webos_tv/docs/deploiement.md).

## Développement

Backend FastAPI (Python 3.12), frontend React/Vite, arbre des menus en JSON
déclaratif (`lg_webos_tv/menu-tree/`).

```bash
cd lg_webos_tv/backend && .venv/bin/python -m pytest        # tests
cd lg_webos_tv/backend && .venv/bin/python -m uvicorn app.main:app --reload
cd lg_webos_tv/frontend && npm run build                     # build servi par FastAPI
```

## Mentions

Projet personnel, non affilié à LG Electronics. LG, webOS et le logo webOS
sont des marques de leurs propriétaires respectifs.
