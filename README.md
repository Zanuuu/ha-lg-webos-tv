# LG webOS TV pour Home Assistant

[![Ajouter le dépôt à Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FZanuuu%2Fha-lg-webos-tv)

> **English** — A Home Assistant app (add-on) that brings the Settings menu
> of LG webOS TVs into Home Assistant: browse and change picture, sound and
> general settings in real time, save and restore presets, and undo changes
> from the history. The interface is in **French** (it mirrors the French
> menu of the LG OLED G5, webOS 25). Install it by adding this repository
> to Home Assistant (button above), then set the TV's IP address in the
> app's configuration.

Le menu Réglages de votre téléviseur LG, en français, dans la barre
latérale de Home Assistant.

![Aperçu de l'interface : réglages de luminosité](docs/images/apercu.png)

## Fonctionnalités

- **Arborescence du menu Réglages** reproduite à l'identique (Image, Son,
  Général, Assistance), avec les libellés et descriptions du téléviseur.
- **Réglages en temps réel** : une modification faite à la télécommande
  apparaît aussitôt, une modification faite dans l'app est appliquée et
  confirmée par relecture.
- **Presets** : capturer l'état des réglages, le réappliquer, l'exporter ou
  l'importer en JSON.
- **Historique** de toutes les modifications, avec retour arrière.
- Réglages non exposés par l'API affichés à leur place, avec la mention
  « À régler sur la TV ».
- Intégration par **Ingress** : authentification Home Assistant, aucun port
  ouvert sur le réseau par défaut. Thème clair ou sombre selon le système.

## Téléviseurs pris en charge

L'arborescence est celle du **LG OLED G5 (webOS 25)**, testée sur les
firmwares 33.31.68 et 43.21.77 (webOS 11.2). Sur d'autres modèles LG webOS,
la plupart des réglages courants devraient fonctionner, mais l'arborescence
peut différer. Les retours sur d'autres modèles sont bienvenus.

Depuis webOS 11.2, le téléviseur réserve l'écriture directe des réglages aux
applications signées par LG : l'app écrit alors par le pont des alertes
système, et passe en **consultation** seulement si cette voie est fermée
(détails dans [`docs/incidents-ecriture.md`](docs/incidents-ecriture.md)).

## Installation

1. Ajouter le dépôt avec le bouton ci-dessus, ou manuellement :
   Paramètres → Modules complémentaires → Boutique des modules → menu ⋮ →
   Dépôts → `https://github.com/Zanuuu/ha-lg-webos-tv`.
2. Installer « LG webOS TV ». Le Superviseur construit l'image sur place :
   comptez quelques minutes la première fois.
3. Onglet Configuration : renseigner l'**adresse IP du téléviseur**.
4. Démarrer l'app, puis accepter la demande d'appairage affichée par le
   téléviseur.
5. Ouvrir « LG webOS TV » dans la barre latérale.

Documentation complète (options, mode consultation, dépannage) :
[`lg_webos_tv/DOCS.md`](lg_webos_tv/DOCS.md). Elle est aussi affichée dans
l'onglet Documentation de l'app.

## Développement

Backend FastAPI (Python 3.12), frontend React / Vite, arborescence des
menus en JSON déclaratif (`lg_webos_tv/menu-tree/`). Lancer en local,
tests, publication, notes techniques : voir
[`docs/developpement.md`](docs/developpement.md).

```bash
cd lg_webos_tv/backend && .venv/bin/python -m pytest
LG_TV_HOST=<ip> .venv/bin/python -m uvicorn app.main:app --reload
cd lg_webos_tv/frontend && npm run build
```

Les contributions sont bienvenues : signalements, corrections de
l'arborescence pour d'autres modèles, traductions.

## Licence et mentions

Code sous licence [MIT](LICENSE).

Projet communautaire, non affilié à LG Electronics ni approuvé par elle.
LG, webOS et le logo webOS sont des marques de leurs propriétaires
respectifs.
