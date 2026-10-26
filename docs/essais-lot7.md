# Essais du lot 7 : gamma, niveau du noir, portée des réglages, lumière à l'œil

Modes opératoires des essais P5 bis, P9, P10 et P11 de
`docs/etude-luminosite-adaptative.md` (§ 6). P5 bis, P9 et P10 conditionnent
le lot 7b (gamma selon l'ambiance, niveau noir compensé, pilotes par
réglage) ; P11 accompagne l'essai réel de la Soirée (lot 7a, 2.11.0).

Les relevés se consignent dans la section **Résultats**, en fin de
document, sans donnée personnelle : ni adresse, ni série du téléviseur, ni
nom de pièce ou d'entité. Les relevés bruts des scripts restent dans
`outils/data/mesures/` (hors git).

## Préparation (une fois)

- Venv racine avec les dépendances des scripts :
  `uv pip install --python .venv -r requirements-dev.txt -r outils/requirements.txt`.
- Clé d'appairage de développement dans `outils/data/bscpylgtv.sqlite` (comme
  pour `mesure_rampe.py`).
- **Dans Home Assistant : désactiver la luminosité adaptative** (sa Soirée
  avec), pour qu'elle n'écrive pas pendant la séance et ne prenne pas les
  écritures des scripts pour des réglages manuels.
- Téléviseur allumé, sur une source SDR (lecteur, clé USB, application).
- Noter avant de commencer le mode d'image, le gamma et le niveau du noir
  du mode Standard : les scripts restaurent ce qu'ils changent, P9 se fait à
  la main.
- Un script interrompu par Ctrl-C pendant une question attend encore
  Entrée avant de restaurer et de s'arrêter.

Durée totale : environ 1 h (P5 bis 10 min, P10 15 min, P9 30 min).

## P5 bis — Correspondance des valeurs de gamma (10 min)

But : savoir quel libellé du menu (« 2.2 », « BT.1886 », peut-être d'autres)
correspond à chaque valeur API (`low`, `medium`, `high1`, `high2`). Point
ouvert de `menu_tree/image.json` (choix « à vérifier ») et prérequis de R13.

1. Sur le téléviseur, ouvrir Image › Paramètres avancés › Luminosité, sans
   entrer dans Gamma.
2. Lancer :
   `LG_TV_HOST=<ip> .venv/bin/python outils/scripts/essai_gamma.py`
   (modes Standard puis Expert (pièce lumineuse, journée) ; `--modes normal
   expert1 expert2` pour ajouter Expert (pièce sombre, nuit),
   `--avec-medium-having-level` pour la cinquième valeur documentée par le
   téléviseur).
3. À chaque écriture, lire la valeur affichée sur la ligne Gamma (rouvrir le
   menu s'il s'est fermé) et la taper telle quelle ; Entrée seule si rien ne
   change.
4. Coller le tableau Markdown affiché à la fin dans Résultats › P5 bis.

Ce qui en sort : la table valeur API → libellé, par mode, et les valeurs
refusées. Si deux valeurs donnent le même libellé, l'indiquer : le menu peut
regrouper des valeurs.

## P10 — Réglages propres au mode ou communs (15 min)

But : pour Réduire la lumière bleue (`eyeComfortMode`), Protection des yeux
(`motionEyeCare`), Luminosité maximale (`peakBrightness`), Contraste
dynamique automatique (`dynamicContrast`), Gamma (`gamma`), Mappage des
tons dynamiques (`hdrDynamicToneMapping`) et Fonction Économie d'énergie
(`energySaving`, rangé avec l'image dans l'API mais présenté dans Général),
savoir si la valeur vaut pour le mode d'image actif seulement ou pour tous. Confirme (ou infirme) la
correction de `arbre.mode_dependant` faite en 2.11.0 pour Réduire la lumière
bleue, et décide de la garde de mode des pilotes du lot 7b.

1. Portée :
   `LG_TV_HOST=<ip> .venv/bin/python outils/scripts/essai_portee.py`
   (Standard et Cinéma par défaut ; `--mode-a`, `--mode-b` pour d'autres).
   Le script lit chaque réglage dans les deux modes ; à valeurs égales, il en
   écrit une autre dans le premier et relit dans le second. Il remet chaque
   valeur aussitôt. Rien à faire pendant ce temps.
   Mappage des tons dynamiques ne vaut qu'en HDR : un refus en SDR est
   attendu ; pour le trancher, relancer avec `--cles hdrDynamicToneMapping`
   sur une source HDR, en donnant deux modes HDR (valeurs API vues dans les
   notifications, par exemple avec `diag_origine.py --sans-rafale`).
2. Réduire la lumière bleue en FILMMAKER MODE :
   `... essai_portee.py --cles --filmmaker`. Le script l'active en Standard,
   passe en FILMMAKER MODE, relit la valeur, puis demande ce que montre le
   menu (activé, désactivé, grisé, absent) et si l'image paraît plus chaude.
   Pour comparer la teinte, basculer vous-même le réglage dans le menu, puis
   le remettre comme il était avant de répondre.
3. Protection des yeux et luminosité notifiée :
   `... essai_portee.py --cles --protection-yeux 5`. Le script active
   Protection des yeux et affiche, pendant 5 minutes, chaque notification de
   `backlight` avec son `caller`. Lancer un contenu qui alterne scènes
   claires et sombres. Aucune notification : la fonction agit en interne,
   sans toucher à la valeur que pilote la luminosité adaptative.
4. Coller le tableau final dans Résultats › P10.

Ce qui en sort : la carte « propre au mode / commun », le comportement de la
lumière bleue en FILMMAKER, et si Protection des yeux modifie la valeur
notifiée (elle mettrait alors la luminosité adaptative en pause à tort).

## P9 — Niveau du noir sous plusieurs éclairages (30 min, sans script)

But : savoir si le niveau du noir réglé à la mire PLUGE (procédure de
BT.814) change avec l'éclairage de la pièce. R16 (niveau noir compensé)
n'est fait que si l'écart atteint 2 points entre pièce noire et pièce
claire.

Matériel : une mire PLUGE (« black level » / PLUGE d'un disque ou d'un
fichier de mires d'étalonnage, en SDR plage limitée), affichée depuis la
source habituelle ; le capteur de la luminosité adaptative en place A (à
côté de l'écran, tourné vers la pièce).

Pour chaque éclairage, **pièce noire**, **lampe seule** (éclairage du soir
habituel), **plein jour** (volets ouverts) :

1. Mode d'image Standard, Luminosité des pixels OLED à la valeur habituelle
   de cet éclairage (celle de la luminosité adaptative, ou la vôtre) ; la
   noter.
2. Attendre une minute que l'œil s'adapte, depuis la place habituelle.
3. Image › Paramètres avancés › Luminosité › Niveau noir : partir d'une
   valeur nettement trop haute (bandes toutes visibles), descendre jusqu'à
   ce que la bande la plus sombre disparaisse **tout juste** alors que la
   plus claire reste visible.
4. Noter : éclairage, lux du capteur (état de l'entité dans Home Assistant,
   ou « Lux filtré »), luminosité OLED, niveau du noir retenu.
5. Recommencer une fois en partant d'une valeur trop basse (bandes toutes
   noyées), et noter les deux valeurs : leur écart dit la précision du
   réglage.

À la fin, remettre le niveau du noir noté pendant la préparation.

Lecture : si la différence entre pièce noire et plein jour ne dépasse pas
la différence entre vos deux réglages d'un même éclairage, ou 1 point, R16
est abandonné. Dès 2 points, R16 se justifie, calé sur vos 3 points.

## P11 — Lumière reçue à l'œil, Soirée (essai réel du lot 7a)

But : calibrer la baisse de la Soirée (20 % par défaut) sur la lumière que
l'écran envoie à l'œil le soir. Le consensus de Brown et al. (2022) vise au
plus 10 lx d'éclairement mélanopique à l'œil dans les 3 h avant le coucher ;
un luxmètre mesure l'éclairement photopique, et l'équivalence entre les deux
pour un blanc D65 est une approximation (à vérifier) : on compare des
ordres de grandeur.

Matériel : un luxmètre, ou à défaut une application de téléphone (mesures
relatives seulement).

1. Pièce noire, contenu habituel du soir (pas une mire), place habituelle.
2. Luxmètre à hauteur des yeux, tourné vers l'écran.
3. Pour Luminosité des pixels OLED à 40, 70 et 100 : relever l'éclairement
   (moyenne à l'œil sur 20 à 30 s, le contenu varie), Réduire la lumière
   bleue désactivé puis activé.
4. Puis avec la Soirée active (baisse de 20 %) : noter la cible affichée par
   le panneau et l'éclairement relevé.

Lecture : si la baisse de 20 % laisse l'éclairement nettement au-dessus de
10 lx dans le noir, une baisse plus forte se discute ; si l'écran est déjà
en dessous sans baisse, la Soirée sert surtout en pièce éclairée.

---

## Résultats

### P5 bis — gamma

| Mode | Valeur API | Confirmée | Relue | Libellé du menu |
|---|---|---|---|---|
| | | | | |

### P10 — portée des réglages

| Réglage | Mode A | Mode B | Valeur A | Valeur B | Essayée en A | Relue en B | Verdict |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

Réduire la lumière bleue en FILMMAKER MODE : …

Protection des yeux et `backlight` notifié : …

### P9 — niveau du noir à la mire PLUGE

| Éclairage | Lux du capteur | Luminosité OLED | Niveau noir (par le haut) | Niveau noir (par le bas) |
|---|---|---|---|---|
| Pièce noire | | | | |
| Lampe seule | | | | |
| Plein jour | | | | |

### P11 — lumière à l'œil

| Luminosité OLED | Lumière bleue | Éclairement à l'œil (lx) |
|---|---|---|
| 40 | désactivée | |
| 40 | activée | |
| 70 | désactivée | |
| 70 | activée | |
| 100 | désactivée | |
| 100 | activée | |
| Soirée (cible : …) | selon l'option | |
