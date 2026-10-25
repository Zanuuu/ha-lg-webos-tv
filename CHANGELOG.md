# Changelog

## 2.8.0 — 2026-10-25

Luminosité adaptative : mise en route guidée et point intermédiaire de la
courbe (lot 4 de `docs/etude-luminosite-adaptative.md`).

- **Mise en route guidée** dans le panneau, à la première activation puis
  relançable : capteur (ceux de la pièce du téléviseur d'abord, puis ceux
  qui ont publié dans l'heure, avec valeur, âge de la mesure et profil
  pressenti), emplacement, vérifications (téléviseur, économie d'énergie
  et mode Éco, mode laissé de côté, capteur qui répond), point d'ancrage,
  activation.
- **Point d'ancrage** : la luminosité réglée pendant la mise en route
  (curseur du panneau ou télécommande, par la file d'écriture, historisée)
  et le lux lissé du moment calent la courbe, décalée en ln(lux), pente
  conservée. Une valeur hors des bornes de luminosité les élargit ; la
  partie hors de portée du capteur (sous 1 lx, au-delà de 100 000 lx) est
  coupée. Pendant la mise en route, la fonction n'écrit pas, ne se met pas
  en pause et ne compte pas ce réglage comme une correction (état
  `mise_en_route`).
- **Deuxième point**, le soir dans le noir (invitation sur la page) : dans
  une lumière au moins 4 fois plus faible, il cale aussi la pente ; un
  point pris dans une lumière voisine remplace le précédent, un point
  contradictoire (moins de lumière, luminosité plus haute) le fait
  oublier. Points d'ancrage en losanges sur la courbe, oubliés si la
  courbe est retouchée.
- **Point intermédiaire** facultatif de la courbe (option
  `point_intermediaire`), interpolation par morceaux sur ln(lux), courbe
  monotone : formulaire des options (« Pièce intermédiaire »), troisième
  poignée de la courbe du panneau, ajout et retrait.
- Lux de la courbe au dixième (sous 100 lx) dans le formulaire et le
  panneau.
- Commandes websocket `lg_webos_tv/luminosite_adaptative/ancrer` et
  `…/mise_en_route` (abonnement, administrateurs) ; configuration
  enrichie (pièce, profil et âge de la mesure de chaque capteur, pièce du
  téléviseur).
- Installations existantes inchangées : sans point intermédiaire ni
  ancrage, la courbe donne les mêmes valeurs qu'en 2.7.0, sans migration.
- Développement : `courbe.py` (logique pure) ; vecteurs de test partagés
  entre pytest et le panneau (`tests/vecteurs_courbe.json`,
  `cd frontend && npm test`).

## 2.7.0 — 2026-10-25

Luminosité adaptative : santé de l'installation (lot 3 de
`docs/etude-luminosite-adaptative.md`).

- **Statistiques journalières** calculées par la fonction elle-même (sans
  dépendre du recorder) : temps téléviseur allumé et fonction active,
  fréquence et résolution des mesures, lumière habituelle, transitions,
  reprises en main (avec la correction faite, par ambiance), écritures non
  confirmées, allers-retours, effet de l'écran sur le capteur. Conservées
  30 jours dans `<config>/lg_webos_tv/historique.sqlite` (table
  `stats_luminosite`, une ligne par jour et par capteur), enregistrées
  toutes les 5 minutes et à l'arrêt, relues au démarrage.
- **Diagnostics**, chacun avec ce qui ne va pas, pourquoi, le chiffre qui
  le justifie et quoi faire : capteur trop lent, capteur trop grossier en
  pièce sombre, plafond du capteur, 0 lx dans le noir, courbe calée de
  travers, allers-retours, rétroaction de l'écran (mesurée à l'allumage et
  à l'extinction du téléviseur, médiane d'au moins 5 événements, et par la
  réponse aux transitions pour un capteur rapide ; emplacement « face à
  l'écran » signalé d'office), corrections fréquentes, écritures refusées,
  capteur et téléviseur dans deux pièces différentes, en plus du conflit
  avec l'économie d'énergie et du capteur figé.
- **Propositions appliquées d'un clic** : « Pièce lumineuse » au 90ᵉ
  centile du lux observé quand la luminosité reste au maximum plus de
  80 % du temps, « Pièce sombre » relevée pour un capteur trop grossier,
  seuils et lissage relevés contre les allers-retours.
- Panneau : section **Santé de l'installation** sur la page Luminosité
  adaptative (diagnostics, contrôles passés et en observation,
  statistiques des 7 derniers jours, jour par jour) ; le conflit avec
  l'économie d'énergie et le capteur figé y sont regroupés. Journal :
  mesures de l'effet de l'écran et épisodes d'allers-retours.
- Commande websocket `lg_webos_tv/luminosite_adaptative/sante`
  (administrateurs) ; la santé suit aussi le flux de la page.
- Diagnostics téléchargeables : état, réglages, statistiques et
  diagnostics de la fonction, sans l'identifiant du capteur ni les noms de
  pièce.
- Aucune nouvelle Réparation : seuls le conflit et le capteur figé, qui
  empêchent la fonction de marcher, en ouvrent une.

## 2.6.0 — 2026-10-25

Luminosité adaptative : transitions douces (lot 2 de
`docs/etude-luminosite-adaptative.md`).

**Changements de comportement** :

- Une transition se fait en **rampe** : la luminosité change point par
  point (4 points par seconde par défaut : de 40 à 100 en 15 s), chaque
  pas confirmé par le téléviseur avant le suivant, et suit le lux lissé
  jusqu'à la cible exacte (en 2.5.0 : 3 à 5 écritures espacées de 5 s,
  qui pouvaient s'arrêter 2 points avant la cible). En descente, la fin de
  la transition suit le lissage (≈ 1 min pour une pièce qui s'assombrit
  franchement), par pas d'un point.
- **Une seule entrée d'historique par transition** (de la valeur de départ
  à celle d'arrivée) au lieu d'une par écriture ; son retour arrière
  restaure la valeur de départ. Une seule ligne au journal de la fonction.
- Les mesures du capteur sont mises de côté **pendant toute la
  transition**, puis 5 s après (20 s pour un capteur face à l'écran).
- **Écart minimal abaissé de 3 à 2.** Une installation qui avait 3 (la
  valeur par défaut, enregistrée par le formulaire même sans y toucher)
  passe au nouveau défaut ; toute autre valeur est conservée. Le champ est
  désormais facultatif : vide, il suit la valeur par défaut.

Détails :

- Une transition s'arrête sur une reprise en main (télécommande, Home
  Assistant, panneau, preset), un changement de mode d'image ou d'entrée,
  ou une écriture non confirmée ; elle ne remplace jamais une écriture de
  l'utilisateur en attente dans la file.
- Réglages avancés : **taille des pas** (1 point par défaut) et **vitesse**
  (4 points par seconde par défaut), dans le formulaire des options et
  dans le panneau.
- Panneau : transition en cours (départ, cible, progression d'après la
  valeur du téléviseur) sur la page et sur la ligne des pixels OLED ;
  journal « Luminosité 60 → 100 en 15 s (60 pas) » avec la cause d'une
  interruption.
- Attribut `rampe` de l'état de la fonction.
- Téléviseur : la notification tardive d'une de nos écritures reste
  reconnue même après une écriture plus récente de la même clé (elle
  aurait pu, pendant une rampe, être prise pour une autre application et
  mettre la fonction en pause).
- Script `outils/scripts/mesure_rampe.py` pour l'essai réel (débit,
  latence par pas, écritures non confirmées, déconnexions).

## 2.5.0 — 2026-10-25

Luminosité adaptative : signal fiable et cohabitation avec le téléviseur
(lot 1 de `docs/etude-luminosite-adaptative.md`).

**Changement de comportement** : la fonction réagit à un signal lissé et
non plus à chaque mesure brute. Une lampe qu'on allume est suivie en
quelques pas espacés de 5 s (au lieu d'un saut une seconde après), un saut
de lumière de plus d'un facteur 4 attend 8 s de confirmation, et une
petite variation (+10 % / −20 % depuis la dernière application) ne change
plus rien. Chaque pas reste une écriture distincte dans l'historique.

- **Filtre** exponentiel sur le logarithme du lux, défini en temps (capteurs
  à 1 s comme à 5 min), plus rapide à la hausse (5 s) qu'à la baisse
  (15 s), réévalué entre deux mesures ; **hystérésis** relative ;
  **confirmation des sauts** isolés ; **mise de côté des mesures** 5 s après
  chaque écriture de la fonction (20 s pour un capteur face à l'écran) ; une
  rafale de mesures ne repousse plus l'application (défaut de la 2.4.0 avec
  un capteur à moins d'une seconde).
- **Profil du capteur** (rapide, périodique, sur variation, lent) d'après
  son intégration puis la fréquence observée de ses mesures ; il n'ajuste
  que les constantes du filtre.
- **Capteur figé** (silence de plus de 3 fois l'intervalle habituel, au
  moins 2 h, téléviseur allumé) : état `capteur_fige`, luminosité
  conservée, Réparation.
- **Conflit avec le téléviseur** : « Fonction Économie d'énergie » autre que
  Désactivé, ou mode d'image Éco → état `conflit_economie_energie`, aucune
  écriture, Réparation ; pour l'économie d'énergie, « Corriger » (ou le
  bouton de la page) la règle sur Désactivé par la file d'écriture.
- **Emplacement du capteur** (A à G) : option, schéma de la pièce et
  conseils dans le panneau, emplacements déconseillés signalés.
- Formulaire des options : emplacement ; **réglages avancés** repliés
  (écart minimal, lissage, seuils, confirmation, mise de côté), vides par
  défaut pour suivre le profil. Options de la 2.4.0 reprises sans
  migration.
- Panneau : lux lissé et dernière mesure, profil, conflit avec son bouton,
  capteur figé, aide sur « Lumière ambiante du MODE FILMMAKER » et
  « Paramètres de luminosité AI » (illisibles par l'API), nouveaux
  événements du journal.
- Commande websocket `luminosite_adaptative/desactiver_economie_energie` ;
  attributs `lux_filtre`, `conflit`, `profil`, `emplacement` de l'état.

## 2.4.0 — 2026-10-25

Panneau : page **Luminosité adaptative** dans la barre latérale (lien
« Détails » depuis la ligne des pixels OLED).

- **État en direct** : lux mesuré, luminosité calculée et luminosité du
  téléviseur, mode d'image (et s'il est laissé de côté), interrupteur,
  dernière erreur d'écriture. En pause : sa **cause** (réglage sur le
  téléviseur, depuis Home Assistant, ce panneau, un preset, un retour
  arrière) et son heure de fin, bouton Reprendre ; sinon bouton
  **Pause 1 h**, qui ne touche pas à la luminosité.
- **Courbe** lux → luminosité sur échelle logarithmique, point « maintenant »
  en direct ; ses deux points se déplacent à la souris, au doigt ou au
  clavier, ou par leurs champs.
- **Réglages** de la fonction (capteur, durée de pause, écart minimal,
  modes laissés de côté) en brouillon, avec Enregistrer / Annuler.
  Appliqués sans recharger l'intégration, sauf pour créer la fonction
  (mise en route depuis la page) ou la retirer.
- **Journal** des 50 derniers événements de la fonction (en mémoire).
- La vue ouverte est retenue si la page est actualisée.

Intégration :

- Cause de la pause retenue (conservée au redémarrage, attribut
  `cause_pause` de l'état), pause manuelle, reconfiguration à chaud
  (changement de capteur compris), journal en mémoire.
- Commandes websocket `lg_webos_tv/luminosite_adaptative/` : `activer`,
  `pause`, `configuration`, `configurer`, `suivre` (abonnement : état
  complet avec le lux, et journal, seulement pendant que la page est
  ouverte).
- Validation des options partagée entre le formulaire et le panneau.

## 2.3.0 — 2026-10-25

Panneau :

- **Luminosité adaptative** : son état s'affiche sur la ligne « Luminosité
  des pixels OLED » (active avec la valeur visée, en pause jusqu'à
  l'heure de reprise, mode d'image laissé de côté, capteur indisponible) ;
  bouton **Reprendre** pendant une pause. Le passage en pause qui suit un
  réglage du curseur est visible et annoncé.
- **Recherche d'un réglage** au-dessus de la barre latérale (touche `/`) :
  sans tenir compte des accents ni de la casse, sur le libellé, le chemin
  dans le menu, les choix proposés et la description. Les résultats se
  règlent sur place ; leur chemin ouvre le menu à cet endroit, ligne mise
  en évidence. Échap vide la recherche.
- Capture du README mise à jour.

Intégration : l'état de la luminosité adaptative est transmis au panneau
(instantané et flux temps réel, seulement quand il change) ; nouvelle
commande websocket `lg_webos_tv/luminosite_adaptative/reprendre`.

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
