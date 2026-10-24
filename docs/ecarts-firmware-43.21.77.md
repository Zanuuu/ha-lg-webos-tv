# Écarts du firmware 43.21.77 (webOS 11.2) par rapport au 33.31.68

Relevé du 24/09/2026. Firmware `lib32-starfish-global-secured-o24n-qilian-3706-43.21.77`,
otaID `HE_DTV_W25O_AFABATAA` (même plateforme G5), webOS **11.2.0**
(33.31.68 : webOS 10.3.1). Extraction dans une copie locale hors dépôt
(clé AES `o24n`, même chaîne que `COMPTE-RENDU-extraction.md`) ; copies utiles
dans `data/firmware/43.21.77/` (hors git).

`docs/ecarts-firmware.md` reste le rapport généré par `croiser_firmware.py`
pour le 33.31.68 ; ce fichier-ci est rédigé à la main et **ne modifie pas
`menu-tree/`** : chaque point est une proposition à valider.

## 1. Accès API (bloquant, traité)

Liste noire du manifeste d'appairage et écriture réservée aux clients
signés par LG : voir `docs/incidents-ecriture.md` § 5. L'app fonctionne
en mode consultation sous ce firmware jusqu'à la version 1.1.1 ; depuis la
1.2.0, l'écriture passe par le pont `createAlert` (§ 7 du même document).

Le **mode développeur** a été testé comme voie d'écriture alternative
(SSH `prisoner`, appel local au service de réglages) : sans effet, `prisoner`
étant confiné au bus luna public qui refuse le service de réglages
(`docs/incidents-ecriture.md` § 6). Seul un accès root permettrait l'écriture ;
non retenu. (Conclusion dépassée par le pont `createAlert`, § 7.)

## 2. Clés lisibles (`valid-settings.js`, inventaire relancé)

Aucune clé retirée. Clés ajoutées à la liste publique, confirmées lisibles
sur le téléviseur (`custom_components/lg_webos_tv/inventaire-api.json`) :

| Catégorie | Nouvelles clés |
|---|---|
| `option` | `standByLight` |
| `time` | `timeOffset`, `offTimerEnable`, `autoOff2HourOnTimer`, `automaticStandBy` |
| `other` | `uhdDeepColor`, `444BypassHDMI1` à `444BypassHDMI4` |
| `sound` | `digitalAudioPriority`, `lgSoundSync` |
| `hotelMode` | `enableHotelMode` (nouvelle catégorie publique) |

Descripteurs : champ `dataType` ajouté ; `pictureMode` gagne les modes
`creator`, `hdrCreator`, `dolbyHdrCreator` (marqués non visibles sur notre
entrée HDMI/SDR).

**Proposition A.** Rattacher ces clés aux entrées existantes de
`menu-tree/` quand elles correspondent à un réglage déjà transcrit (ex.
veille automatique, voyant de veille, Deep Colour HDMI), après
vérification du libellé sur la TV. Rien n'est ajouté tant que ce n'est pas
confirmé.

**Proposition B.** Mode d'image « Créateur » (`creator`) : à vérifier sur la TV
(présence dans le menu, libellé français exact) avant tout ajout.

## 3. App Réglages (`com.palm.app.settings`)

Bundle `main.js` : 3,24 Mo → 3,08 Mo. Traductions françaises : 1 968 →
1 745 chaînes (563 retirées, 340 nouvelles). Comparaison mécanique contre
`menu-tree/` (293 entrées) :

- **Clés API qui n'apparaissent plus dans le bundle** : `parentalGuidance`,
  `applockPerApp`, `inputBlock` (Général › Système › Sécurité). Une
  nouvelle application `com.webos.app.securitycenter` apparaît dans ce
  firmware : les verrouillages y ont probablement migré.
- **Libellés absents des traductions de l'app Réglages** (liste complète
  reproductible, cf. méthode ci-dessous) : sections Accessibilité (guide
  audio, zoom d'écran, contraste élevé, échelle de gris…), Sortie son
  (« Utiliser un haut-parleur sans fil / filaire… »), Application de la
  barre de son, Optimiseur de mémoire, Service AI (Recommandations d'AI),
  Sécurité (verrouillages), vitesse de suivi du pointeur. Plusieurs se
  retrouvent dans d'autres applications : `com.webos.app.accessibility`,
  `com.webos.app.quicksettings` (nouvelle), `com.webos.app.storagemanager`.

Ces constats indiquent une **réorganisation des menus** par webOS 11, pas
nécessairement une disparition : la structure affichée par la TV peut
avoir changé (écrans déportés dans d'autres applications).

**Proposition C.** Relever sur la TV les écrans Accessibilité, Sortie son,
Sécurité et Service AI (photos ou transcription), puis mettre à jour
`menu-tree/` écran par écran. Le guide d'utilisation webOS 25 n'est plus
une référence suffisante pour ces sections.

## Méthode (reproductible)

- `valid-settings.js` : diff direct entre les deux rootfs.
- Inventaire : `backend/scripts/explore_05_inventaire.py` (manifeste non
  signé ; la version logicielle n'est plus lisible, cf. § 1).
- App Réglages : `analyser_firmware.py` exécuté sur chaque bundle depuis
  une copie aux chemins adaptés (le script cible le 33.31.68), puis
  recherche, pour chaque entrée de `menu-tree/`, de sa clé API dans le
  bundle et de ses libellés dans `resources/fr/strings.json`
  (`mnt/lg/wee/ui_l10n/usr/palm/applications/com.palm.app.settings/`).
  L'analyse heuristique ne retrouve que 68 tables de choix contre 102 :
  écart probablement dû à la minification, non interprété.
  `croiser_firmware.py` n'a **pas** été exécuté (il réécrit `menu-tree/`).
