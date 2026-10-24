# Rapport de phase 1 — Exploration de l'API du LG OLED G5

## Téléviseur testé

- Modèle : OLED65G56LS (HE_DTV_W25O_AFABATAA), numéro de série (masqué)
- Firmware : **33.31.68** (webOS TV 25), pays FR, langue fr-FR
- Date des tests : 17 août 2026
- Bibliothèque : bscpylgtv 0.5.2, connexion SSAP en WebSocket TLS (port 3001)

Toute mise à jour du firmware impose de refaire l'inventaire : relancer les
scripts `backend/scripts/explore_*.py` (voir méthodologie).

### Mise à jour 43.21.77 (webOS 11.2) — 24 septembre 2026

- Inventaire relancé (`explore_05`) : `custom_components/lg_webos_tv/inventaire-api.json` reflète
  désormais le 43.21.77. Aucune clé perdue, 14 ajoutées (détail :
  `docs/ecarts-firmware-43.21.77.md`). Mode d'image au moment du relevé :
  `filmMaker`. Champ `firmware` vide : la version logicielle n'est plus
  lisible sans manifeste signé.
- Appairage : le manifeste par défaut de bscpylgtv est en liste noire ;
  les scripts utilisent le manifeste non signé de l'app
  (`custom_components/lg_webos_tv/manifeste-ssap.json`, via `scripts/common.py`).
- **Écriture impossible** (`setSystemSettings` → `401 insufficient
  permissions`) : les sections « écriture » ci-dessous décrivent le
  comportement du 33.31.68. Détail : `docs/incidents-ecriture.md` § 5.

## Méthodologie

L'appairage (`explore_01`) conserve la clé client dans `data/bscpylgtv.sqlite`
(hors git). L'inventaire (`explore_05`) part des 1575 clés candidates de la
documentation communautaire bscpylgtv pour le G5 (`available_settings_G5.md`,
relevé sur firmware 33.21.81), extraites par `extraire_candidats.py`, et teste
chaque clé contre notre téléviseur : l'API nomme les clés rejetées dans son
message d'erreur, ce qui permet un sondage par lots avec retrait itératif.
Résultat brut complet : `custom_components/lg_webos_tv/inventaire-api.json`.

## Réglages lisibles (`getSystemSettings`)

130 clés lisibles sur 1575 candidates, réparties ainsi :

| Catégorie | Lisibles | Contenu |
|---|---|---|
| `picture` | 61 | réglages d'image du mode actif : backlight, contrast, brightness, color, sharpness, tint, colorTemperature, gamma, colorGamut, dynamicContrast, peakBrightness, energySaving, eyeComfortMode, hdrDynamicToneMapping, motionEyeCare, realCinema, truMotionMode*, noiseReduction, mpegNoiseReduction, smoothGradation, superResolution, dynamicColor, balance des blancs (2/10/22 points), CMS complet |
| `lock` | 19 | verrouillages, contrôle parental, limites d'usage |
| `option` | 15 | pays, code postal, audioGuidance, livePlus, storeMode, quickStartMode, wallPaperSettings… |
| `general` | 8 | alwaysOn, tvOnScreen, tvInstallMethod, homeAutoLaunch… |
| `sound` | 8 | soundMode, soundOutput, soundOutputDigital, eArcSupport, avSync, avSyncSpdif, avSyncBypassInput, tvSetupConfiguration |
| `other` | 6 | simplinkEnable, ueiEnable, uhdDeepColorHDMI1–4 |
| `""` | 4 | eulaStatus, localeInfo, mobileSetupStatus… |
| `network` | 3 | deviceName, wolwowlOnOff, bleAdvertisingOnOff |
| `twinTv` | 3 | status, role, systemMode (undefined ici) |
| `time` | 2 | timeZone, onTimerVolume |
| `support` | 1 | automaticUpdate |

\* `truMotionMode` est lisible mais n'apparaissait pas dans la lecture par
lots (présent dans la liste publique communautaire) : à revalider en phase 2
lors du rapprochement clé par clé.

Les valeurs de `picture` sont celles du **mode d'image actif** au moment de la
lecture (ici `expert2`). Le paramètre `dimension` de la requête est accepté
mais ignoré sur ce firmware : impossible de lire les valeurs d'un autre mode
sans changer de mode (vérifié : `vivid`, `cinema`, `game` renvoient les
valeurs du mode courant).

## Catégories inaccessibles en lecture

Rejet de la totalité de leurs clés : `aiPicture`, `caption`, `channel`,
`commercial`, `commercialTv`, `hotelMode`, `musicCatch`, `push`, `soundbar`,
`timemachine`, `timer`, `voiceframework`.

Cas particulier `aspectRatio` : les clés `justScan` et `arcPerApp` sont
acceptées par le schéma mais la lecture échoue avec « There is no matched
result from DB », y compris avec un paramètre `dimension` explicite —
vraisemblablement parce qu'aucune entrée n'était active pendant les tests.
À réessayer avec une source HDMI active ; d'ici là, considéré inaccessible.

Conséquence pour le projet : une grande partie des menus (AI, jeu,
accessibilité fine, entretien OLED, chaînes…) sera affichée « À régler sur la
TV ». Le détail entrée par entrée sera établi en phase 2.

## Réglages modifiables (`setSystemSettings`)

Test d'écriture complet réussi sur `picture.sharpness` (`explore_06`) :
lecture (0) → écriture (1) → relecture confirmant 1 → restauration (0)
→ relecture confirmant 0. La réponse d'écriture est `{"returnValue": true}`.

L'écriture de chaque clé lisible n'a volontairement pas été testée une par
une : cela modifierait réellement tous les réglages du téléviseur. La liste
communautaire des clés modifiables par l'API publique sur G5 couvre
`picture` (toutes les clés lisibles ci-dessus), `sound`, `option`, `other`,
`lock`, `general`, `network`, `time.timeZone`, `support.automaticUpdate`.
Stratégie retenue (déjà prévue au plan) : chaque écriture du service est
suivie d'une relecture de confirmation, donc toute clé refusée à l'écriture
sera détectée à l'usage et consignée. `sound.soundMode` est lisible mais
absent de la liste communautaire d'écriture : à vérifier prudemment en
phase 3.

## Abonnement aux changements (`subscribe`)

Verdict : **fonctionnel**. L'abonnement SSAP `settings/getSystemSettings`
avec `type: subscribe` est accepté (`explore_07`) :

- réponse initiale avec l'état courant des clés demandées ;
- à chaque modification par l'API : notification en **delta** (seules les
  clés modifiées), avec un champ `caller` (`com.webos.service.apiadapter`) ;
- modification à la télécommande : **notifiée également**. Un changement de
  mode d'image via les réglages rapides produit deux notifications : d'abord
  `{"pictureMode": "expert1", "caller": "com.webos.app.quicksettings"}`, puis
  un second delta portant les valeurs du nouveau mode (contrast, brightness,
  color, sharpness, backlight).

Attention : dans ce second delta, les valeurs numériques arrivent sous forme
de **chaînes** (`"contrast": "85"`) alors que la lecture directe renvoie des
entiers. Le backend devra normaliser les types (phase 3).

Conséquence : la synchronisation temps réel du frontend est possible ; le
rafraîchissement périodique reste en filet de sécurité (reconnexions).

## Découverte des plages de valeurs

- `settings/getSystemSettingDesc` est joignable **directement en SSAP** (pas
  besoin du détour Luna, dont le hack par alerte ne renvoie de toute façon
  aucune donnée). Il renvoie type (`Range`, `ArrayExt`…), bornes
  (`min`/`max`/`interval`), listes de choix avec indicateurs `visible` /
  `active` par valeur, et dimensions de dépendance (`input`, `pictureMode`,
  `dynamicRange`).
- Mais il n'accepte qu'une **liste blanche restreinte** de clés sur ce
  firmware — 33 descripteurs obtenus : `picture` (backlight, brightness,
  color, contrast, sharpness, eyeComfortMode, pictureMode — 25 modes dont
  9 visibles en SDR), `lock` (19), `general` (3), `sound` (eArcSupport,
  soundOutput, soundOutputDigital), `""` (eulaInfoNetwork).
- `settings/getSystemSettingValues` existe mais refuse toutes les clés
  essayées (« key is not allowed for the request ») : inutilisable.

Conséquence : pour la majorité des réglages, bornes et listes de choix seront
saisies à la main dans l'arbre des menus (phase 2), comme prévu en repli. Les
33 descripteurs obtenus sont dans `custom_components/lg_webos_tv/inventaire-api.json` et serviront de
référence exacte pour ces clés.

## Décisions découlant de la phase

1. Synchronisation : abonnement temps réel (canal WebSocket backend →
   frontend en phase 3), avec relecture après écriture et rafraîchissement
   périodique en filet de sécurité.
2. Plages de valeurs : saisies à la main en phase 2, sauf pour les clés
   couvertes par `getSystemSettingDesc`.
3. Presets multi-modes : la lecture inter-modes étant impossible
   (`dimension` ignoré), un preset ne peut capturer que les valeurs du mode
   actif. À traiter en phase 5 (capture mode par mode en guidant
   l'utilisateur, ou preset limité au mode actif).
4. Après toute mise à jour du firmware : relancer `explore_05_inventaire.py`
   et comparer `custom_components/lg_webos_tv/inventaire-api.json`.

## Phase 7, étape 0 : origine des changements et cadence d'écriture (24/10/2026)

Firmware 43.21.77, mode d'image Vif, script
`lg_webos_tv/backend/scripts/diag_origine.py`.

**Connexion avec la seule clé client.** `WebOsClient.create(…, client_key=…)`
sans `key_file_path` : connexion et lecture conformes, le stockage
sqlitedict de bscpylgtv n'est pas ouvert. bscpylgtv accepte aussi un
stockage fourni (`storage=`, protocole `StorageProto`), utile pour
l'appairage initial.

**Écriture par alerte.** L'appel `createAlert` + `closeAlert` dure 0,02 à
0,12 s ; la notification d'abonnement portant la nouvelle valeur arrive
environ 0,1 s plus tard, la relecture la retrouve dès le premier essai
(0,5 s). Dix écritures enchaînées sans attente (0,51 s au total) sont
**toutes appliquées, dans l'ordre** : les dix valeurs notifiées sont
exactement les dix demandées. Aucune perte, aucun réordonnancement.

**Champ `caller` des notifications** : il distingue les origines.

| Origine du changement | `caller` |
|---|---|
| Écriture par le pont `createAlert` (nos écritures) | `com.webos.app.starfish_flutter_systemui` |
| Menu Réglages (télécommande) | `com.palm.app.settings` |
| Réglages rapides (mode d'image, curseur de luminosité) | `com.webos.app.quicksettings` |
| Valeurs du nouveau mode, après un changement de mode d'image | **absent** |

**Cascade au changement de mode.** Chaque changement de `pictureMode`
produit une notification avec `caller`, suivie 0,03 à 0,06 s plus tard d'un
second delta **sans `caller`** portant les valeurs du nouveau mode
(contrast, brightness, color, sharpness, backlight). Les types y sont
mêlés : entiers ou chaînes selon le mode (`"contrast": "100"` en Sport,
`"backlight": 100` entier dans le même delta en Jeu).

**Curseur des réglages rapides.** Un glissement produit une rafale
(≈ 25 notifications en 0,5 s), dont de nombreux doublons de la même valeur.

Conséquences pour l'intégration :

1. Confirmation d'écriture sur la notification (≈ 0,15 s) plutôt que par
   relecture périodique ; relecture conservée en secours.
2. File d'écriture : pas de perte à craindre, la coalescence (dernière valeur
   gagnante) sert seulement à ne pas envoyer d'intermédiaires inutiles.
3. Origine : notification d'une écriture en cours de notre part → la nôtre ;
   sans `caller` → cascade de changement de mode ; sinon → changement
   **manuel** sur le téléviseur. Pas de fenêtre temporelle à deviner.
4. Événement « manuel » regroupé par clé (une rafale du curseur = un
   événement) ; normalisation des types appliquée à la cascade.
