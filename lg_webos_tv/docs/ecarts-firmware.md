# Écarts et corrections issus du firmware 33.31.68

Croisement de l'arbre des menus (transcrit depuis le guide webOS 25)
avec l'app Réglages du firmware installé (`com.palm.app.settings` :
bundle `main.js` + traductions françaises `strings.json`).
Généré par `backend/scripts/croiser_firmware.py`.

## Écarts notables guide → firmware

- `image.mode-selection` : Libellé du mode eco : « Éco » (firmware) vs « Economie d'énergie automatique » (guide) ; « Basique » introuvable dans le firmware.
- `image.parametres-avances.luminosite.luminosite-maximale` : Titre à variante : Luminosité maximale / Luminosité dynamique.
- `image.parametres-avances.couleur.gamme-couleurs` : Choix du firmware : Détection auto/Originale/Dynamique/Étendu/Large — le guide listait Adobe RGB et Cinéma, absents du firmware 33.31.68.
- `son.mode-selection` : Libellés simples confirmés : « Son AI Pro » et « Voix nette » (le guide écrivait « Son AI/Son AI Pro » et « Voix nette/Voix nette Pro »).

## Corrections appliquées

- `general.systeme.parametres-supplementaires.parametres-ecran-veille.duree` : liste de choix posée depuis le firmware (6 choix).
- `general.systeme.parametres-supplementaires.options-de-pointeur.vitesse-de-suivi` : liste de choix posée depuis le firmware (5 choix).
- `general.systeme.parametres-supplementaires.options-de-pointeur.taille-du-pointeur` : liste de choix posée depuis le firmware (3 choix).
- `image.mode-selection` : AVERTISSEMENT, choix « Economie d'énergie automatique » introuvable.
- `image.parametres-avances.luminosite.contraste-dynamique-automatique` : liste de choix posée depuis le firmware (4 choix).
- `image.parametres-avances.luminosite.amplificateur-expression` : liste de choix posée depuis le firmware (3 choix).
- `image.parametres-avances.luminosite.luminosite-maximale` : liste de choix posée depuis le firmware (2 choix).
- `image.parametres-avances.luminosite.gamma` : liste de choix posée depuis le firmware (4 choix).
- `image.parametres-avances.luminosite.plage-video` : liste de choix posée depuis le firmware (3 choix).
- `image.parametres-avances.luminosite.led-local-dimming` : liste de choix posée depuis le firmware (4 choix).
- `image.parametres-avances.couleur.gamme-couleurs` : liste de choix posée depuis le firmware (5 choix).
- `image.parametres-avances.clarte.resolution-elevee` : liste de choix posée depuis le firmware (4 choix).
- `image.parametres-avances.clarte.reduction-bruit` : liste de choix posée depuis le firmware (5 choix).
- `image.parametres-avances.clarte.reduction-bruit-mpeg` : liste de choix posée depuis le firmware (5 choix).
- `image.parametres-avances.clarte.degrades-fluides` : liste de choix posée depuis le firmware (4 choix).
- `image.parametres-avances.clarte.trumotion` : liste de choix posée depuis le firmware (6 choix).
- `son.mode-selection` : liste de choix posée depuis le firmware (8 choix).

## Vérification visuelle sur le téléviseur (utilisateur, 17/08/2026)

- Pas de mode d'image « Basique » ; « Standard » présent.
- Titre confirmé : « Luminosité maximale » (pas « Luminosité dynamique »).
- Gamma : libellés numériques (« 2.2 », « BT.1886 » constatés) — correspondance API à établir en phase 3.
- Température de couleur : curseur (mode expert).
- Ordre confirmé : Image, Son, Général, Assistance ; sous Général : Accessibilité, Toujours prêt, Service d'AI, Optimiseur de jeu, Maintenance OLED, Précautions d'utilisation, Chaînes, Réseau, Périphériques externes, Système, Économie d'énergie.

- `image.mode-selection` : choix supprimé(s) : Basique.
- `image.parametres-avances.luminosite.gamma` : liste de choix posée depuis le firmware (2 choix).

## Constats d'API

- Les clés supplémentaires vues dans l'app (dimensionInfo.*, expressionEnhancer, oledCareMode, energySavingAutoMin, ac4DialogueEnhancer, pointerSpeed/Size, screenOffTime…) sont toutes refusées par l'API publique `getSystemSettings` (testé le 17/08/2026) : l'app passe par le bus Luna privilégié. L'inventaire de la phase 1 reste la référence de ce qui est pilotable.
