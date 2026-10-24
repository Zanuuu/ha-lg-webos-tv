# LG webOS TV pour Home Assistant

> **English** — A Home Assistant integration (HACS) for LG webOS TV
> settings: picture, sound and general settings become Home Assistant
> entities, synchronized in real time both ways (remote control → Home
> Assistant, Home Assistant → TV, every write confirmed by the TV). It adds
> actions for automations (set a setting only in a given picture mode,
> apply a preset), an event when a setting is changed with the remote, an
> ambient-light blueprint for OLED brightness, and a sidebar panel that
> mirrors the TV's Settings menu with presets and undo history. Setting
> names and the panel are in **French** (they mirror the French menu of the
> LG OLED G5, webOS 25). Works with webOS 11.2 firmwares, where LG blocks
> direct settings writes for unsigned clients.

Les réglages de votre téléviseur LG dans Home Assistant : des entités
synchronisées en temps réel dans les deux sens, des actions et un événement
pour les automatisations, et le menu Réglages du téléviseur, en français,
dans la barre latérale.

![Aperçu du panneau : réglages de luminosité](docs/images/apercu.png)

## Fonctionnalités

- **Entités** générées depuis l'arborescence du menu : curseurs (luminosité
  des pixels OLED, contraste…), listes (mode d'image, TruMotion, économie
  d'énergie…), interrupteurs, capteurs. Les réglages d'usage courant sont
  activés d'emblée, les autres créés désactivés.
- **Synchronisation bidirectionnelle** : un réglage fait à la télécommande
  met l'entité à jour aussitôt ; une commande depuis Home Assistant est
  appliquée puis confirmée par le téléviseur (l'état affiché est toujours
  celui du téléviseur, jamais une valeur supposée).
- **Automatisations** :
  - action `lg_webos_tv.regler`, avec une garde facultative sur le mode
    d'image ;
  - action `lg_webos_tv.appliquer_preset` et un bouton par preset ;
  - événement « Réglage modifié sur le téléviseur » quand un réglage est
    changé à la télécommande, pour qu'une automatisation cède la main ;
  - blueprint « luminosité OLED selon la lumière ambiante ».
- **Panneau « LG webOS TV »** dans la barre latérale : le menu Réglages
  complet (y compris les réglages que l'API n'expose pas, affichés « À
  régler sur la TV »), presets exportables en JSON, historique avec retour
  arrière.

## Téléviseurs pris en charge

L'arborescence est celle du **LG OLED G5 (webOS 25)**, testée sur les
firmwares 33.31.68 et 43.21.77 (webOS 11.2). Sur d'autres modèles LG webOS,
la plupart des réglages courants devraient fonctionner, mais l'arborescence
peut différer. Les retours sur d'autres modèles sont bienvenus.

Depuis webOS 11.2, le téléviseur réserve l'écriture directe des réglages aux
applications signées par LG : l'intégration écrit alors par le pont des
alertes système, et passe en **consultation** seulement si cette voie est
fermée (détails dans [`docs/incidents-ecriture.md`](docs/incidents-ecriture.md)).

## Installation

Prérequis : Home Assistant 2026.10 ou plus récent, [HACS](https://hacs.xyz),
téléviseur allumé et joignable, avec « LG Connect Apps » (contrôle réseau)
autorisé. Une adresse IP fixe (réservation DHCP) est recommandée.

1. HACS → menu ⋮ → Dépôts personnalisés → ajouter
   `https://github.com/Zanuuu/ha-lg-webos-tv`, catégorie **Intégration**.
2. Installer « LG webOS TV », puis redémarrer Home Assistant.
3. Paramètres → Appareils et services → Ajouter une intégration →
   « LG webOS TV » (le téléviseur peut aussi être découvert automatiquement).
4. Saisir l'adresse du téléviseur, puis accepter la demande d'appairage
   « Réglages TV (Home Assistant) » sur son écran (elle expire au bout de
   deux minutes).

Si le téléviseur refuse un jour la clé d'appairage (par exemple après une
mise à jour de son logiciel), Home Assistant propose de refaire l'appairage.
Changer d'adresse : menu ⋮ de l'intégration → Reconfigurer.

## Entités

Toutes appartiennent à l'appareil « LG webOS TV ». Les noms sont les
libellés du menu du téléviseur ; un libellé ambigu hors de son écran est
précédé de son menu (« Image — Mode Sélection », « Balance des blancs —
Méthode »).

| Type | Exemples | Remarque |
|---|---|---|
| Liste (`select`) | Mode Sélection (mode d'image), TruMotion, Fonction Économie d'énergie | options = libellés du menu |
| Curseur (`number`) | Luminosité des pixels OLED, Ajuster le contraste, Niveau noir | bornes du menu |
| Interrupteur (`switch`) | Protection des yeux, Compatibilité eARC, SIMPLINK | |
| Capteur (`sensor`) | Son — Mode Sélection, Pays | réglages en lecture seule |
| Bouton (`button`) | Appliquer le preset Soirée | un par preset |
| Événement (`event`) | Réglage modifié sur le téléviseur | `manuel` ou `autre_application` |
| Diagnostic | Connexion, Écriture des réglages impossible, Voie d'écriture | |

**Réglages d'image et mode d'image.** Le téléviseur garde une valeur par
mode d'image : une entité de réglage d'image montre et modifie la valeur du
mode **actif**, indiqué par son attribut `mode_image`. Changer de mode met
à jour toutes ces entités.

N'est exposé que ce dont la correspondance avec l'API est entièrement
connue ; le reste reste accessible dans le panneau.

## Automatisations

### Régler un réglage seulement dans un mode d'image

```yaml
action: lg_webos_tv.regler
data:
  entity_id: number.lg_webos_tv_luminosite_des_pixels_oled
  valeur: 60
  mode_image: cinema   # n'écrit que si le mode Cinéma est actif
response_variable: resultat
```

Sans `mode_image`, la valeur s'applique au mode actif. Avec, l'action ne
fait rien si un autre mode est actif et le dit dans sa réponse
(`ok: false`) sans faire échouer l'automatisation. `valeur` accepte un
nombre, un libellé du menu (`Cinéma`) ou une valeur API (`cinema`), on/off.

### Appliquer un preset

Créer le preset dans le panneau (« Presets & historique »), puis :

```yaml
action: lg_webos_tv.appliquer_preset
data:
  nom: Soirée
```

Le mode d'image du preset est appliqué en premier, puis les réglages
capturés pour ce mode. La réponse liste les réglages appliqués et ceux en
échec. Chaque preset a aussi son bouton.

### Céder la main à la télécommande

L'entité « Réglage modifié sur le téléviseur » émet un événement `manuel`
quand un réglage est changé à la télécommande ou par les réglages rapides
(une seule fois par réglage, à la fin d'un glissement de curseur), avec les
attributs `entree_id`, `libelle`, `cle`, `valeur` et `mode_image`. Les
changements faits par Home Assistant et les valeurs qui suivent un
changement de mode ne le déclenchent pas.

### Blueprint : luminosité OLED selon la lumière ambiante

[`blueprints/automation/lg_webos_tv/luminosite_ambiante.yaml`](blueprints/automation/lg_webos_tv/luminosite_ambiante.yaml)
— Paramètres → Automatisations → Blueprints → Importer, avec l'URL du
fichier sur le dépôt.

- échelle logarithmique entre une pièce sombre et une pièce lumineuse ;
- changement ignoré sous un écart minimal ;
- pause après un réglage à la télécommande, jusqu'à un délai choisi ou au
  prochain allumage du téléviseur ;
- réappliqué à chaque changement de mode d'image ; modes calibrés (FILMMAKER
  MODE, Expert) laissés de côté par défaut.

## Écriture sous webOS 11 et mode consultation

Chaque modification est confirmée par la notification du téléviseur (ou,
à défaut, une relecture) : une valeur refusée (hors plage) fait échouer
l'action avec un message. Si le téléviseur n'autorise plus aucune voie
d'écriture, l'intégration passe en consultation : les réglages restent
suivis en temps réel, une alerte apparaît dans Paramètres → Réparations, et
l'écriture se réactive d'elle-même si un logiciel ultérieur la rouvre.

Certains réglages sont volontairement en lecture seule : leur écriture
s'est révélée dangereuse lors des essais (le pays, notamment, réinitialise
en cascade d'autres réglages).

## Dépannage

- **Entités indisponibles** : téléviseur éteint ou injoignable ; vérifier
  l'adresse et « LG Connect Apps ». La connexion est retentée seule.
- **Écriture refusée** : la valeur sort de la plage acceptée dans le mode
  d'image actif.
- **Diagnostics** : menu ⋮ de l'intégration → Télécharger les diagnostics
  (adresse et clé masquées).

## Données

L'historique et les presets sont stockés dans `<config>/lg_webos_tv/`
(inclus dans les sauvegardes de Home Assistant) ; la clé d'appairage dans
l'entrée de configuration.

**Venir de l'app (add-on) LG webOS TV 1.x** : exporter les presets depuis
l'app (« Exporter »), installer l'intégration, les réimporter dans le
panneau, puis désinstaller l'app.

## Développement

Intégration Python dans `custom_components/lg_webos_tv/`, panneau React /
Vite dans `frontend/`, arborescence des menus en JSON déclaratif. Tests,
build du panneau, publication, notes techniques :
[`docs/developpement.md`](docs/developpement.md).

Les contributions sont bienvenues : signalements, corrections de
l'arborescence pour d'autres modèles, traductions.

## Licence et mentions

Code sous licence [MIT](LICENSE).

Projet communautaire, non affilié à LG Electronics ni approuvé par elle.
LG, webOS et le logo webOS sont des marques de leurs propriétaires
respectifs.
