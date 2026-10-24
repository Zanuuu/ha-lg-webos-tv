# Incidents constatés lors des premières écritures réelles (phase 5)

Le développement des presets (phase 5) a fourni la première occasion
d'écrire, en une seule séquence, la quasi-totalité des réglages accessibles
en écriture d'après l'inventaire de phase 1. Trois écarts ont été constatés
le 17/08/2026 contre le téléviseur réel (firmware 33.31.68) ; tous ont été
corrigés dans l'arbre des menus et, pour le premier, dans le code.

## 1. `option.country` déclenche une réinitialisation en cascade

**Constat.** L'application d'un preset complet a écrit `option.country`
avec sa valeur déjà active (« FRA » → « FRA », un no-op en apparence). Le
téléviseur a immédiatement basculé le mode d'image sur « Éco » et, à la
vérification, plusieurs autres réglages sans rapport avaient changé sans
qu'aucune écriture de notre part ne les ait touchés :

| Réglage | Avant | Après (inattendu) |
|---|---|---|
| `picture.pictureMode` | expert2 | eco |
| `picture.backlight` (mode expert2) | 80 | 60 |
| `sound.soundOutputDigital` | passThrough | auto |
| `option.audioGuidance` | off | on |
| `lock.parentalControl` | false | true |
| `picture.energySaving` | off | auto |

Ces changements sont apparus **après** que notre séquence d'écriture a
confirmé ces mêmes valeurs comme correctes (relecture immédiate conforme),
avec un délai d'environ une demi-seconde après l'écriture de `country` —
signature d'un traitement asynchrone côté téléviseur, cohérent avec une
réinitialisation partielle des réglages dépendants de la région/du pays
(un comportement de type « nouvelle configuration pays », semblable à un
sous-ensemble du parcours de première mise en service).

**Conséquence.** Toutes les valeurs touchées ont été restaurées manuellement
à leur état d'origine et vérifiées. Le mode d'image et les réglages du
téléviseur de l'utilisateur sont revenus à l'identique de leur état avant
ce test.

**Correction.** `general.systeme.lieu.pays` passe en `lecture_seule` dans
l'arbre des menus : ni l'interface ni les presets ne peuvent plus l'écrire.
Aucune méthode d'écriture sûre n'a été identifiée ; à revoir seulement si le
besoin se présente, avec une confirmation explicite dans l'interface le cas
échéant.

## 2. `picture.blackLevel` : format de valeur erroné

**Constat.** L'entrée « Plage vidéo » avait été rapprochée d'un choix simple
(auto/low/high), mais l'API renvoie et attend en réalité un **objet** avec
une valeur par norme de diffusion (`{"ntsc": "auto", "pal": "auto", …}`),
comme déjà noté dans `docs/inventaire-api.json` en phase 1. L'écriture d'une
valeur simple a été rejetée côté validation avant même d'atteindre le
téléviseur.

**Correction.** Passé en `lecture_seule` ; le bon format d'écriture (quelle
sous-clé cibler, sur quelle base) reste à établir.

## 3. `picture.whiteBalanceLuminance` : hors plage

**Constat.** Ce rapprochement était déjà marqué « présumé, à confirmer »
en phase 2. L'écriture de la valeur relevée (130) a été refusée par le
téléviseur : « The value is Out of range or interval ».

**Correction.** Passé en `lecture_seule` ; la clé ou la plage exacte reste à
établir.

## 4. Bug corrigé : conversion booléenne trop générale

**Constat.** `general.systeme.securite.activer-la-fonction`
(`lock.parentalControl`) est un interrupteur, catégorie pour laquelle le
backend convertit systématiquement les booléens en chaînes `"on"`/`"off"`
avant écriture (convention correcte pour la quasi-totalité des interrupteurs
de l'API webOS). Cette clé attend en réalité un **booléen JSON natif** : la
conversion automatique produisait `"off"`, systématiquement refusé
(« No matched extended item »). Confirmé en écrivant directement le booléen
natif, qui est accepté.

**Correction.** `backend/app/arbre.py` exempte désormais `parentalControl`
de la conversion automatique (`CLES_BOOLEENNES_NATIVES`). Aucune autre clé
de ce type n'a été identifiée à ce jour.

## 5. Firmware 43.21.77 (webOS 11.2) : appairage rejeté, écriture interdite

**Constat (24/09/2026).** Après la mise à jour du téléviseur en 43.21.77
(webOS 11.2.0, otaID inchangé `HE_DTV_W25O_AFABATAA`), l'app journalisait
`401 insufficient permissions (not registered)` sur chaque abonnement et
n'affichait plus aucune valeur.

**Cause.** La passerelle SSAP (`com.webos.service.secondscreen.gateway`)
embarque désormais une liste noire de signatures de manifeste
(`blacklist.json`, version 1.0.1 du 2026-01-27, actualisable depuis les
serveurs LG). Elle contient la signature `test-signing-cert` du manifeste
par défaut de bscpylgtv — celui que presque tous les clients
communautaires réutilisent. Réponse brute au `register`, avec ou sans clé :
`403 Pairing rejected: blacklisted certificate detected`. bscpylgtv 0.5.2
ignore cette erreur (il garde l'ancienne clé et déclare la connexion
établie), d'où les `401 not registered` en aval.

**Ce qui reste permis.** Un manifeste **non signé** est accepté : la
passerelle n'en retient que les permissions dont le niveau d'accès n'est pas
`SECURE` (`client-profile.js`, `loadUnsignedProperties`) :

| Méthode | Permission | Niveau | Manifeste non signé |
|---|---|---|---|
| `settings/getSystemSettings`, `getSystemSettingDesc`, abonnements | `READ_SETTINGS` | PROTECTED | accordée |
| `settings/setSystemSettings`, `resetSystemSettings` | `WRITE_SETTINGS` | SECURE | **refusée** (`401 insufficient permissions`) |
| `system.notifications/createAlert` (contournement des scripts HA) | `WRITE_NOTIFICATION_ALERT` | SECURE | refusée |
| `com.webos.service.update/getCurrentSWInformation` | `READ_UPDATE_INFO` | SECURE | refusée |

Vérifié sur le téléviseur (`backend/scripts/diag_enregistrement.py`) :
appairage accepté à l'écran, lecture de `picture` conforme, écriture
refusée. L'ancienne clé d'appairage reste valable avec le nouveau manifeste
(pas de nouvelle demande à l'écran). La demande d'appairage expire au bout
de 120 s (`403 cancelled`). Le `hello` SSAP ne reçoit plus de réponse.

**Correction.** L'app s'appaire avec son propre manifeste non signé
(`backend/app/manifeste-ssap.json`) et vérifie à chaque connexion :
l'enregistrement (sonde de lecture ; en cas de refus, nouvelle demande
d'appairage espacée de `APPAIRAGE_DELAI_S`) et la permission d'écriture
(sonde `setSystemSettings` sur une clé hors liste, rejetée par l'adaptateur
avant toute écriture si la permission est accordée). Sans permission,
l'app passe en **mode consultation** : lecture et temps réel, historique des
changements faits à la télécommande, capture de presets ; modification,
application de preset et retour arrière désactivés (API : 403). Si un
firmware ultérieur rouvre la permission, l'écriture se réactive seule.

Contournement écarté : réutiliser une autre signature LG non encore
blacklistée — révocation volontaire de LG, liste noire actualisable à
distance, solution sans garantie de durée.

## 6. Mode développeur webOS : testé, insuffisant pour l'écriture (24/09/2026)

**Objectif.** Après le passage en mode consultation (§ 5), vérifier sur le
téléviseur si le **mode développeur** de webOS ouvre une voie d'écriture des
réglages en contournant la passerelle SSAP, via un appel local au service de
réglages (`luna://com.webos.settingsservice/setSystemSettings`).

**Mise en place.** Compte LG, app *Developer Mode* activée, *Key Server* activé.
Accès SSH `prisoner@<TV>:9922` avec la clé privée servie par la TV
(`http://<TV>:9991/webos_rsa`, passphrase affichée dans l'app). OpenSSH récent
exige de réautoriser l'algorithme de clé d'hôte hérité
(`-o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa`).

**Constat (bloquant).** L'utilisateur `prisoner` est **confiné au bus luna
public** :

| Élément | Observation |
|---|---|
| `/usr/bin/luna-send` (bus privé) | `-rwx------ root root` → non exécutable par `prisoner` (« Permission denied ») |
| `/usr/bin/luna-send-pub` (bus public) | exécutable |
| `luna-send-pub … settingsservice/getSystemSettings` | `{"returnValue":false,"errorText":"Access denied"}` |

Le service de réglages est donc **inaccessible en lecture comme en écriture**
depuis le bus public accordé au mode dev. Aucun accès privilégié n'est ouvert
par le mode développeur, ni en SSH ni via une app/service qu'on y installerait
(même sandbox de bus).

**Conclusion.** Sur webOS 11.2, l'écriture des réglages exige soit un manifeste
**signé** par LG (niveau `SECURE`, cf. § 5 et l'analyse de
`com.webos.service.secondscreen.gateway` : `WRITE_SETTINGS` est `SECURE`, un
manifeste non signé perd cette permission, la liste noire ne bloque que deux
chaînes de signature précises), soit un **accès root** au bus privé. La
signature est écartée (forger une signature avec la clé de LG). Le root n'est
pas retenu sur ce téléviseur (récent, sous garantie ; dépend d'un exploit,
cassable par MAJ). **L'app reste en mode consultation**, comportement déjà en
place ; l'écriture se réactiverait seule si un accès privilégié devenait
disponible.
