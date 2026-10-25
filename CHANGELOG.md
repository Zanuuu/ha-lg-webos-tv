# Changelog

## 2.2.0 — 2026-10-25

Panneau :

- **Téléviseur éteint ou injoignable** : bandeau explicite, dernières
  valeurs connues affichées, contrôles désactivés (ils restaient actifs et
  chaque écriture échouait).
- **Écritures** : « Envoi… » quand la confirmation du téléviseur tarde ; en
  cas d'échec, l'erreur est annoncée et le contrôle revient à la valeur du
  téléviseur au lieu de garder celle qui a été refusée.
- **Presets** : aperçu avant application (réglages modifiés avec leur
  valeur actuelle et la nouvelle, réglages déjà à la bonne valeur,
  réglages d'un autre mode d'image qui ne seront pas appliqués) ;
  confirmation avant suppression.
- **Historique** : valeurs et mode d'image affichés avec les libellés du
  menu ; liste mise à jour en direct ; « Revenir à cet instant » demande
  confirmation et indique le nombre de modifications annulées.
- **Navigation** : Presets et Historique dans la barre latérale du
  panneau ; bouton retour et touche Échap pour remonter d'un niveau ; sur
  mobile, bouton pour ouvrir le menu de Home Assistant ; tableaux en
  cartes sur petit écran.
- Chargement et échec du chargement du menu affichés (la page restait
  blanche), accessibilité (navigation, erreurs et envois annoncés).

Intégration : le flux temps réel du panneau signale les changements de
l'historique et des presets.

## 2.1.0 — 2026-10-25

- **Luminosité adaptative** intégrée (options de l'intégration) : remplace
  le blueprint « luminosité OLED selon la lumière ambiante », retiré.
  Supprimer l'automatisation créée depuis le blueprint avant d'activer la
  fonction, sinon les deux se disputent la luminosité.
  - La pause ne dépend plus que de la luminosité OLED : régler un autre
    réglage à la télécommande ne la lève plus.
  - Les changements faits depuis Home Assistant (entité, panneau, preset,
    retour arrière) mettent aussi en pause.
  - Réappliquée au changement d'entrée, pas seulement de mode d'image.
  - Contenus HDR / Dolby Vision et modes inconnus du menu laissés de côté.
  - Pause conservée au redémarrage de Home Assistant.
- Historique : origine « Luminosité adaptative ».
- L'ancienne app (add-on 1.x) est retirée du dépôt : le dépôt d'add-ons
  ne la propose plus. Ses scripts de diagnostic passent dans `outils/`.

## 2.0.0 — 2026-10-24

L'app (add-on) devient une **intégration Home Assistant**, distribuée par
HACS : les réglages du téléviseur deviennent des entités, synchronisées en
temps réel dans les deux sens.

- Entités générées depuis l'arborescence du menu (listes, curseurs,
  interrupteurs, capteurs) ; réglages d'usage courant activés d'emblée.
  L'état affiché est toujours celui confirmé par le téléviseur.
- Actions `lg_webos_tv.regler` (garde facultative sur le mode d'image) et
  `lg_webos_tv.appliquer_preset`, avec réponse ; un bouton par preset.
- Événement « Réglage modifié sur le téléviseur » pour les réglages faits à
  la télécommande ou par les réglages rapides (origine lue dans le champ
  `caller` des notifications du téléviseur).
- Blueprint « luminosité OLED selon la lumière ambiante ».
- Le menu Réglages, les presets et l'historique deviennent un panneau de la
  barre latérale ; thème clair ou sombre selon le profil Home Assistant ;
  origine de chaque modification dans l'historique.
- Configuration dans l'interface, avec découverte du téléviseur, appairage
  guidé, réauthentification si le téléviseur refuse la clé, changement
  d'adresse.
- Écriture confirmée par la notification du téléviseur (≈ 0,15 s au lieu
  de 0,5 s au moins) ; écritures rapprochées regroupées.
- Alerte dans Réparations si le téléviseur ferme l'écriture ; diagnostics
  téléchargeables.
- Migration depuis l'app : exporter les presets, les réimporter dans le
  panneau, désinstaller l'app.

## 1.3.0 — 2026-10-24

Nouvelle interface et ouverture du projet à la communauté.

- Interface refondue « écran OLED » : l'élément sélectionné s'allume comme
  sur le téléviseur, curseurs en barre de réglage avec la valeur en grand,
  titre du sous-menu courant, police Atkinson Hyperlegible Next.
- Thème clair ou sombre selon le système.
- Navigation au clavier visible partout (focus « allumé »).
- Espaces manquants corrigés dans plusieurs descriptions de réglages.
- L'adresse du téléviseur (`lg_tv_host`) n'a plus de valeur par défaut :
  elle est obligatoire pour une nouvelle installation. Les installations
  existantes conservent leur configuration.
- Libellés des options traduits (français, anglais) dans l'onglet
  Configuration.
- Documentation : section « Téléviseurs pris en charge » et « Dépannage »,
  licence MIT, notes de développement déplacées dans `docs/` à la racine du
  dépôt.

## 1.2.0 — 2026-10-24

Écriture des réglages rétablie sous le firmware 43.21.77 (webOS 11.2).

- Le téléviseur refuse toujours `setSystemSettings` aux clients non
  signés ; l'app écrit désormais par une alerte système dont l'action
  appelle le service de réglages (contournement de la communauté Home
  Assistant). Modification, presets et retour arrière fonctionnent de
  nouveau.
- Le manifeste d'appairage demande la permission `WRITE_NOTIFICATION_TOAST`
  (clé d'appairage existante conservée, pas de nouvelle demande à l'écran).
- Chaque écriture est confirmée par relecture : une valeur refusée par le
  téléviseur est signalée « non confirmée ».
- Mode consultation conservé si aucune voie d'écriture n'est accordée.

## 1.1.1 — 2026-09-24

- L'en-tête affiche « Appairage : acceptez la demande sur la TV » dès que
  la demande est à l'écran (première connexion, sans clé), et non plus
  « Connexion… » pendant les deux minutes d'attente.

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
