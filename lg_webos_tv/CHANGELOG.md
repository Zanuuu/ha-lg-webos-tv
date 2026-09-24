# Changelog

## 1.1.0 — 2026-09-24

Distribution par dépôt d'apps Home Assistant
(https://github.com/Zanuuu/ha-lg-webos-tv) au lieu d'une copie
dans `/addons`.

- Identifiant de l'app : `lg_webos_tv`. C'est une nouvelle app pour le
  Superviseur : les données de l'app locale (historique, presets, clé
  d'appairage) ne sont pas reprises ; procédure dans
  `docs/deploiement.md`.

## 1.0.3 — 2026-09-24

- App renommée « LG webOS TV » (nom et entrée de la barre latérale),
  nouvelle icône et logo webOS. Identifiant technique inchangé
  (`lg_settings`) : historique, presets et appairage sont conservés.

## 1.0.2 — 2026-09-24

Compatibilité avec le firmware 43.21.77 (webOS 11.2) du téléviseur.

- Appairage avec un manifeste propre à l'app, non signé : webOS 11 rejette
  le manifeste par défaut de bscpylgtv (signature mise en liste noire par
  LG), ce qui rendait l'app muette (`401 not registered`).
- Mode consultation : webOS 11 réserve l'écriture des réglages aux clients
  signés par LG. L'app le détecte à chaque connexion, affiche un bandeau,
  grise les contrôles et masque application de preset et retour arrière ;
  l'API répond 403 aux écritures. Réactivation automatique si l'écriture
  redevient possible.
- Appairage refusé ou expiré détecté (état « Appairage » dans l'en-tête),
  nouvelle demande espacée de trois minutes.
- L'app ne se déclare plus « connectée » quand aucun abonnement n'aboutit.
- Inventaire API relevé sur le 43.21.77 (14 clés lisibles de plus).

## 1.0.1 — 2026-08-17

Interface adaptée aux fenêtres étroites (panneau Ingress sur mobile,
colonne réduite).

- Les lignes de réglage passent le contrôle sous le libellé quand la place
  manque, au lieu d'écraser le texte.
- Sous 720 px : la barre latérale devient un bandeau d'onglets horizontal,
  les curseurs prennent toute la largeur, les tables des presets et de
  l'historique défilent horizontalement.
- En-tête réorganisable (mode d'image, connexion) et hauteur calée sur
  `100dvh` pour les navigateurs mobiles.

## 1.0.0 — 2026-08-17

Première version installable en app Home Assistant locale.

- Réplique complète du menu Réglages (Image, Son, Général, Assistance) en
  français, construite depuis le guide officiel et vérifiée contre le
  firmware webOS 25 (33.31.68).
- Lecture temps réel (abonnement SSAP + repli périodique) et écriture des
  réglages pilotables par l'API ; mention « À régler sur la TV » pour le
  reste.
- Presets : capture complète ou partielle, application avec garde sur le
  mode d'image, import/export JSON.
- Historique : annulation d'une modification, retour à un instant donné.
- Intégration Home Assistant par Ingress (authentification héritée), port
  direct optionnel désactivé par défaut.
