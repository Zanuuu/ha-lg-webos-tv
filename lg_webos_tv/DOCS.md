# LG webOS TV

Réplique en français du menu Réglages d'un LG OLED 65 G5 (webOS 25) :
consultation et modification des réglages du téléviseur, presets
exportables/importables, historique des modifications avec retour arrière.
Compatible webOS 11 (voir « Écriture sous webOS 11 »).

## Prérequis

- Téléviseur LG G5 (webOS 25) allumé et joignable sur le réseau local, avec
  « LG Connect Apps » / contrôle réseau autorisé.
- Au premier démarrage, le téléviseur affiche une demande d'appairage
  « Réglages TV (Home Assistant) » : l'accepter avec la télécommande (elle
  expire au bout de deux minutes ; l'app la représente ensuite toutes les
  trois minutes, l'en-tête affiche « Appairage »). La clé d'appairage est
  conservée dans le stockage persistant de l'app.

## Écriture sous webOS 11

Depuis le firmware 43.21.77 (webOS 11.2), le téléviseur réserve l'écriture
directe des réglages aux clients signés par LG. L'app écrit alors par une
autre voie : une alerte système, fermée aussitôt, dont l'action exécute le
changement sur le téléviseur. Chaque modification est relue pour
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

## Options

| Option | Description |
|---|---|
| `lg_tv_host` | Adresse IP du téléviseur sur le réseau local. |
| `acces_lan` | Autorise l'accès direct **sans authentification Home Assistant**. À activer uniquement si vous mappez aussi le port 8000 dans l'onglet réseau. Par défaut, seul l'accès via l'interface Home Assistant (Ingress) est accepté. |

## Utilisation

L'interface apparaît dans la barre latérale de Home Assistant
(« LG webOS TV »). Elle reproduit l'arborescence du menu Réglages du
téléviseur : les valeurs affichées sont lues en temps réel, les modifications
sont appliquées immédiatement.

- Les réglages que l'API du téléviseur n'expose pas sont affichés à leur
  place normale avec la mention « À régler sur la TV ».
- Les réglages d'image sont propres au mode d'image actif (affiché dans
  l'en-tête) : toute lecture ou écriture ne concerne que le mode en cours.
- Le bouton « Presets & historique » donne accès à la capture/restauration
  d'états et à l'annulation des modifications.

## Réglages en lecture seule

Certaines clés sont volontairement verrouillées en lecture seule car leur
écriture s'est révélée dangereuse ou incorrecte lors des essais sur le
téléviseur réel (notamment le pays, dont l'écriture déclenche une
réinitialisation en cascade de plusieurs réglages). Détails dans
`docs/incidents-ecriture.md` du dépôt du projet.

## Données persistantes

L'historique, les presets et la clé d'appairage TV sont stockés dans le
répertoire `/data` de l'app : ils survivent aux redémarrages et mises à
jour, et sont supprimés à la désinstallation.
