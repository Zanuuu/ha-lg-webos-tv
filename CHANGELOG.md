# Changelog

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
