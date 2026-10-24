# LG webOS TV

Le menu Réglages de votre téléviseur LG, en français, dans Home Assistant :
consultation et modification des réglages en temps réel, presets
exportables/importables, historique des modifications avec retour arrière.

## Téléviseurs pris en charge

L'arborescence reproduite est celle du **LG OLED G5 (webOS 25)**, testée
sur les firmwares 33.31.68 et 43.21.77 (webOS 11.2). Sur d'autres modèles
LG webOS, la connexion et la plupart des réglages courants (image, son)
devraient fonctionner, mais l'arborescence peut différer de celle de votre
téléviseur. Les réglages que l'API n'expose pas s'affichent « À régler sur
la TV ».

## Prérequis

- Téléviseur allumé et joignable sur le réseau local, avec
  « LG Connect Apps » / contrôle réseau autorisé. Une adresse IP fixe
  (réservation DHCP) est recommandée.
- Au premier démarrage, le téléviseur affiche une demande d'appairage
  « Réglages TV (Home Assistant) » : l'accepter avec la télécommande. Elle
  expire au bout de deux minutes ; l'app la représente ensuite toutes les
  trois minutes, et l'en-tête affiche « Appairage » pendant l'attente. La clé
  d'appairage est conservée dans le stockage persistant de l'app.

## Options

| Option | Description |
|---|---|
| `lg_tv_host` | Adresse IP du téléviseur sur le réseau local. **Obligatoire.** |
| `acces_lan` | Autorise l'accès direct **sans authentification Home Assistant**. À activer uniquement si vous mappez aussi le port 8000 dans la section Réseau. Par défaut, seul l'accès via l'interface Home Assistant (Ingress) est accepté. |

## Utilisation

L'interface apparaît dans la barre latérale de Home Assistant
(« LG webOS TV »). Elle reproduit l'arborescence du menu Réglages du
téléviseur : les valeurs affichées sont lues en temps réel, les modifications
sont appliquées immédiatement. L'interface suit le thème clair ou sombre du
système.

- Les réglages que l'API du téléviseur n'expose pas sont affichés à leur
  place normale avec la mention « À régler sur la TV ».
- Les réglages d'image sont propres au mode d'image actif (affiché dans
  l'en-tête) : toute lecture ou écriture ne concerne que le mode en cours.
- Le bouton « Presets & historique » donne accès à la capture et à la
  restauration d'états, et à l'annulation des modifications.

## Écriture sous webOS 11

Depuis webOS 11.2 (firmware 43.21.77 sur le G5), le téléviseur réserve
l'écriture directe des réglages aux clients signés par LG. L'app écrit alors
par une autre voie : une alerte système, fermée aussitôt, dont l'action
exécute le changement sur le téléviseur. Chaque modification est relue pour
confirmation ; une valeur refusée par le téléviseur (hors plage) apparaît
comme « non confirmée », sans message détaillé.

Une alerte peut s'afficher très brièvement à l'écran lors d'une
modification.

## Mode consultation

Si le téléviseur n'autorise aucune des deux voies d'écriture (par exemple
après une mise à jour qui fermerait celle des alertes), l'app le détecte à
chaque connexion et passe en mode consultation, signalé par un bandeau :

- les réglages restent affichés et suivis en temps réel ;
- l'historique enregistre toujours les changements faits à la
  télécommande, et les presets peuvent toujours être capturés ;
- la modification, l'application d'un preset et le retour arrière sont
  désactivés.

Si l'écriture redevient possible, l'app la réactive d'elle-même.

## Réglages en lecture seule

Certaines clés sont volontairement verrouillées en lecture seule car leur
écriture s'est révélée dangereuse ou incorrecte lors des essais sur un
téléviseur réel (notamment le pays, dont l'écriture déclenche une
réinitialisation en cascade de plusieurs réglages).

## Dépannage

- **« Déconnecté » en permanence** : vérifier que le téléviseur est allumé
  (ou en veille réseau active), que l'adresse `lg_tv_host` est la bonne et
  que « LG Connect Apps » est autorisé. L'app retente la connexion
  automatiquement.
- **« Appairage » en permanence** : la demande n'a pas été acceptée sur le
  téléviseur avant d'expirer. Elle réapparaît toutes les trois minutes :
  l'accepter avec la télécommande.
- **Bandeau de consultation** : le téléviseur refuse l'écriture (voir
  « Mode consultation »). Le journal de l'app indique la voie d'écriture
  détectée à chaque connexion.
- **Modification « non confirmée »** : le téléviseur a ignoré la valeur,
  généralement parce qu'elle sort de la plage acceptée pour ce réglage dans
  le mode d'image actif.

## Données persistantes

L'historique, les presets et la clé d'appairage sont stockés dans le
répertoire `/data` de l'app : ils survivent aux redémarrages et aux mises à
jour, et sont supprimés à la désinstallation.
