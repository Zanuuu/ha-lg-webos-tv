# Étude : optimiser la luminosité adaptative et guider l'utilisateur

Étude du 25/10/2026 (révisée le même jour : textes ITU lus, ensemble des réglages du téléviseur), sur la base de la version 2.4.0
(`custom_components/lg_webos_tv/luminosite_adaptative.py`). C'est une
étude : aucune modification du code. Elle sert à décider de la suite avant
toute implémentation.

**Conventions.**

- **[Observé]** : lu dans le code, le firmware 33.31.68, le guide webOS 25
  ou les relevés déjà consignés dans `docs/`.
- **[Source]** : publication ou documentation citée (liste en fin de
  document).
- **[Supposé]** : raisonnement ou ordre de grandeur que je n'ai pas mesuré.
- **À vérifier** : fait inconnu, à trancher par une mesure (§ 6) ou par
  vous.
- Confiance des recommandations : **élevée**, **moyenne**, **faible**.

Les valeurs numériques proposées (constantes de temps, seuils) sont des
**points de départ** tirés des sources ou d'un calcul. Elles sont à
confirmer par le protocole d'essai, pas à graver telles quelles.

---

## 1. Synthèse

### 1.1 Recommandations classées

Classement par rapport gain/effort, risque pris en compte. « Gain » se
mesure pour l'ensemble des utilisateurs HACS, pas pour une installation
particulière.

| # | Recommandation | Gain | Effort | Risque | Confiance |
|---|---|---|---|---|---|
| R1 | **Robustesse du signal** : filtre exponentiel sur log(lux), asymétrique (montée plus rapide que descente), à pas de temps irrégulier ; hystérésis relative sur le lux ; confirmation des sauts isolés ; capteur figé détecté ; correction du rebond qui affame l'application quand le capteur publie plus d'une fois par seconde | Élevé | Faible à moyen | Faible | Élevée |
| R2 | **Cohabitation avec les fonctions natives** : détecter « Fonction Économie d'énergie » ≠ Désactivé et le mode Éco (lisibles), avertir et proposer de les désactiver ; avertir par texte pour « Paramètres de luminosité AI » et « Lumière ambiante du MODE FILMMAKER » (illisibles par l'API) | Élevé | Faible | Faible | Élevée (détection) / Moyenne (effet réel, à mesurer) |
| R3 | **Question « Où est votre capteur ? »** et guide de placement : textes, schéma, réglages adaptés (garde contre la rétroaction) | Élevé | Faible | Faible | Élevée |
| R4 | **Rampes** : passer d'une valeur à l'autre par pas, avec une entrée d'historique par rampe et non par pas | Élevé (confort visible) | Moyen | Moyen (débit soutenu, historique) | Moyenne, à confirmer par mesure |
| R5 | **Diagnostics** : cadence et résolution du capteur, saturation, capteur figé, courbe calée de travers (valeur collée à une borne), allers-retours, pauses fréquentes, rétroaction ; page « Santé de l'installation » avec la correction à faire | Élevé | Moyen | Faible | Élevée (détections simples) / Moyenne (rétroaction) |
| R6 | **Mise en route guidée** : capteurs de la pièce du téléviseur proposés en premier, profil détecté, placement, vérifications, puis un **point d'ancrage** (« réglez la luminosité qui vous convient maintenant ») qui cale la courbe | Élevé | Moyen | Faible | Élevée |
| R7 | **Reprise en main améliorée** : la pause se lève aussi quand l'ambiance change nettement (lux ×2 ou ÷2 depuis le réglage manuel), pas seulement au bout du délai | Moyen | Faible | Faible | Moyenne |
| R8 | **Apprentissage par suggestions** : conserver les corrections manuelles (lux, valeur gardée, mode) et proposer un ajustement de la courbe que l'utilisateur accepte ou non ; pas d'apprentissage silencieux | Moyen à élevé | Moyen | Faible (validé par l'utilisateur) | Moyenne |
| R9 | **Courbe à 3 points** (sombre, intermédiaire, lumineux) au lieu de 2, monotone, toujours sur log(lux) | Moyen | Moyen (interface) | Faible | Moyenne |
| R10 | **Rétroaction de l'écran** : la mesurer (allumage et extinction du téléviseur, réponse aux écritures), geler la mesure juste après une écriture, l'expliquer ; compensation numérique seulement en option, plus tard | Moyen (élevé pour un capteur face à l'écran) | Moyen à élevé | Moyen (estimation fausse) | Moyenne |
| R11 | **Décalage pilotable** : une entité « Décalage de la luminosité adaptative » (−30 à +30), que les automatisations de l'utilisateur règlent selon l'heure, la présence, l'application… au lieu d'intégrer chaque contexte | Moyen | Faible | Faible | Moyenne |
| R12 | **Capteur de secours**, puis éventuellement fusion de plusieurs capteurs (médiane, moyenne géométrique pondérée) | Faible à moyen | Moyen | Faible | Moyenne |
| R13 | **Gamma selon l'ambiance** (bascule BT.1886 → 2.2 seulement au-delà de 200 à 300 lx), en option désactivée par défaut, une fois la correspondance API des valeurs gamma établie ; justifié par BT.2100, BT.2390 et BT.2408, mais avec une amplitude normative inférieure au cran du menu | Faible à moyen | Moyen | Moyen | Faible à moyenne |
| R14a | **Entités « Lux filtré » et « Ambiance »** (sombre, intermédiaire, claire, avec hystérésis) pour les automatisations de l'utilisateur | Moyen | Faible | Faible | Élevée |
| R14b | **Ambiances intégrées** : valeur par ambiance pour Luminosité maximale, Contraste dynamique, Mappage des tons dynamiques (HDR), Protection des yeux, gamma ; reprise en main par réglage ; valeur de base restaurée | Moyen | Élevé | Moyen | Faible (aucune valeur par défaut fondée, sauf gamma) |
| R15 | **Soirée** : à partir d'une heure ou d'une entité, plafond de luminosité abaissé et, en option, « Réduire la lumière bleue » ; d'après le consensus de Brown et al. (2022), sans promesse de santé | Moyen | Moyen | Faible | Moyenne (principe), faible (bénéfice sur le sommeil) |
| R16 | **Niveau noir compensé** en pièce claire, calé par l'utilisateur sur une mire PLUGE à 2 ou 3 éclairages (procédure de BT.814) | Faible à moyen | Moyen | Moyen | Moyenne (principe normatif), faible (amplitude, à mesurer) |
| — | Écartés : contraste (BT.2022 déconseille d'adapter le blanc par le signal), température de couleur, profondeur de couleur et teinte, réglages d'étalonnage, netteté et traitements du signal, TruMotion, mode d'image jour/nuit intégré, adaptation automatique de « Protection des yeux », anticipation par capteur extérieur, élévation du soleil, application active | — | — | — | voir § 3.6 et 3.7 |

### 1.2 Ce que je ferais en premier

**R1 + R2 + R3 dans un même lot (lot 1, § 7)**, sans mesure préalable :
les valeurs proposées sont des points de départ réglables, et l'essai réel
du lot les valide.

Pourquoi :

1. **Tout le monde en profite, quel que soit le capteur.** Aujourd'hui,
   chaque mesure brute est appliquée (après une seconde de rebond) dès
   qu'elle s'écarte de 3 points : un passage devant le capteur, un reflet
   ou le bruit d'un capteur à 1 lx de résolution en pièce sombre suffisent
   à changer la luminosité (§ 2.2). Le filtrage et l'hystérésis règlent
   cela sans rien demander à l'utilisateur.
2. **C'est un prérequis des autres pistes.** Diagnostics, apprentissage et
   rampes travaillent sur un lux filtré et horodaté : il faut ce socle
   d'abord.
3. **Le conflit avec « Économie d'énergie » Auto est le premier piège d'un
   nouvel utilisateur** : deux régulations sur la même luminosité. On le
   détecte avec un réglage déjà lu par l'intégration ; l'avertissement
   coûte peu.
4. **Le placement pèse plus que l'algorithme** (§ 3.3, 3.4) : une seule
   question bien posée évite la plupart des installations ratées.
5. **Effort et risque faibles** : logique pure, testable sans téléviseur ;
   aucune nouvelle voie d'écriture, aucun nouvel appel à l'API.

Les rampes (R4), plus visibles, viennent juste après ; leur vitesse est
réglable, et le débit soutenable comme l'effet visuel d'un pas se mesurent
à l'essai réel du lot 2 (protocole § 6, P4).

### 1.3 Arbitrages qui vous reviennent

Regroupés au § 8.1 (portée, autres réglages, nombre de capteurs, apprentissage,
complexité de l'interface, historique des rampes, persistance des
diagnostics), chacun avec ma recommandation.

---

## 2. Constat

### 2.1 Ce que fait la version 2.4.0 [Observé]

Vérifié dans le code ; les points de la consigne sont confirmés, avec les
précisions suivantes.

- **Courbe** (`calculer_cible`) : interpolation linéaire de
  `ln(max(lux, 1))` entre `ln(lux_min)` et `ln(lux_max)`, bornée, vers
  `[luminosite_min, luminosite_max]`, arrondi 0,5 vers le haut. Défauts :
  5 et 300 lx, 40 et 100 (`const.py`). Un seul capteur
  (`capteur_lux`). Avec ces défauts, la pente vaut
  60 / ln(60) ≈ **14,7 points par unité de ln(lux)**, soit ≈ 34 points
  par décade.
- **Écart minimal** (3 par défaut) : zone morte **sur la sortie**, comparée
  à la valeur actuelle du téléviseur. Pas d'hystérésis sur le lux, pas de
  lissage, pas de rampe : **confirmé**.
- **Déclenchement** : chaque `state_changed` du capteur (y compris un
  changement d'attribut seul) appelle `_planifier(1 s)`. Une échéance plus
  lointaine est conservée, une plus proche est remplacée : c'est un
  **rebond glissant** (*debounce*) d'une seconde.
- **Lecture du lux** : `float(state)` ; `unavailable` / `unknown` donnent
  « capteur indisponible ». Aucune vérification de l'unité ni de la
  fraîcheur de la valeur.
- **Reprise en main** : toute écriture de `backlight` d'origine extérieure
  (télécommande, réglages rapides, autre application, entité, panneau,
  preset, retour arrière) met en pause `pause` minutes (120 par défaut).
  Levée au rallumage (déconnexion vue pendant la pause), au bouton
  « Reprendre », à l'échéance. La cause (origine, heure) est conservée ;
  **ni le lux du moment ni la valeur choisie** ne le sont.
- **Modes d'image** : défauts exclus `filmMaker`, `expert1`, `expert2` et
  l'option groupée HDR / Dolby Vision ; un mode inconnu du menu est traité
  comme exclu. Réapplication après la cascade d'un changement de mode ou
  d'entrée (1 s), ou 3 s après un lot (preset, annulation).
- **Écriture** : par la file coalescente, avec garde de mode
  (`mode_attendu`). Chaque écriture confirmée est **inscrite dans
  l'historique SQLite** (`restauration.ecrire` → `historique.enregistrer`),
  et l'historique **n'est jamais purgé** (aucun `DELETE` dans
  `historique.py`).
- **Panneau** : courbe à deux points éditable, état en direct, pause 1 h,
  journal des 50 derniers événements en mémoire. La mise en route ne
  demande que le capteur ; la liste des capteurs est filtrée sur la classe
  `illuminance`, triée par nom, sans notion de pièce.

### 2.2 Limites observées

1. **Bruit et quantification en pièce sombre.** Avec les défauts, 3 points
   correspondent à un rapport de lux de e^(3/14,7) ≈ **1,23** (+23 %). Or un
   capteur à résolution de 1 lx passe de 5 à 6 lx en un pas : +2,7 points ;
   de 5 à 7 lx : +4,9 points, donc une écriture. Le bruit d'un seul
   lux au voisinage de `lux_min` suffit à faire des allers-retours de la
   luminosité, d'autant que la zone morte compare à la valeur du
   téléviseur et non au lux de la dernière application (pas de mémoire du
   sens). [Observé dans le code, calcul]
2. **Pas de rejet des valeurs isolées** : un passage devant le capteur ou
   un éclat de soleil est appliqué une seconde plus tard.
3. **Famine du rebond** : un capteur qui publie plus souvent qu'une fois par
   seconde (ESPHome réglé à 500 ms, ou un attribut qui change à chaque
   mesure) repousse l'échéance indéfiniment : la luminosité n'est **jamais**
   appliquée tant que le flux continue. [Observé dans `_planifier` ; cas
   rare mais réel]
4. **Capteur figé non détecté** : un capteur Zigbee à pile morte garde
   souvent sa dernière valeur dans Home Assistant ; la fonction reste
   « active » sur une mesure périmée.
5. **Sauts visibles** : un écart de 40 à 100 est écrit en une fois. Les
   écritures n'affichent rien, mais le changement de luminosité lui-même
   se voit.
6. **Aucune cohabitation** avec les fonctions natives (§ 3.6) : le code ne
   lit ni `energySaving` ni le mode Éco.
7. **Le signal le plus utile est jeté** : une reprise en main dit « à ce
   lux, je veux cette valeur », mais seule l'origine est gardée.
8. **Pause longue et aveugle** : régler la luminosité pour un film puis
   allumer une lampe laisse la fonction en pause jusqu'à 2 h.
9. **Mise en route minimale** : rien ne guide vers le bon capteur, le bon
   placement, ni des bornes adaptées au capteur choisi.

### 2.3 Limites supposées (à confirmer par l'essai)

- **Rétroaction de l'écran** probable dès que le capteur voit l'écran
  (§ 3.4) : la luminosité suivrait alors le contenu (pompage), et la
  courbe serait décalée vers le haut en pièce sombre. [Supposé, calcul]
- **Bornes par défaut** : `luminosite_min` = 40 pourrait être trop lumineux
  pour une pièce noire, si l'on vise ≈ 100 cd/m² comme BT.2035 (§ 3.1). La
  correspondance entre « Luminosité des pixels OLED » et la luminance réelle
  n'est pas connue. **À vérifier** (P3).
- **Débit soutenu** : 10 écritures enchaînées sont toutes appliquées
  (`docs/rapport-api.md`, phase 7), mais un débit de plusieurs écritures
  par seconde pendant des minutes n'a pas été essayé. **À vérifier** (P4).

---

## 3. Analyse par axe

### 3.0 Ce que disent les textes ITU

Textes lus dans leur version officielle (PDF et DOCX de l'ITU, liste au
§ 9) : BT.2035 (2013), BT.2100-3 (2025), BT.1886 (2011), BT.814-4 (2018),
BT.500-15 (2023), BT.2022 (2012), et les rapports BT.2390-11 (2023) et
BT.2408-8 (2024). Citations en anglais, telles qu'écrites.

| Texte | Ce qu'il fixe | Ce qui nous concerne |
|---|---|---|
| **BT.2035** § 1.1, 1.4, 3.2, 3.4 (SDR, pièce de référence) | Éclairage de la pièce **10 lx** ; fond D65 ; luminance du fond derrière l'écran « ≈ between 10 % ± 2 % of reference white value » ; blanc de référence 100 cd/m², noir < 0,01 cd/m² ; EOTF BT.1886 ; surfaces sombres et mates, « minimize stray light on the display screen » | Les deux chiffres cités au premier tour étaient justes : 10 lx **et** un fond à 10 % du blanc (10 cd/m²). C'est la référence « pièce sombre » |
| **BT.2100** tableau 3 et notes 3d, 5f, 5g (HDR) | Entourage 5 cd/m², périphérie ≤ 5 cd/m², « Avoid light falling on the screen » ; hors environnement de référence, régler le noir par PLUGE (BT.814) ; gamma système HLG fonction de la crête ; « The system gamma value may be decreased for brighter background and surround conditions » | Le gamma doit baisser quand l'entourage s'éclaire |
| **BT.500-15** § 2.1.2 et note 3, § 2.1.6 (évaluation à domicile) | 200 lx sur l'écran, mesurés perpendiculairement ; crête 70 à 500 cd/m² ; « **Peak luminance should be adjusted according to the room illumination** » ; « Brightness and contrast of a display should be adjusted under the environment illuminance by using the PLUGE » ; annexe 3 : conditions complémentaires à 500 lx, crête 70 à 200 cd/m², fond à 1/4 de la crête | **Fondement normatif de la fonction** : la crête suit l'éclairage de la pièce. Le noir et le contraste se règlent sous l'éclairage réel |
| **BT.2022** § 1.2, 1.7, 1.7.2 | Mêmes valeurs à domicile ; « Contrast could be strongly influenced by the environment illuminance » ; « it is preferable to use backlight intensity control rather than using signal level scaling to retain the bit precision. In the case of other display technologies that do not use a backlight, the white level should be adjusted by means other than signal level scaling » | Faire varier la luminosité par **la luminosité du panneau** (notre `backlight`), **pas par le contraste** (mise à l'échelle du signal) |
| **BT.814-4** annexes 3 à 5 | Contraste = gain (règle la luminance du blanc) ; luminosité = relèvement du noir, réglé pour que « the blackest stripe just disappears, whilst the brighter stripe remains visible » ; « The adjustments described below are very dependent on the viewing conditions » ; gamma HLG corrigé hors environnement de référence (annexe 5) | Le niveau du noir **dépend de l'éclairage**, et la mire PLUGE donne une méthode que l'utilisateur peut appliquer |
| **BT.1886** annexe 1 | EOTF `L = a·(max(V + b, 0))^γ`, γ = 2,404 ; a = gain (« contrast »), b = relèvement du noir (« brightness ») ; mesure de conformité en pièce noire | BT.1886 suppose une pièce sombre ; le libellé « BT.1886 » du menu Gamma désigne ce cas |
| **BT.2390-11** § 2, 5.4, 6.2 | « To compensate for a brighter environment, display adjust may lift the black level of the signal » ; tests de la BBC (21 observateurs) : `γ_bright = γ_ref − 0,076·log10(L_amb / 5)`, L_amb luminance ambiante en cd/m² | Deux leviers reconnus pour une pièce plus claire : **relever le noir** et **baisser le gamma**, avec une amplitude chiffrée |
| **BT.2408-8** § 3.2, tableaux 3 à 5 | Crête nominale « adjusted to a comfortable level for the viewing environment » ; corrections de gamma selon l'éclairage mesuré perpendiculairement à l'écran, avec un entourage à 60 % de réflexion : 3 lx → +0,08 ; 25 lx → 0 ; 50 lx → −0,02 ; 75 lx → −0,04 ; 130 lx → −0,05 ; « a gamma adjustment of 0.03 is just visible to the expert viewer when viewed side-by-side » | Ordre de grandeur des corrections de gamma, et passage du lux à la luminance de l'entourage |

**Passer du lux du capteur à la luminance de l'entourage.** Le tableau 5
de BT.2408 revient à `L_entourage ≈ E × ρ / π` avec ρ ≈ 0,6
(130 lx × 0,6 / π ≈ 25 cd/m²). Pour un capteur en A (§ 3.3), qui mesure
l'éclairement perpendiculaire à l'écran comme le prévoient BT.500 et
BT.2408, la formule de BT.2390 donne alors :

| Éclairement mesuré (A) | Luminance de l'entourage (ρ = 0,6) | Correction de gamma (BT.2390) |
|---|---|---|
| 5 lx | ≈ 1 cd/m² | +0,05 |
| 26 lx | ≈ 5 cd/m² (référence) | 0 |
| 50 lx | ≈ 10 cd/m² | −0,02 |
| 200 lx | ≈ 38 cd/m² | −0,07 |
| 500 lx | ≈ 95 cd/m² | −0,10 |

[Calcul d'après les textes. Ces formules portent sur le gamma système HLG
en production ; les transposer au gamma SDR d'un téléviseur est une
**extrapolation**.]

**Ce que j'en retiens.**

1. La fonction actuelle est **conforme à l'esprit des normes** : BT.500
   demande d'adapter la crête à l'éclairage, et BT.2022 de le faire par la
   luminosité du panneau. Confiance élevée.
2. **Le contraste n'est pas le bon levier** pour adapter la luminosité
   (BT.2022 § 1.7.2). Confiance élevée.
3. **Le niveau du noir et le gamma sont des leviers légitimes**, reconnus
   par BT.814, BT.2390 et BT.2408, mais **d'amplitude faible** : environ
   0,15 de gamma entre une pièce à 5 lx et une pièce à 500 lx. Le menu du G5
   ne propose que des crans (2.2, BT.1886, peut-être d'autres, à vérifier),
   distants d'environ 0,2. Une bascule n'est donc justifiée par les normes
   qu'en pièce très claire (§ 3.6.3). Confiance moyenne.
4. Aucun texte ITU ne traite de la couleur selon l'ambiance : fond et blanc
   restent en D65 partout. Confiance élevée.

### 3.1 Courbe et dynamique

#### Forme de la courbe

**État de l'art.**

- La perception de la luminosité suit approximativement le logarithme de
  l'éclairement : Microsoft montre que des paliers d'ambiance courants
  (« Pitch black » 0–10 lx … « Direct sunlight » 30 000–100 000 lx)
  s'alignent quand le lux est porté sur une échelle logarithmique.
  [Source : Microsoft, *Understanding and Interpreting Lux Values*] Le
  choix actuel (linéaire sur ln(lux)) est donc **le bon modèle de base** ;
  je ne recommande pas de le remplacer.
- Les environnements de référence fixent les extrêmes (§ 3.0) : pièce de
  référence à 10 lx avec un blanc à 100 cd/m² (BT.2035), domicile à 200 lx
  sur l'écran avec une crête de 70 à 500 cd/m², et une crête « adjusted
  according to the room illumination » (BT.500-15).
- Les préférences mesurées montrent une hausse modérée de la luminance
  préférée avec l'ambiance : de l'ordre de 100 cd/m² pour 100 à 300 lx
  chez des sujets jeunes dans une étude sur LCD ; ≈ 150 cd/m² à 200 lx
  et 3 m pour un 55 pouces (Matsumoto et al.). Les sujets âgés préfèrent
  plus lumineux (≈ 210–240 cd/m²). [Source : études citées au § 9 ;
  chiffres issus des résumés, articles complets non lus]
- Android passe d'une courbe constructeur commune plus un facteur global à
  une courbe **personnelle** apprise ; le curseur y devient perceptif
  (non linéaire). [Source : Android Developers Blog, 2018]

**Conséquences.** Entre une pièce noire et une pièce claire, la luminance
préférée varie d'un facteur 1,5 à 2,5 environ, pas de 1 à 10. L'amplitude
40 → 100 est plausible **si** la luminance de l'écran est à peu près
proportionnelle à la valeur OLED, ce qui n'est pas établi. La forme exacte
compte moins que **le calage sur la préférence de l'utilisateur**, d'où le
point d'ancrage (R6) et les suggestions (R8).

**Options classées.**

1. **Courbe à 3 points sur log(lux), interpolation linéaire par morceaux,
   monotone** (recommandé, R9). Lisible (« sombre, soirée, jour »),
   éditable au doigt, suffisante pour corriger un capteur qui sature ou un
   placement qui écrase une plage. Conserve la compatibilité : les deux
   points actuels sont les extrémités, le point intermédiaire est
   facultatif. Confiance moyenne.
2. *Gamma* sur la sortie (`t^γ`) : un seul nombre, mais abstrait pour
   l'utilisateur, et sans fondement tant que la réponse de l'écran est
   inconnue. Non recommandé.
3. Modèle perceptif (luminance cible en cd/m², convertie en valeur OLED par
   une table mesurée) : le plus juste en théorie, mais il exige la table
   OLED → cd/m² du G5 par mode d'image, qu'on ne connaît pas (P3). À
   reconsidérer **seulement si** P3 montre une réponse très non linéaire.

#### Dynamique

**État de l'art (Android, AOSP `config.xml`).** [Source]

| Paramètre Android | Défaut AOSP | Rôle |
|---|---|---|
| `config_autoBrightnessBrighteningLightDebounce` | 4000 ms | stabilité exigée avant d'éclaircir |
| `config_autoBrightnessDarkeningLightDebounce` | 8000 ms | stabilité exigée avant d'assombrir |
| `config_ambientBrighteningThresholds` | 100 (dixièmes de %, soit +10 %) | hystérésis en montée |
| `config_ambientDarkeningThresholds` | 200 (soit −20 %) | hystérésis en descente |
| `config_autoBrightnessLightSensorRate` | 250 ms | cadence du capteur |
| `config_brightness_ramp_rate_slow` / `_fast` | 60 / 180 unités par seconde | rampes d'affichage |
| `config_autoBrightnessShortTermModelTimeout` | 300 000 ms | oubli d'une correction de l'utilisateur |

Deux principes à retenir : **montée plus rapide que descente**, et
**hystérésis relative** (en pourcentage du lux, donc en log). Les
constructeurs remplacent ces valeurs par appareil : ce sont des ordres de
grandeur, pas des valeurs à copier. Le compte rendu de Display Daily sur
Dolby Vision IQ cite aussi le défaut opposé, celui des algorithmes trop
lents qui produisent des « surges » de luminosité très gênantes.

**Différence essentielle avec un téléphone.** Android lit son capteur
toutes les 250 ms. Ici, le capteur peut publier toutes les secondes
(ESPHome) comme toutes les 5 minutes, ou seulement sur variation (Zigbee,
Z-Wave sur pile). **Le filtre doit donc être défini en temps, pas en
nombre d'échantillons**, et tolérer des pas irréguliers.

**Options classées (R1).**

1. **Filtre exponentiel sur ln(lux), à pas de temps irrégulier,
   asymétrique** (recommandé). À chaque mesure, après un intervalle Δt :
   `α = 1 − exp(−Δt / τ)`, `y ← y + α·(ln(lux) − y)`, avec τ_montée < τ_descente.
   Un capteur lent (Δt grand) donne α ≈ 1 : la mesure s'applique presque
   telle quelle, sans retard ajouté ; un capteur rapide est lissé. **Un seul
   algorithme s'adapte de lui-même au capteur.** Départs proposés :
   τ_montée = 5 s, τ_descente = 15 s. Confiance élevée sur le principe,
   moyenne sur les valeurs.
   - Le filtre doit évoluer aussi entre deux mesures (valeur maintenue) :
     réévaluer à intervalle fixe tant que `y` n'a pas rejoint la dernière
     mesure, sinon un capteur qui ne publie que sur variation laisse le
     filtre à mi-chemin.
2. **Hystérésis relative sur le lux filtré** : nouvelle application seulement
   si le lux filtré sort de `[L_réf / 1,2 ; L_réf × 1,1]`, où `L_réf` est le
   lux de la dernière application (repris d'Android : +10 % / −20 %).
   Supprime les allers-retours du § 2.2-1. L'écart minimal en sortie reste,
   abaissé à 2 par défaut quand les rampes existeront.
3. **Confirmation des sauts isolés** : un saut de plus d'un facteur 4 par
   rapport au filtre n'est pris en compte que s'il est confirmé par une
   deuxième mesure **ou** après un délai de confirmation (8 s proposés)
   sans démenti. Un capteur qui ne publie que sur variation n'enverra pas
   de seconde mesure : d'où le délai. Coût : une lampe qu'on allume est
   suivie avec 8 s de retard. Médiane glissante écartée : sur un capteur
   à 5 minutes, une médiane de 3 ajoute 10 minutes de retard.
4. **Débit au lieu du rebond glissant** (correction du § 2.2-3) :
   application au plus une seconde après la *première* mesure d'une rafale
   (*throttle*), et non une seconde après la dernière.
5. **Capteur figé** : si `last_reported` (mis à jour par Home Assistant
   même quand la valeur ne change pas, depuis 2024.3 [Source : blog
   développeurs HA]) n'a pas bougé depuis plus de 3 fois l'intervalle
   habituel du capteur et au moins 2 h, téléviseur allumé : nouvel état
   « capteur figé », la valeur courante est gardée. Confiance moyenne : un
   capteur qui ne publie que sur variation, dans une pièce stable, peut se
   taire longtemps légitimement. D'où le seuil long et un **diagnostic**
   plutôt qu'une coupure si l'intervalle habituel n'est pas connu.

**Rampes (R4).**

- Mesuré : un appel `createAlert` + `closeAlert` dure 0,02 à 0,12 s, la
  notification arrive ≈ 0,1 s après ; dix écritures sans attente passent
  en 0,51 s, toutes appliquées dans l'ordre. [Observé, rapport phase 7]
- Notre chemin attend la notification sous verrou (`Televiseur.ecrire`) :
  de l'ordre de **5 écritures par seconde au mieux**. [Supposé, d'après les
  délais mesurés]
- Proposition : pas de 1 à 2 points toutes les 0,25 à 0,5 s, soit 4 points
  par seconde. 40 → 100 prend alors 15 s ; un écart courant de 10 points,
  2,5 s. La coalescence de la file joue naturellement : si la cible change
  pendant la rampe, le pas suivant vise la nouvelle cible.
- **À mesurer avant de coder** (P4) : un pas de 1 ou 2 points se voit-il
  sur du contenu réel ? Le téléviseur lisse-t-il déjà lui-même ? Un débit
  de 4 écritures par seconde pendant 15 s, plusieurs fois par heure,
  reste-t-il stable (pas de refus EWS 1008, pas d'alerte visible) ?
- **Historique** : une rampe de 60 pas créerait 60 entrées. Proposition :
  une seule entrée par rampe (ancienne = départ, nouvelle = arrivée). Cela
  touche une décision actée (« toutes les écritures … avec leur origine
  dans l'historique ») : arbitrage A5 au § 8.1.
- Une reprise en main pendant une rampe l'interrompt (origine extérieure
  notifiée), comme aujourd'hui.

#### Valeurs par défaut sensées

- Courbe : garder 5 / 300 lx et 40 / 100 tant que P3 et P7 n'ont pas
  donné mieux ; le point d'ancrage de la mise en route (R6) cale la courbe
  sur l'utilisateur dès le premier jour.
- Filtre : τ_montée 5 s, τ_descente 15 s, hystérésis +10 % / −20 %,
  confirmation 8 s au-delà d'un facteur 4, gel de 5 s après nos écritures
  (§ 3.4). Les profils de capteur (§ 4.1) n'ajustent que ces valeurs-là,
  jamais la courbe.

### 3.2 Profils par type de capteur

**Ce que l'application peut détecter seule.** [Observé : API Home
Assistant ; exemples de valeurs **à vérifier**]

- Registre des entités : **plateforme** de l'entité (`zha`, `mqtt` pour
  Zigbee2MQTT, `esphome`, `zwave_js`, `hue`, `deconz`, `matter`…), unité
  (`lx` : c'est la seule unité de la classe `illuminance`), `state_class`.
- Registre des appareils : **fabricant, modèle, `model_id`**, et la
  **pièce** de l'appareil, à comparer avec celle du téléviseur (même pièce →
  capteur proposé en premier). L'intégration n'utilise pas encore le
  registre des appareils.
- Observation : intervalle entre publications (`last_reported`), plus petit
  pas entre deux valeurs distinctes en faible lumière (résolution), valeurs
  entières seulement, maximum atteint de façon répétée (saturation), 0
  fréquent (plancher).

Le modèle de la puce d'un montage ESPHome n'apparaît pas dans le registre
(le « modèle » est la carte) : **à demander** à l'utilisateur, ou à
déduire du nom de l'entité, faute de mieux.

**Familles courantes.** Tout ce qui n'est pas sourcé est marqué.

| Famille | Exemples | Plage | Faible lumière | Rapport | Réglable côté capteur | Sources |
|---|---|---|---|---|---|---|
| ESPHome BH1750 | modules GY-30 / GY-302 | jusqu'à ≈ 54 600 lx en mode H (65 535 / 1,2) ; plage annoncée à vérifier | pas de 1 lx (mode H) ou 0,5 lx (mode H2) ; mesure 120 ms ; sortie à 0 lx : 0 à 3 comptes | `update_interval` 60 s par défaut | oui (`update_interval`, filtres ESPHome) | fiche ROHM, doc ESPHome, calcul tiers |
| ESPHome TSL2591 | modules Adafruit | jusqu'à ≈ 88 000 lx ; dynamique 600 M:1 | excellente (gain ×9 500) | 60 s par défaut ; intégration 100–600 ms | oui ; gain auto : une mesure peut saturer après un saut | doc ESPHome |
| ESPHome VEML7700 | modules Adafruit | 0 à ≈ 120 000 lx ; non linéaire au-delà de 1 000 lx aux faibles gains, forte erreur au soleil | bonne, mais « plusieurs secondes » par mesure sous 46 lx en mode auto | 60 s par défaut | oui ; facteur d'atténuation du verre | doc ESPHome |
| Zigbee Aqara T1 (GZCGQ11LM) | capteur de lumière dédié | plage à vérifier ; 0 = « trop faible pour être mesuré » | à vérifier | `detection_period` 1 à 59 s | oui (Z2M : période, `illuminance_calibration` en %) | doc Zigbee2MQTT |
| Zigbee Philips Hue | capteur de mouvement SML001/002/004 | à vérifier ; 0 = trop faible | à vérifier | ≈ 5 min en périodique, plus sur variation (rapports d'utilisateurs, non officiels) ; nouvelle mesure au mouvement | calibrage en % (Z2M) ; cadence peu ou pas réglable d'après les rapports | doc Z2M, forums |
| Zigbee IKEA VALLHORN (E2134) | capteur de mouvement | à vérifier | à vérifier | à vérifier | calibrage (Z2M) | doc Z2M, forum openHAB |
| Présence mmWave avec lux (Tuya, Aqara FP2…) | capteurs de plafond ou de mur | à vérifier | souvent entiers, bruités (à vérifier) | à vérifier | variable | — |
| Z-Wave Fibaro FGMS-001 | capteur de mouvement | à vérifier | — | **seuil par défaut 200 lx** (paramètre 40) et rapport périodique désactivé (paramètre 42 = 0) | oui | documentation tierce, forums |
| Z-Wave Aeotec MultiSensor 6 | multicapteur | à vérifier | — | sur pile, 3 600 s par défaut (paramètre 111), arrondi au réveil ; seuil paramètre 43 (100 par défaut, unité à vérifier) | oui, mais l'alimentation est figée à l'inclusion | documentation tierce, forums |
| Station météo (Ecowitt…) | extérieur | à vérifier ; parfois en W/m² | sans objet la nuit | à vérifier | non | — |

**Ce que la plupart des capteurs domotiques ont en commun** (constat des
sources, confiance moyenne) : périodes longues ou rapports sur variation,
pas grossier en faible lumière, aucune donnée sur la réponse angulaire. Le
réglage d'usine des Z-Wave courants (Fibaro : 200 lx de seuil) les rend
**inutilisables tels quels** pour une pièce à 5–50 lx.

**Ce que l'application propose par profil** (recommandé, R1 + R5) :

| Profil | Détection | Filtre proposé | Conseil affiché |
|---|---|---|---|
| Rapide (intervalle < 10 s) | ESPHome, ou intervalle observé | τ 5 s / 15 s, confirmation des sauts 8 s | « Une mesure toutes les 1 à 5 s suffit ; plus rapide n'apporte rien. » |
| Sur variation (Zigbee courant) | plateforme `zha` / `mqtt` / `hue` | τ 0 s / 5 s (les mesures sont rares, ne pas les retarder) ; confirmation des sauts seulement si une 2ᵉ mesure arrive vite | « Réglez la période de détection au plus court » (Aqara) ; « la cadence de ce capteur ne se règle pas » (Hue, à vérifier) |
| Lent (intervalle > 5 min ou seuil > 50 lx) | Z-Wave sur pile, intervalle observé | sans filtre ; diagnostic « trop lent » | « Abaissez le seuil de rapport (paramètre 40 de 200 à 10 lx, par exemple) ; l'autonomie de la pile baissera. » Valeurs à vérifier |
| Extérieur | pièce « extérieur », ou choix de l'utilisateur | refusé comme capteur principal | « Ce capteur mesure la lumière du jour : utile en secours ou en complément, pas seul. » |

**Étalonnage.** Point important : sur une courbe en ln(lux), **un facteur
multiplicatif équivaut à un décalage de la courbe** (ln(k·lux) =
ln(lux) + ln k). Avec un seul capteur, un facteur d'étalonnage ne sert à
rien de plus que de déplacer `lux_min` et `lux_max` ; le point d'ancrage le
fait mieux, puisqu'il cale directement sur la préférence. Le facteur ne
sert que si l'on **change** ou **combine** des capteurs, ou pour que les
valeurs proposées soient exprimées en « vrais » lux. Le décalage
(additif) compte au plancher : un capteur qui affiche 1 lx dans le noir
complet. Recommandation : **pas d'assistant d'étalonnage au départ** ; un
facteur par capteur seulement avec la fusion (R12). Confiance élevée sur le
raisonnement.

### 3.3 Placement

**Ce que mesure un capteur de lux.** Un éclairement en lx, reçu par sa
surface, selon son orientation. Il ne mesure ni la luminance du fond ni
« l'adaptation de l'œil », mais il s'en approche selon son orientation.
BT.2022 définit l'éclairement ambiant domestique **sur l'écran, mesuré
perpendiculairement à l'écran** [Source] : c'est exactement ce qui
dégrade le contraste par reflet, et ce que mesure le capteur intégré au
téléviseur, en façade.

| Emplacement | Ce qu'il mesure | Biais | Rétroaction de l'écran (§ 3.4) | Correction | Verdict |
|---|---|---|---|---|---|
| **A. À côté de l'écran, dans son plan, tourné vers la pièce** (meuble TV, cadre) | éclairement reçu par l'écran (définition BT.2022) | soleil direct si une fenêtre fait face | faible (l'écran n'émet pas vers lui ; seule la lumière renvoyée par la pièce) | aucune | **Recommandé** |
| **B. Mur derrière le téléviseur, tourné vers le mur** | lumière renvoyée par le mur, ≈ π × luminance du fond | éclairage d'ambiance derrière l'écran (*bias light*) : c'est justement le fond que l'on voit | faible | aucune ; courbe plus basse (un mur renvoie 20 à 60 % de la lumière, à vérifier) | Bon, difficile à installer |
| **C. Plafond, tourné vers le bas** (capteurs de présence) | lumière renvoyée par le sol et les meubles, lampes proches | une suspension proche domine | moyenne | point d'ancrage | Acceptable |
| **D. Au point de vue (canapé), tourné vers l'écran** | éclairement vertical vu par le spectateur | — | **forte** : l'écran est la source principale en pièce sombre | gel + diagnostic ; compensation incertaine | **Déconseillé** |
| **E. Au point de vue, tourné vers le haut** | éclairement horizontal général | lampes de lecture | moyenne | point d'ancrage | Acceptable |
| **F. Près d'une fenêtre** | surtout la lumière du jour | surestime la pièce le jour, inutile le soir ; soleil direct, saturation | faible | capteur intérieur en complément | Déconseillé seul |
| **G. Extérieur** | lumière du jour | aucun lien avec l'éclairage artificiel | nulle | — | Secours ou complément seulement |

**Comment guider.**

1. Question **« Où est votre capteur ? »** au réglage (A à G, plus « autre
   / je ne sais pas »), avec un **schéma** vu de dessus (§ 4.2). La réponse
   règle la garde contre la rétroaction (D : gel plus long, diagnostic
   renforcé), signale les cas déconseillés (D, F, G seuls), et
   préremplit le profil.
2. Textes courts par emplacement, avec l'action conseillée (§ 4.2).
3. Diagnostic de rétroaction (§ 3.4) qui **vérifie** a posteriori la réponse
   donnée : « Votre capteur semble voir l'écran : … ».

Confiance : élevée sur le classement A > B > C/E > D ; moyenne sur les
ordres de grandeur (§ 3.4).

### 3.4 Rétroaction de l'écran

**Ordre de grandeur** [Supposé, calcul ; à mesurer en P2]. Un écran de
65 pouces fait 1,16 m². Pour un émetteur lambertien de luminance moyenne L
vu de face à une distance d grande devant sa taille, l'éclairement reçu
vaut environ `E ≈ L·A·cos θ_e·cos θ_r / d²`. La lumière renvoyée par la
pièce s'estime par `Φ·ρ / (S·(1 − ρ))`, avec `Φ = π·L·A`, pour une pièce
de 85 m² de parois et un facteur de réflexion moyen ρ = 0,4.

| Luminance moyenne de l'image | Face à l'écran, 2,5 m (D) | Face à l'écran, 3,5 m (D) | Plafond, 2 m devant et 1,2 m au-dessus du centre (C) | Lumière renvoyée seule (A, B) |
|---|---|---|---|---|
| 30 cd/m² (film sombre) | ≈ 6 lx | ≈ 3 lx | ≈ 3 lx | ≈ 1 lx |
| 100 cd/m² (émission claire) | ≈ 19 lx | ≈ 10 lx | ≈ 9 lx | ≈ 3 lx |
| 470 cd/m² (plein écran blanc, maximum SDR mesuré par RTINGS sur le G5) | ≈ 88 lx | ≈ 45 lx | ≈ 44 lx | ≈ 13 lx |

Lecture : dans une pièce à 5 lx, un capteur face à l'écran mesure 2 à 4
fois la lumière ambiante sur du contenu courant. Placé à côté de l'écran
(A), il ne reçoit qu'environ 1 à 3 lx de lumière renvoyée.

**Effet sur la fonction.**

- **Biais** : à 5 lx réels, un film sombre lu face à l'écran donne
  ≈ 11 lx, donc une cible de 52 au lieu de 40 (+12 points).
- **Pompage** : quand le contenu passe de sombre à clair, la contribution
  passe par exemple de 3 à 15 lx, la mesure de 8 à 20 lx, et la cible varie
  de 14,7 × ln(2,5) ≈ **13 points** : la luminosité suit le contenu, avec
  le retard du capteur. C'est le vrai problème.
- **Oscillation proprement dite peu probable** : le gain de boucle vaut à
  peu près `pente × (part de l'écran dans la mesure) / valeur OLED`, soit
  ≈ 14,7 × 0,67 / 70 ≈ 0,14 pour 10 lx venus de l'écran sur 15 lx mesurés,
  à la valeur OLED 70 : très inférieur à 1.
  La boucle converge, avec un biais. Une courbe très raide (plage de lux
  étroite) et un filtre lent peuvent néanmoins produire des cycles.
  [Supposé ; hypothèse : luminance proportionnelle à la valeur OLED, à
  vérifier en P3]

**Détection automatique (options classées).**

1. **Allumage et extinction du téléviseur** (recommandé) : comparer le lux
   filtré juste avant la déconnexion et 30 à 120 s après (et l'inverse au
   rallumage). La médiane des écarts sur plusieurs événements estime la
   contribution de l'écran, à la valeur OLED et au contenu moyens. Marche
   avec tous les capteurs assez rapides pour publier dans la fenêtre ; sans
   conclusion pour un capteur à 5 minutes. Attention : l'extinction coïncide
   souvent avec un changement d'éclairage (on rallume en fin de film) ; d'où
   la médiane et un nombre minimal d'événements (5, proposé). Confiance
   moyenne.
2. **Réponse aux écritures** : après une rampe de Δb points, mesurer la
   variation de ln(lux) une fois le capteur stabilisé. Elle devrait être
   nulle sans rétroaction. Exige un capteur rapide. Confiance moyenne.
3. **Variance pendant le visionnage** : un lux qui fluctue beaucoup plus
   téléviseur allumé qu'éteint, à heure comparable, signe une rétroaction.
   Indice faible, utile en complément.

**Compensation.**

- **Gel de la mesure** pendant une écriture et quelques secondes après (5 s
  proposées ; le délai du capteur s'y ajoute, d'où un gel plus long pour le
  placement D). Simple, sans risque. Recommandé.
- **Soustraction d'une contribution estimée** `Ê_écran × (valeur OLED /
  valeur de référence)` : elle ignore la part due au contenu, qui n'est pas
  accessible par l'API (aucune donnée de niveau moyen de l'image), et peut
  rendre l'ambiance négative en pièce noire. **Seulement en option, plus
  tard**, bornée (au plus 80 % de la mesure). Confiance faible.
- **Filtre plus lent en descente** pour le placement D : amortit le pompage,
  au prix de la réactivité.
- **La vraie correction est le déplacement du capteur** : le diagnostic le
  dit, chiffres à l'appui.

### 3.5 Combinaison de capteurs

**Options classées.**

1. **Capteur principal + capteur de secours** (recommandé, R12) : le
   secours ne sert que si le principal est indisponible ou figé. Utile,
   simple, aucun réglage de fusion. Exige un facteur relatif entre les deux,
   appris en continu quand les deux publient (médiane de ln(l1/l2)).
2. **Médiane de 3 capteurs ou plus** : robuste à un capteur aberrant
   (soleil sur l'un, ombre sur l'autre). Rare chez les utilisateurs ;
   à proposer seulement si la demande existe.
3. **Moyenne géométrique pondérée** (moyenne des ln(lux), poids par
   capteur) : pour combiner deux placements complémentaires (A et C). Plus
   difficile à expliquer.
4. *Minimum / maximum* : non recommandés (le minimum suit l'ombre,
   le maximum le soleil direct).
5. **Rôles différents (extérieur pour anticiper)** : faible valeur. Le
   rapport intérieur / extérieur change avec les volets et les rideaux, et
   la fonction n'a rien à anticiper : un capteur intérieur rapide suit déjà
   la tombée du jour, qui est lente. Écarté (confiance moyenne).

**Combinaisons recommandées selon l'équipement.**

| Équipement | Recommandation |
|---|---|
| Un capteur intérieur | Seul, placé en A si possible |
| Un intérieur lent (Zigbee à 5 min) + un rapide (ESPHome) | Le rapide en principal, le lent en secours |
| Un intérieur + un extérieur | L'intérieur seul ; l'extérieur en secours de jour au mieux |
| Seulement un extérieur ou une station météo | Déconseillé : la fonction suit le jour, pas l'éclairage de la pièce ; message explicite |

**Incohérences à signaler** : rapport entre deux capteurs très instable
(écart-type de ln(l1/l2) élevé), l'un figé ou saturé, l'un à 0 quand
l'autre dépasse 20 lx.

### 3.6 Autres réglages du téléviseur

#### 3.6.0 Fonctions natives : le G5 a-t-il un capteur ? Oui. [Observé]

| Fonction (libellé du menu) | Ce qu'elle fait (guide, firmware) | Lisible par l'API ? | Effet sur notre fonction |
|---|---|---|---|
| **Fonction Économie d'énergie** = Auto (Général › Économie d'énergie) | « Le capteur du produit détecte l'éclairage ambiant et règle automatiquement la luminosité de l'écran » (guide 6.14) ; « Luminosité minimale » associée (`energySavingAutoMin`, non lisible) | **Oui** : `picture.energySaving` (auto, off, min, med, max), entité active par défaut | **Conflit direct** : deux régulations sur la même luminosité. Le guide prévient que la luminosité peut ne plus être réglable en Auto ou Maximum |
| Mode d'image **Éco** | « Le capteur de lumière ambiante ajuste automatiquement … Luminosité des pixels OLED selon les conditions d'éclairage ambiant » (guide) | **Oui** : `pictureMode` = `eco` | Même conflit |
| **Lumière ambiante du MODE FILMMAKER** | Spécification FILMMAKER MODE 1.1 de l'UHD Alliance, « Ambient Light Compensation » : ajuste la luminance et le gamma, pas les couleurs, en SDR, HDR10 et Dolby Vision [Source : presse] | **Non** (`filmmakerAmbientLight` refusé en lecture) | Aucun par défaut : `filmMaker` est exclu. C'est **la bonne voie pour ce mode** : à recommander plutôt que d'inclure FILMMAKER dans notre fonction |
| **Paramètres de luminosité AI** (Général › Service d'AI) | « L'IA exprime efficacement les zones plus sombres en fonction de l'environnement et des caractéristiques du contenu » (guide 6.6.2) | **Non** (`aiPicture.ai_Brightness` refusé) | Cumul possible, effet à vérifier |
| **Protection des yeux** | « Ajuste automatiquement la luminosité … en fonction des données d'image » (guide) | Oui (`motionEyeCare`) | Agit sur le contenu, pas sur l'ambiance ; cumul à signaler pour information |
| Dolby Vision IQ | Combine les métadonnées dynamiques et le capteur du téléviseur ; ajuste le rétroéclairage et la courbe PQ [Source : presse] | Le guide du G5 ne cite la marque qu'en mentions légales : **présence et réglage à vérifier** | Les modes HDR et Dolby Vision sont exclus par défaut |

Le firmware conditionne ces options à une configuration
`tv.model.digitalEye` (≠ `off`), qui désigne vraisemblablement la présence
du capteur. [Observé dans `settings-main.js` ; interprétation supposée] La
**valeur mesurée par le capteur du téléviseur n'est exposée nulle part**
dans l'app Réglages (aucun service de capteur appelé). L'utiliser comme
source serait idéal (placement A, sur l'écran même) : **à vérifier**, mais
peu probable par l'API publique.

**À mesurer (P5)** : en Économie d'énergie Auto, le téléviseur modifie-t-il
la *valeur* `backlight` (alors notifiée, et avec quel `caller` ? notre
fonction se mettrait en pause à tort si elle la prenait pour un réglage
manuel), ou applique-t-il un facteur interne invisible ? Nos écritures
sont-elles acceptées et ont-elles un effet ?

**Recommandation (R2, confiance élevée pour la détection)** :

- `energySaving` ≠ `off` ou mode `eco` : état « en conflit avec une
  fonction du téléviseur », message et bouton « Désactiver l'économie
  d'énergie automatique » (écriture de `energySaving` = `off` par la file,
  sur action explicite de l'utilisateur).
- Rubrique d'aide : « Lumière ambiante du MODE FILMMAKER » et « Paramètres
  de luminosité AI » ne sont pas lisibles ; si vous les utilisez, voici ce
  qui se passe.

#### 3.6.1 Méthode

Tous les réglages lisibles ou écrivables par l'API (`inventaire-api.json`,
`menu_tree/`) sont passés en revue, avec quatre questions :

1. Existe-t-il un **fondement** (norme, physique de la vision, étude) pour
   le faire dépendre de la lumière ambiante, ou de l'heure ?
2. Le réglage est-il **continu** (curseur, suivi en douceur possible) ou
   **discret** (liste : chaque changement se voit) ?
3. Est-il **propre au mode d'image** ? Le descripteur du téléviseur le dit
   pour 7 clés seulement [Observé] : `backlight`, `contrast`, `brightness`,
   `color`, `sharpness` dépendent de l'entrée et du mode ; `pictureMode` de
   l'entrée et de la plage dynamique ; `eyeComfortMode` (Réduire la lumière
   bleue) a une dimension vide, donc **vaut pour tous les modes et toutes
   les entrées**. Pour les autres, les descripteurs sont refusés : **à
   vérifier** (P10).
4. Quel **risque** pour l'image (écart à l'intention de l'auteur) et pour la
   cohérence avec les fonctions natives ?

#### 3.6.2 Réglages exposés par l'API

| Réglage (menu) | Clé | Type | Lien avec l'ambiance ou l'heure | Ce qu'on pourrait faire | Risques | Verdict | Confiance |
|---|---|---|---|---|---|---|---|
| Luminosité des pixels OLED | `backlight` | curseur 0–100, propre au mode | **Normatif** : crête selon l'éclairage (BT.500-15 note 3), par le panneau et non le signal (BT.2022 § 1.7.2) | Ce que fait la fonction | — | Fait ; à améliorer (R1 à R10) | Élevée |
| Ajuster le contraste | `contrast` | curseur 0–100, propre au mode | Gain utilisateur, fixe le blanc (BT.814) ; BT.2022 déconseille d'adapter le blanc par mise à l'échelle du signal | Rien de plus que `backlight`, en moins bien | Perte de précision, écrêtage au-delà de la valeur de référence | **Non** | Élevée |
| Niveau noir | `brightness` | curseur 0–100, propre au mode | **Normatif** : à régler sous l'éclairage réel avec PLUGE (BT.814, BT.500) ; relevé en pièce claire (BT.2390). Physique : la lumière renvoyée par l'écran, `E × R / π`, masque les détails proches du noir (réflectance R du G5 inconnue, à mesurer) | Petit décalage selon le lux, calé par l'utilisateur sur une mire PLUGE à 2 ou 3 éclairages (R16) | Noirs grisâtres si une lampe s'allume brièvement ; amplitude utile peut-être nulle sur un écran peu réfléchissant | **Option**, désactivée par défaut, seulement si P9 montre un écart d'au moins 2 points entre pièce noire et pièce claire | Moyenne (principe), faible (amplitude) |
| Gamma | `gamma` | liste (2.2, BT.1886… ; correspondance API inconnue), propre au mode (à vérifier) | **Normatif** : gamma plus bas en entourage clair (BT.2100 note 5g, BT.2390, BT.2408), mais ≈ −0,1 seulement à 500 lx ; pratique des étalonneurs : 2.2 en pièce claire, 2.4 / BT.1886 dans le noir | Bascule BT.1886 ↔ 2.2 au-delà d'un seuil élevé (≈ 200 à 300 lx), hystérésis forte (R13) | Saut visible à chaque bascule ; correction plus forte que ce que donnent les normes | **Option**, après P5 bis | Faible à moyenne |
| Contraste dynamique automatique | `dynamicContrast` | liste off/low/medium/high | Aucune norme ; traitement selon le contenu. En pièce claire, rehausser le contraste améliore la lisibilité perçue (c'est l'esprit du mode Vif) [Supposé] | Valeur par ambiance (R14) | Déforme l'image dans le noir ; se cumule avec l'ABL | Possible dans les ambiances, **aucune valeur proposée par défaut** | Faible |
| Luminosité maximale | `peakBrightness` | liste off/high | Aucune norme ; augmente la luminance des hautes lumières. Utile en pièce claire, éblouissante et plus usante dans le noir [Supposé] | Activé en ambiance claire, désactivé dans le noir (R14) | Faible | Possible dans les ambiances | Faible à moyenne |
| Mappage des tons dynamiques | `hdrDynamicToneMapping` | liste on/off (HGIG accepté par l'API) | HDR seulement ; en PQ (luminance absolue), c'est le levier d'adaptation naturel, plutôt que `backlight`. Pratique répandue : activé en pièce claire, désactivé pour la fidélité dans le noir (aucune source solide trouvée) | Valeur par ambiance quand l'utilisateur inclut les modes HDR (R14) | Change le rendu de l'auteur ; ne pas toucher au HGIG des jeux | Possible, HDR seulement | Faible |
| **Protection des yeux** | `motionEyeCare` | interrupteur | Guide : « ajuste automatiquement la luminosité et réduit l'effet de flou **en fonction des données d'image** ». Presse : assombrit les scènes rapides ou claires, rend les scènes sombres plus sombres ; RTINGS la désactive pour ses mesures. **Aucun lien avec l'ambiance** : c'est une troisième régulation, selon le contenu, qui se cumule avec la nôtre | Pourrait se défendre dans le noir (scènes claires soudaines) [Supposé], mais elle assombrit les scènes sombres là où c'est le plus gênant | Pompage cumulé avec notre fonction ; effet sur `backlight` à vérifier (P5, P10) | **Pas d'adaptation automatique** ; diagnostic d'information quand elle est active ; valeur par ambiance possible (R14), non recommandée | Moyenne |
| **Réduire la lumière bleue** | `eyeComfortMode` | liste on/off, **globale** (tous modes, toutes entrées) | **Lien avec l'heure, pas avec le lux.** Consensus de 18 chercheurs (Brown et al., 2022) : au plus 10 lx d'éclairement mélanopique équivalent à l'œil dans les 3 h avant le coucher ; un écran seul peut en fournir plus de 60 ; réduire le bleu des écrans ne retire qu'environ 50 % de l'effet, « best combined with other evening light reductions, such as dimming screens ». Effet sur le sommeil discuté : pas de différence avec Night Shift sur 167 étudiants (Duraccio et al., 2021), un effet sur le sommeil lent profond dans une autre étude (Schmid et al., 2021, source secondaire) | État « Soirée » (R15) : à partir d'une heure choisie ou d'une entité Home Assistant, activer la réduction **et** abaisser le plafond de luminosité, l'abaisser étant le levier le plus fort ; retour à la normale le matin ou à l'extinction | Image plus chaude (écart au D65), **y compris dans les modes calibrés**, puisque le réglage est global (comportement du firmware en FILMMAKER à vérifier) ; bénéfice sur le sommeil incertain : à présenter sans promesse de santé | **Option « Soirée »**, désactivée par défaut | Moyenne (principe), faible (bénéfice) |
| Température de couleur | `colorTemperature` | curseur −50 à +50 | Les normes fixent un blanc D65 dans toutes les conditions ; Dolby Vision IQ et la compensation FILMMAKER ne touchent pas aux couleurs ; les capteurs domotiques de température de couleur sont rares | Imitation de True Tone | Écart à l'intention de l'auteur ; ferait doublon avec Réduire la lumière bleue | **Non** | Moyenne |
| Profondeur de couleur, Teinte | `color`, `tint` | curseurs | La saturation perçue varie avec la luminance (effet Hunt), mais aucune norme ni fonction native ne corrige la couleur selon l'ambiance | — | Couleurs fausses | **Non** | Moyenne |
| Gamme de couleurs, gestion des couleurs, balance des blancs | `colorGamut`, `colorManagement*`, `whiteBalance*` | listes, curseurs | Étalonnage ; aucun lien avec l'ambiance | — | Défait un étalonnage | **Non** | Élevée |
| Netteté, Résolution élevée, Réduction du bruit (×2), Dégradés fluides, Cinéma originel, TruMotion | `sharpness`, `superResolution`, `noiseReduction`, `mpegNoiseReduction`, `smoothGradation`, `realCinema`, `truMotionMode` | curseur, listes | Dépendent du signal et du contenu, pas de la lumière | — | — | **Non** | Élevée |
| Mode Sélection | `pictureMode` | liste | Les modes sont présentés « selon votre environnement » par le guide ; bascule jour / nuit concevable | Bascule par ambiance | Réinitialise tous les réglages du mode ; contrarie le choix de l'utilisateur ; notre fonction suit déjà chaque changement de mode | **Non intégré** ; automatisation de l'utilisateur sur les entités « Lux filtré » et « Ambiance » (R14a) | Moyenne |
| Fonction Économie d'énergie | `energySaving` | liste | Régulation native par le capteur du téléviseur | Désactivation sur demande (R2) | Conflit | Détection (R2) | Élevée |
| Plage vidéo | `blackLevel` | lecture seule | Dépend du signal de la source | — | — | **Non** | Élevée |
| Réglages du son | `sound.*` | — | Hors du sujet de la lumière | — | — | Hors périmètre | — |

Réglages du menu **inaccessibles par l'API**, signalés seulement :
Amplificateur d'expression, Détail presque noir, Luminosité minimale de
l'économie d'énergie, Lumière ambiante du MODE FILMMAKER, Paramètres de
luminosité AI. Ils restent « À régler sur la TV ».

**HDR et Dolby Vision.** En PQ, la luminance est absolue et la luminosité
OLED vaut 100 par défaut ; la baisser réduit tout, hautes lumières
comprises. Les modes HDR restent exclus par défaut de la luminosité
adaptative ; pour un utilisateur qui les inclut, le levier pertinent est
le Mappage des tons dynamiques (ligne ci-dessus) et, s'il existe sur le G5,
Dolby Vision IQ.

#### 3.6.3 Gamma et niveau du noir : ce que donnent les chiffres

- **Gamma.** D'après le § 3.0, passer de 5 à 500 lx justifie environ
  −0,15 de gamma ; 0,03 est « just visible » pour un expert en comparaison
  côte à côte (BT.2408). Le cran BT.1886 (2,4) → 2.2 vaut −0,2 : il dépasse
  la correction normative même à 500 lx. La règle des étalonneurs (2.2 en
  pièce claire) compense aussi les **reflets sur l'écran**, que la formule
  de la BBC, qui porte sur l'adaptation de l'œil à l'entourage, ne prend pas
  en compte [Supposé]. Proposition : bascule vers 2.2 seulement au-delà
  d'environ 200 à 300 lx, retour sous la moitié de ce seuil, au plus une
  bascule par demi-heure, et jamais dans un mode laissé de côté.
- **Niveau du noir.** La lumière ambiante renvoyée par l'écran s'ajoute au
  noir : `L_reflet ≈ E × R / π`. Avec une réflectance diffuse de 1 %, valeur
  **purement illustrative** (celle du G5 n'est pas publiée, à mesurer), cela
  donne environ 0,02 cd/m² à 5 lx, 0,16 cd/m² à 50 lx et 0,6 cd/m² à 200 lx.
  Or le seuil de détection d'un noir descend sous 0,004 cd/m² dans un
  entourage sombre (BT.2390 § 2, travaux de Mantiuk). En pièce claire, les
  premiers niveaux de gris disparaissent donc sous le reflet : relever le
  noir les rend visibles, comme le prévoit la procédure PLUGE réalisée sous
  l'éclairage réel. C'est **mesurable par l'utilisateur** sans instrument
  (P9).

#### 3.6.4 Un mécanisme commun : les ambiances

Plutôt qu'une fonction par réglage, je propose deux étages.

**R14a — Exposer l'état de la pièce** (effort faible, recommandé) : deux
entités nouvelles, « Lux filtré » (le signal de R1, lissé et confirmé) et
« Ambiance » (`sombre`, `intermédiaire`, `claire`, seuils réglables avec
hystérésis et durée minimale de 10 min). Toute automatisation peut alors
basculer un réglage avec l'action `lg_webos_tv.regler` (garde de mode
comprise) sans recalculer le filtrage. Le README donne deux exemples
(gamma, Luminosité maximale).

**R14b — Ambiances intégrées** (effort élevé, plus tard) : pour chaque
ambiance, une valeur facultative par réglage discret retenu (gamma,
Luminosité maximale, Contraste dynamique, Mappage des tons dynamiques en
HDR, Protection des yeux) et un décalage du niveau du noir. Règles :

- changement appliqué seulement quand l'ambiance est stable depuis la durée
  minimale, ou à l'allumage, ou à un changement de mode ou d'entrée (le
  saut passe alors inaperçu) ;
- **reprise en main par réglage** : un changement manuel d'un réglage met en
  pause son seul pilotage, comme aujourd'hui pour la luminosité ;
- **valeur de base** : la valeur de l'utilisateur, relue sur le téléviseur
  par mode (jamais supposée), est restaurée quand l'ambiance qui l'avait
  modifiée prend fin ou quand la fonction est désactivée ;
- modes laissés de côté respectés ; `eyeComfortMode` traité à part
  (réglage global, état « Soirée »).

**R15 — Soirée** : état horaire et non lumineux (une heure de début, ou une
entité Home Assistant `input_datetime` ou `binary_sensor` choisie). Pendant
la soirée : Réduire la lumière bleue activé (facultatif) et plafond de
luminosité abaissé (−20 points proposés, à confirmer en P11), conformément à
Brown et al. (dimming d'abord). Fin à l'heure de fin, à l'extinction du
téléviseur ou par « Reprendre ». Textes sans promesse de santé.

**R16 — Niveau noir compensé** : décalage du niveau du noir interpolé sur
log(lux) entre deux ou trois points relevés par l'utilisateur avec une mire
PLUGE (assistant du panneau : afficher la mire depuis une source, régler
jusqu'à ce que la bande la plus sombre disparaisse et que la plus claire
reste visible, valider ; le lux est noté). Borné à +5 points par rapport à
la valeur de base. Désactivé si P9 ne montre pas d'écart utile.

### 3.7 Contexte domotique

| Entrée | Usage possible | Analyse | Verdict |
|---|---|---|---|
| Lumières et volets de la pièce | **Accélérateur** : une lampe ou un volet qui change d'état dans la pièce du téléviseur ouvre une fenêtre de 30 s sans confirmation ni lissage en montée | Réduit le retard visible là où il gêne le plus. Sans valeur de lux, aucune cible fiable à anticiper | Option, priorité basse (confiance moyenne) |
| Élévation du soleil | Anticipation, ou secours sans capteur | La lumière du jour intérieure dépend des volets, de l'orientation, des nuages : trop indirect | Non |
| Heure | Soirée : plafond de luminosité, réduction de la lumière bleue | Fondé sur la lumière reçue à l'œil avant le coucher (Brown et al., 2022), pas sur l'ambiance | État « Soirée » (R15) ; décalage pilotable (R11) pour le reste |
| Présence | — | Téléviseur allumé sans personne : sans enjeu | Non |
| Entrée ou application (jeu, film) | Courbe différente par usage | Déjà couvert, en grande partie, par les modes d'image laissés de côté ; demanderait un nouvel abonnement dans `televiseur.py` | Non pour l'instant |

**Recommandation (R11)** : plutôt que d'intégrer chaque contexte, exposer
une entité `number` « Décalage de la luminosité adaptative » (−30 à +30
points, ajouté à la cible, borné à 0–100). Les automatisations de
l'utilisateur la règlent selon l'heure, la présence ou l'application, avec
les outils de Home Assistant. Peu de code, aucune hypothèse sur la maison
de l'utilisateur. Confiance moyenne.

### 3.8 Reprise en main et apprentissage

**État de l'art.** [Source]

- Android, modèle court terme : une correction de l'utilisateur déforme la
  courbe (correction gamma bornée à ×3, `config_autoBrightnessAdjustmentMaxGamma`
  = 300 %), et son effet est oublié après 5 minutes
  (`config_autoBrightnessShortTermModelTimeout`) ou quand la lumière change
  nettement.
- Android 9, long terme : un modèle appris sur l'appareil, conçu avec
  DeepMind, entraîné la nuit pendant la charge. Google rapporte qu'après une
  semaine, près de la moitié des testeurs internes faisaient moins de
  corrections manuelles, et que les interactions avec le curseur avaient
  baissé de plus de 10 %. Ce sont des chiffres de Google, non vérifiés de
  façon indépendante.

**Notre cas diffère** : peu de corrections (quelques-unes par semaine), et
une correction peut dire « ce film est sombre » plutôt que « cette ambiance
appelle plus de lumière ». Un modèle appris en silence dériverait sur peu
de données bruitées.

**Options classées.**

1. **Pause plus intelligente (R7)** : la pause actuelle reste, mais se lève
   aussi quand le lux filtré change d'un facteur 2 depuis la correction
   (même idée qu'Android : la correction valait pour *cette* ambiance).
   Peu de code. Recommandé.
2. **Suggestions validées (R8)** : chaque correction gardée au moins
   10 minutes (non suivie d'une autre), lux stable, est enregistrée :
   lux filtré, valeur gardée, cible de la courbe, mode, entrée, heure.
   Quand au moins 3 corrections d'une même plage de lux (une demi-décade)
   s'écartent de la courbe dans le même sens d'au moins 5 points (médiane),
   le panneau propose « Vos réglages manuels suggèrent +8 en pièce sombre.
   Appliquer ? », avec l'aperçu de la courbe modifiée. L'utilisateur garde
   la main, rien ne dérive. Recommandé (confiance moyenne).
3. **Décalage conservé** (au lieu d'une pause) : la fonction continue en
   gardant l'écart choisi par l'utilisateur. Plus fluide, mais garde
   l'écart d'un réglage fait pour un contenu particulier. En option au
   mieux.
4. **Apprentissage automatique** de la courbe : écarté pour l'instant
   (risque de dérive, opacité), à réexaminer avec des données réelles des
   suggestions.

**État à conserver** : table `corrections` dans la base SQLite
`<config>/lg_webos_tv/`, donc dans les sauvegardes. Purge au-delà de
365 jours ou de 500 lignes. **Transparence** : les corrections apparaissent
en points sur la courbe du panneau, avec un bouton « Oublier ».

### 3.9 Diagnostics et accompagnement

Détail au § 4.5. Principes :

- Statistiques glissantes **calculées par la fonction elle-même** (sans
  dépendre du recorder de Home Assistant, que l'utilisateur peut avoir
  restreint), agrégées par jour et conservées 30 jours.
- **Un diagnostic dit ce qui ne va pas, pourquoi, et quoi faire**, avec le
  chiffre qui le justifie.
- Deux niveaux : informations dans le panneau ; **Réparation** Home
  Assistant (comme `ecriture_impossible`) seulement pour ce qui empêche la
  fonction de marcher (conflit avec l'économie d'énergie, capteur figé).

### 3.10 Usure de l'OLED et limitation automatique de luminosité

Ce qui change réellement, sans exagérer :

- **Usure** : la durée de vie d'une OLED suit en première approximation
  `L^n × T = constante`, avec un facteur d'accélération n de l'ordre de
  1,6 à 1,8 selon les matériaux [Source : littérature et brevets ; ajusté
  par empilement, pas universel]. Baisser la luminance de 20 % allonge
  donc la durée de vie liée à la luminance d'environ 1,25^1,7 ≈ 1,46
  **pour les mêmes contenus**. L'essai longue durée de RTINGS montre que la
  rémanence dépend surtout des contenus statiques (chaînes d'information à
  luminosité maximale) et que les dalles récentes, plus lumineuses, n'ont
  pas moins de rémanence que les anciennes à pleine puissance [Source].
  **Conclusion honnête** : baisser la luminosité dans le noir réduit l'usure,
  mais l'effet compte surtout pour les contenus statiques ; on peut le dire
  comme un bénéfice secondaire, pas le vendre comme une protection.
- **Limitation automatique de luminosité (ABL)** : sur une image claire
  plein écran, le téléviseur plafonne lui-même la puissance. La luminosité
  OLED change donc surtout les images moyennes et les petites zones
  lumineuses ; sur une image très claire, passer de 100 à 85 peut se voir
  peu. [Supposé, mécanisme connu des OLED ; amplitude sur le G5 à vérifier]
  Conséquence pratique : la rétroaction est la plus forte sur les images
  claires, celles où notre réglage agit le moins.
- Notre fonction ne touche à aucune fonction de maintenance OLED.

---

## 4. Ce que l'application propose

### 4.1 Profils de capteurs

Détection à l'ajout du capteur, puis confirmée par l'observation (24 h) :

```
profil = selon(plateforme, fabricant/modèle connus)      # point de départ
       → ajusté par intervalle observé, résolution, saturation
```

Table embarquée `profils-capteurs.json` (fabricant / modèle → profil,
plage connue, conseil de configuration), **remplie seulement de valeurs
sourcées**, les autres laissées vides (« à vérifier ») et complétées par
l'observation. Textes indicatifs :

> **Capteur détecté : Aqara T1 (Zigbee2MQTT).** Ce capteur publie sur
> variation. Réglez sa « période de détection » au plus court
> (Zigbee2MQTT › appareil › Exposes) pour suivre une lampe qu'on allume.

> **Capteur ESPHome.** Une mesure toutes les 2 à 5 s suffit
> (`update_interval: 5s`). Inutile de filtrer dans ESPHome : la fonction
> lisse elle-même.

> **Capteur Z-Wave à seuil élevé.** Ce capteur ne signale un changement
> qu'au-delà de 200 lx : dans une pièce de télévision, il ne bougera
> presque jamais. Abaissez le seuil de rapport dans ses paramètres.

### 4.2 Guide de placement

Schéma vu de dessus (SVG du panneau, sans logo ni dessin LG) :

```
            mur
  ┌──────────────────────────┐
  │   [B]  ▀▀▀▀▀▀▀▀▀▀  (TV)  │   B : derrière, tourné vers le mur
  │  [A]→              ←[A]  │   A : à côté de l'écran, vers la pièce  ✔
  │            [C]           │   C : plafond, vers le bas
  │                          │
  │  fenêtre [F]             │   F : près d'une fenêtre                ✘ seul
  │            [E]↑ [D]↑     │   D : au canapé, vers l'écran           ✘
  │          (canapé)        │   E : au canapé, vers le haut
  └──────────────────────────┘   G : extérieur                         ✘ seul
```

Textes par emplacement (indicatifs) :

- **A — À côté de l'écran, tourné vers la pièce (recommandé).** Il mesure
  la lumière qui tombe sur l'écran, celle qui crée les reflets et fait
  paraître l'image terne. L'écran l'éclaire peu. Évitez qu'une fenêtre ou
  une lampe le vise directement.
- **B — Derrière le téléviseur, tourné vers le mur.** Il mesure la clarté
  du mur autour de l'image, ce que vos yeux voient autour de l'écran. Les
  valeurs sont plus basses : la mise en route en tient compte.
- **C — Au plafond.** Convient, surtout loin d'une suspension. Une lampe
  proche peut dominer la mesure.
- **D — Au canapé, tourné vers l'écran.** À éviter : l'écran éclaire le
  capteur, et la luminosité suivrait les scènes claires et sombres. Si vous
  ne pouvez pas le déplacer, la fonction réduit sa réactivité.
- **E — Au canapé, tourné vers le haut.** Convient ; une lampe de lecture
  proche peut fausser la mesure.
- **F — Près d'une fenêtre.** Il voit surtout le jour ; le soir, il
  ignore vos lampes. Préférez un capteur intérieur, celui-ci en secours.
- **G — Extérieur.** Ne mesure pas votre pièce. En secours seulement.

### 4.3 Combinaisons

Formulaire : un capteur principal, un capteur de secours facultatif
(R12). Le panneau affiche, quand les deux publient, leur rapport habituel
et signale une incohérence (§ 3.5).

### 4.4 Valeurs par défaut

| Option | Actuel | Proposé | Justification |
|---|---|---|---|
| Points de la courbe | 5 lx → 40 ; 300 lx → 100 | identiques + point intermédiaire facultatif | en attente de P3 et P7 ; le point d'ancrage cale l'utilisateur |
| Écart minimal | 3 | 3, puis 2 avec les rampes | l'hystérésis sur le lux prend le relais |
| Lissage montée / descente | — | 5 s / 15 s | ordre de grandeur Android (4 s / 8 s), capteurs plus lents |
| Hystérésis | — | +10 % / −20 % | AOSP |
| Confirmation des sauts | — | 8 s au-delà d'un facteur 4 | compromis retard / rejet |
| Gel après écriture | — | 5 s (placement D : 20 s) | délai du capteur |
| Rampe | — | 4 points par seconde | à confirmer (P4) |
| Pause | 120 min | 120 min, **ou** lux ×2 / ÷2 | R7 |
| Modes laissés de côté | FILMMAKER, Expert 1 et 2, HDR | identiques | modes calibrés ; la compensation native FILMMAKER existe |

Les options avancées (lissage, hystérésis, confirmation, gel, rampe) ne
sont pas montrées par défaut : elles dérivent du profil et du placement.

### 4.5 Diagnostics

Seuils proposés, à ajuster après l'essai réel.

| Diagnostic | Détection | Message (indicatif) | Action proposée |
|---|---|---|---|
| Conflit avec l'économie d'énergie | `energySaving` ≠ `off`, ou mode `eco` | « La fonction Économie d'énergie du téléviseur règle déjà la luminosité selon son propre capteur. Les deux se contrarient. » | Bouton « Désactiver l'économie d'énergie automatique » ; Réparation HA |
| Capteur trop lent | intervalle médian > 5 min, téléviseur allumé | « Votre capteur donne une mesure toutes les 12 min en moyenne : la luminosité suit avec ce retard. » | conseil du profil |
| Capteur trop grossier | plus petit pas > 20 % de la valeur sous 20 lx, ou valeurs entières sous 10 lx | « Sous 10 lx, votre capteur ne mesure que des valeurs entières : en pièce sombre, la courbe avance par sauts. » | relever « Pièce sombre » ou changer de capteur |
| Saturation | même maximum atteint de façon répétée et ≥ 80 % du temps au-dessus de `lux_max` ; ou 0 / plancher la plupart du temps | « Votre capteur plafonne à 54 612 lx » / « votre capteur affiche 0 dans le noir » | information ; plancher traité comme `lux_min` |
| Capteur figé | `last_reported` ancien (§ 3.1) | « Aucune mesure depuis 3 h alors que le téléviseur est allumé. Pile ? Réseau Zigbee ? » | Réparation HA ; luminosité figée |
| Courbe calée de travers | > 80 % du temps actif à une borne sur 7 jours | « Depuis une semaine, la luminosité reste au maximum 85 % du temps : la pièce est plus claire que prévu par la courbe. » | proposer `lux_max` = 90ᵉ centile du lux observé |
| Allers-retours | ≥ 3 inversions de sens en 10 min, lux sans tendance | « La luminosité change de sens souvent : mesure instable. » | augmenter le lissage ou l'hystérésis (bouton) |
| Rétroaction | contribution estimée (§ 3.4) > 30 % du lux courant en pièce sombre, ou placement D déclaré | « Votre capteur voit l'écran : environ 9 lx de sa mesure viennent du téléviseur. La luminosité suit les scènes. » | déplacer le capteur (schéma) ; gel prolongé |
| Pauses fréquentes | ≥ 1 reprise en main par jour sur 7 jours | « Vous avez corrigé la luminosité 9 fois cette semaine, surtout en pièce sombre (+8 en moyenne). » | suggestion de courbe (R8) |
| Écritures refusées | écritures non confirmées répétées | « Le téléviseur n'applique pas les changements. » | renvoi vers l'état d'écriture |
| Pièces différentes | capteur et téléviseur dans deux pièces différentes du registre | « Ce capteur est dans le Bureau, le téléviseur dans le Salon. » | information |

### 4.6 Parcours de mise en route

Ordre : d'abord ce qui conditionne la réussite (capteur, placement,
conflits), ensuite la préférence.

1. **Capteur.** Liste triée : capteurs de la pièce du téléviseur d'abord,
   puis ceux qui ont publié dans l'heure, puis les autres. Pour chacun :
   valeur actuelle, âge de la dernière mesure, profil détecté. Capteur de
   secours facultatif (plus tard).
2. **Emplacement.** « Où est ce capteur ? » (A à G, schéma). Message
   immédiat si D, F ou G.
3. **Vérifications automatiques.** Économie d'énergie, mode Éco, mode actuel
   laissé de côté, capteur qui répond. Chaque problème a son bouton ou son
   explication.
4. **Point d'ancrage.** « Réglez maintenant la luminosité qui vous convient
   dans l'éclairage actuel. » Le curseur écrit en direct (par la file,
   origine `panneau`, sans mettre la fonction en pause pendant l'assistant).
   Le couple (lux filtré, valeur) **décale la courbe en log(lux)** pour
   passer par ce point, pente conservée.
5. **Activation**, avec la phrase « Dans les prochains jours, la page vous
   dira si l'installation fonctionne bien. »
6. **Plus tard (relance du panneau)** : « Ce soir, dans le noir,
   refaites le réglage » → deuxième point : la pente est alors calée sur
   l'utilisateur aussi.

### 4.7 Maquettes

**Formulaire des options (Home Assistant), version simple :**

```
┌ Luminosité adaptative ─────────────────────────────────────┐
│ Capteur de luminosité ambiante   [ Salon – Lux (Aqara T1) ▾]│
│ Emplacement du capteur           [ À côté de l'écran     ▾]│
│ Capteur de secours (facultatif)  [                       ▾]│
│ Pièce sombre            [   5 ] lx   Luminosité  [  40 ]    │
│ Pièce intermédiaire     [  40 ] lx   Luminosité  [     ]    │  ← facultatif
│ Pièce lumineuse         [ 300 ] lx   Luminosité  [ 100 ]    │
│ Pause après un réglage manuel        [ 120 ] min            │
│ ☑ Reprendre quand l'éclairage change nettement              │
│ Modes d'image laissés de côté        [ FILMMAKER, Expert…▾] │
│ ▸ Réglages avancés (lissage, hystérésis, rampe)             │
└─────────────────────────────────────────────────────────────┘
```

**Page du panneau :**

```
┌ Luminosité adaptative ─────────────────────── [Pause 1 h] ─┐
│ ● Active — 18 lx (filtré) → cible 62 · téléviseur 62        │
│   Mode d'image : Standard (réglages propres à ce mode)      │
├ Santé de l'installation ────────────────────────────────────┤
│ ⚠ Économie d'énergie Auto active sur le téléviseur          │
│   Les deux régulations se contrarient. [Désactiver]          │
│ ✓ Capteur : une mesure toutes les 40 s, résolution 1 lx      │
│ ⓘ Votre capteur semble voir l'écran (≈ 6 lx). [Pourquoi ?]  │
│ ⓘ Protection des yeux active : la luminosité varie aussi     │
│   selon les images.                                          │
├ Ambiance et soirée ──────────────────────────────────────────┤
│ Ambiance : intermédiaire (depuis 21:05)   Soirée : depuis 21:30│
│   Plafond −20 · Réduire la lumière bleue : activé            │
│   Gamma 2.2 au-delà de 250 lx : désactivé    [Configurer]    │
├ Courbe ──────────────────────────────────────────────────────┤
│ 100 ┤                         ●━━━━━━                        │
│     │                  ━━━━━━┛    ○ correction (12/10)      │
│  50 ┤      ○  ━━━━━━━┛                                       │
│     │━━━━━●                                                  │
│   0 ┼────┬─────┬──────┬──────┬───── lx (échelle log)         │
│      1   10   100   1000  10000      ▲ mesure actuelle      │
│ Suggestion : +6 en pièce sombre (4 corrections). [Aperçu]    │
├ Journal ─────────────────────────────────────────────────────┤
│ 21:42 rampe 70 → 62 (12 lx)   21:10 pause : télécommande …   │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Impact technique

### 5.1 Architecture

Contraintes respectées : état jamais optimiste, écritures par la file
coalescente, accès au téléviseur limité à `televiseur.py`, options dans
l'entrée de configuration, rien de bloquant dans la boucle.

- **Nouveau module pur `courbe_lux.py`** (nom à choisir), sans Home
  Assistant : courbe à points, filtre irrégulier asymétrique, hystérésis,
  confirmation des sauts, planification des pas d'une rampe, estimateur de
  rétroaction, statistiques de diagnostic. Testable avec des séries
  synthétiques horodatées, comme `televiseur.py` l'est sans Home Assistant.
- **`luminosite_adaptative.py`** reste l'orchestrateur : abonnements aux
  capteurs (principal, secours), `async_track_state_report_event` pour
  `last_reported` (helper à confirmer dans la version de Home Assistant
  visée, **à vérifier**), état « capteur figé » et « conflit », rampes.
- **Rampes** : chaque pas passe par `FileEcritures.demander` et attend sa
  confirmation avant le suivant ; la cible courante vit dans la fonction,
  l'état affiché reste celui du téléviseur. Une écriture non confirmée
  arrête la rampe.
- **Historique des rampes** : `restauration.ecrire` gagnerait un paramètre
  `historiser=False` pour les pas intermédiaires, et une entrée unique
  serait écrite à la fin (ancienne = départ, nouvelle = arrivée). Le retour
  arrière d'une rampe restaure le départ. Sous réserve de l'arbitrage A5.
- **`televiseur.py`** : inchangé pour les lots 1 à 5. `energySaving` et
  `pictureMode` y sont déjà suivis. Seuls l'application active ou une
  éventuelle lecture du capteur du téléviseur demanderaient de nouveaux
  appels (non retenus).
- **Registres** : registre des entités et des appareils pour la plateforme,
  le fabricant, le modèle et la pièce (lecture seule, dans la boucle, sans
  entrée/sortie).
- **Persistance** : base SQLite existante, tables `corrections` et
  `stats_luminosite` (agrégats journaliers, 30 jours), accès hors boucle
  comme l'historique. Le journal en mémoire reste.
- **Panneau** : nouvelles commandes websocket `lg_webos_tv/luminosite_adaptative/…`
  `diagnostic`, `ancrer`, `suggestions`, `appliquer_suggestion`,
  `oublier_correction` ; `configuration` enrichie (profil, pièce, âge de la
  mesure par capteur). Toujours réservées aux administrateurs.
- **Entité facultative** : `number` « Décalage » (R11), dans la catégorie
  configuration ; attributs de l'état : lux filtré, profil, placement.
- **Réparations** : deux nouveaux problèmes (`conflit_economie_energie`,
  `capteur_fige`), sur le modèle de `ecriture_impossible`.
- **Autres réglages (lot 7)** : généraliser l'orchestrateur en « pilotes »
  par réglage (continu pour `backlight` et le décalage du niveau du noir,
  discret pour le gamma, la soirée et les ambiances), chacun avec sa propre
  reprise en main (origine notifiée ou historisée, clé par clé) et sa
  **valeur de base** relue sur le téléviseur et conservée par mode (et par
  entrée pour les 5 curseurs dont le descripteur l'indique). Toutes les
  écritures restent dans la file coalescente, avec la garde de mode, sauf
  pour `eyeComfortMode`, global. Prérequis : la correction de
  `arbre.mode_dependant` (§ 8.3) si P10 la confirme.

### 5.2 Migration des options

Les options sont lues par `{**OPTIONS_LUMINOSITE_DEFAUT, **options}` : toute
nouvelle clé avec une valeur par défaut est **rétrocompatible sans
migration**. Recommandation :

- garder `lux_min`, `lux_max`, `luminosite_min`, `luminosite_max` comme
  extrémités de la courbe, et ajouter `point_intermediaire` facultatif
  (`[lux, luminosité]` ou absent) ; pas de liste libre de points, plus
  difficile à éditer dans le formulaire ;
- nouvelles clés : `emplacement_capteur` (défaut `inconnu`),
  `capteur_secours`, `reprise_sur_changement` (défaut vrai : changement de
  comportement à annoncer dans le CHANGELOG), et les options avancées
  (défauts du profil quand elles sont absentes) ;
- `valider_options` et sa copie JavaScript (`luminosite.js`) étendues
  ensemble ; un fichier de vecteurs de test partagé entre pytest et le
  panneau éviterait que les deux calculs divergent (il n'y a pas de tests
  du panneau aujourd'hui : à prévoir avec un petit script Node).
- `ConfigFlow.VERSION` inchangé ; un `MINOR_VERSION` et
  `async_migrate_entry` ne seraient nécessaires que si l'on renommait des
  clés : à éviter.

### 5.3 Tests à prévoir

- Module pur : filtre à pas irréguliers (capteur à 1 s, 60 s, 5 min, sur
  variation), asymétrie, hystérésis (aucune écriture sur un bruit de ±1 lx
  à 5 lx), confirmation des sauts, débit au lieu du rebond (flux à 0,5 s →
  application), courbe à 3 points monotone, point d'ancrage, plan de rampe.
- Orchestrateur (`pytest-homeassistant-custom-component`, horloge simulée) :
  capteur figé, conflit `energySaving`, rampe interrompue par une reprise en
  main, cible changée en cours de rampe, rampe et changement de mode
  (garde de mode), une seule entrée d'historique par rampe, levée de pause
  sur lux ×2, capteur de secours.
- Diagnostics : séries synthétiques pour chaque ligne du § 4.5, dont la
  rétroaction (lux +6 à chaque allumage) et les fausses alertes
  (extinction suivie d'une lampe allumée).
- Websocket : nouvelles commandes, droits administrateur.
- Rétrocompatibilité : options 2.4.0 sans les nouvelles clés → comportement
  identique, filtre excepté.

---

## 6. Protocole d'essai réel

À mener par vous ; les scripts d'appoint iraient dans `outils/scripts/`.
Les relevés sont à consigner dans `docs/` (pas de donnée personnelle).

**Quand mener chaque essai.** Les essais valident les recommandations, ils
ne les cadrent pas : aucun n'est un préalable au lot 1. Seuls P5 bis, P9 et
P10 conditionnent un lot (le 7), en une séance d'environ une heure.

| Essai | Moment |
|---|---|
| P1, P2 | remplacés par les mesures automatiques des diagnostics (lot 3), faites sur chaque installation ; relevés manuels facultatifs |
| P3 | abandonné, sauf si les suggestions du lot 5 révèlent une courbe mal formée |
| P5 | essai réel du lot 1 |
| P4 | essai réel du lot 2 |
| P6 | essai réel du lot 6 (capteur de secours) |
| P7 | essai réel du lot 4 (point d'ancrage) |
| P5 bis, P9, P10 | **avant** le lot 7 |
| P11 | essai réel du lot 7 |
| P8 | après chaque lot livré |

**Matériel.** Les capteurs disponibles (au moins un rapide, ESPHome si
possible, et un Zigbee) ; un luxmètre, ou à défaut un téléphone avec une
application de luxmètre (mesures **relatives** seulement) ; des mires plein
écran noir, gris 50 %, blanc 100 % et une fenêtre blanche à 10 % (clé USB
ou vidéo) ; l'export de l'historique Home Assistant des capteurs.

| Essai | But | Mode opératoire | Résultat attendu |
|---|---|---|---|
| **P1 Caractérisation des capteurs** | profils | Une heure lumière stable, téléviseur éteint : intervalle entre mesures, bruit, plus petit pas. Noir complet : plancher. Lampe torche à 10 cm : saturation | tableau par capteur ; complète le § 3.2 |
| **P2 Rétroaction par emplacement** | valider le § 3.4 | Pièce sombre stable. Pour chaque emplacement A à E et OLED 40 / 70 / 100 : lux téléviseur éteint, puis mire noire, grise, blanche (attendre 2 mesures stables) | contribution en lx par emplacement ; coefficient k ; comparer au tableau du § 3.4 |
| **P3 Réponse de l'écran** | modèle perceptif ou non | Fenêtre blanche à 10 % (évite l'ABL), luxmètre au contact du centre, OLED de 0 à 100 par pas de 10, modes Standard et Cinéma | courbe relative luminance / valeur OLED ; décide de garder l'interpolation simple (§ 3.1) |
| **P4 Écritures en rampe** | R4 | Script : pas de 1 point toutes les 0,25 s, de 2 points toutes les 0,5 s, de 5 points par seconde, de 40 à 100 et retour, sur une mire grise puis du contenu réel. Puis 4 écritures par seconde pendant 2 min, et 1 par seconde pendant 10 min | pas visibles ou non ; lissage propre du téléviseur ; toutes les écritures confirmées ; aucun refus 1008 ; aucune alerte visible ; latence par pas |
| **P5 Cohabitation** | R2 | Économie d'énergie Auto, puis mode Éco : faire varier la lumière de la pièce, suivre les notifications de `backlight` (`diag_origine.py`, champ `caller`), puis écrire `backlight`. Idem avec Paramètres de luminosité AI et Lumière ambiante FILMMAKER | la fonction native change-t-elle la valeur notifiée ? avec quel `caller` ? notre écriture tient-elle ? |
| **P5 bis Gamma** | R13 | Écrire `gamma` = `low`, `medium`, `high1`, `high2` en mode Standard puis Expert, lire le libellé affiché dans le menu | correspondance API ↔ libellés (point ouvert de `menu_tree`) |
| **P6 Étalonnage croisé** | R12 | Capteurs côte à côte et luxmètre, 5 niveaux (noir, lampe, plafonnier, jour couvert, jour clair) | facteur relatif entre capteurs ; linéarité |
| **P7 Préférence** | courbe par défaut, point d'ancrage | Dans 5 ambiances (noir, lampe seule, soirée, jour couvert, plein jour), régler la luminosité préférée sur un contenu habituel ; noter le lux de chaque capteur | 5 points de préférence ; comparer à la courbe par défaut et au calage par un ou deux points |
| **P9 PLUGE sous plusieurs éclairages** | R16, intérêt du niveau noir compensé | Mire PLUGE (BT.814) affichée depuis une source (fichier de mires) en mode Standard ; à 3 éclairages (noir, lampe, jour), capteur en A : régler Niveau noir jusqu'à ce que la bande la plus sombre disparaisse et que la plus claire reste visible ; noter la valeur et le lux | courbe niveau noir / lux ; si l'écart ne dépasse pas 1 point, R16 est abandonné |
| **P10 Réglages discrets et réglages globaux** | R14b, R15 | Pour `eyeComfortMode`, `motionEyeCare`, `peakBrightness`, `dynamicContrast`, `gamma`, `hdrDynamicToneMapping` : écrire dans un mode, passer dans un autre, relire (propre au mode ou global ?) ; effet de Réduire la lumière bleue en FILMMAKER ; Protection des yeux active sur un contenu variable : la valeur `backlight` notifiée change-t-elle ? | carte « propre au mode / global » ; corrige au besoin `arbre.mode_dependant` (§ 8.3) |
| **P11 Lumière reçue à l'œil** | R15 | Luxmètre au point de vue, tourné vers l'écran, pièce noire, contenu courant, OLED 40 / 70 / 100, avec et sans Réduire la lumière bleue | éclairement photopique à l'œil (l'éclairement mélanopique exige un spectromètre : à vérifier) ; calibre le plafond de soirée |
| **P8 Validation d'une semaine** | critères de réussite | Version de test avec le lot 1 (et 2), usage normal | compter les reprises en main, les inversions, les diagnostics ; impression subjective |

**Critères de réussite proposés.**

- Lumière stable : au plus une écriture par 10 minutes, aucune inversion.
- Lampe allumée ou éteinte : nouvelle luminosité atteinte en moins de
  « intervalle du capteur + 15 s », sans saut visible (avec les rampes).
- Capteur placé en A : contribution de l'écran inférieure à 20 % de la mesure
  en pièce sombre (P2).
- Après calage par deux points : la cible s'écarte de moins de 5 points de la
  préférence dans au moins 4 des 5 ambiances de P7.
- Semaine de validation : moins d'une reprise en main par jour en moyenne,
  aucun diagnostic faux constaté.

---

## 7. Lots de mise en œuvre proposés

Dans l'ordre ; chacun livrable seul, validé par vous avant le suivant.

| Lot | Contenu | Prérequis | Version indicative |
|---|---|---|---|
| **1 — Signal fiable et cohabitation** | R1 (filtre, hystérésis, confirmation, débit au lieu du rebond, capteur figé, gel après écriture), R2 (conflit économie d'énergie et mode Éco, Réparation), R3 (emplacement du capteur, textes, schéma), profils minimaux (plateforme + intervalle observé) | — (P5 à l'essai réel) | 2.5.0 |
| **2 — Rampes** | R4, entrée d'historique unique par rampe, écart minimal à 2 | lot 1 ; arbitrage A5 (P4 à l'essai réel) | 2.6.0 |
| **3 — Santé de l'installation** | R5 : statistiques journalières, diagnostics du § 4.5 (rétroaction comprise), page du panneau | lot 1 | 2.7.0 |
| **4 — Mise en route guidée** | R6 (pièce, profil, vérifications, point d'ancrage), R9 (point intermédiaire de la courbe) | lots 1, 3 (P7 à l'essai réel) | 2.8.0 |
| **5 — Reprise en main et suggestions** | R7 (levée sur changement d'ambiance), R8 (corrections, suggestions, points sur la courbe) | lot 4 ; arbitrage A2 | 2.9.0 |
| **6 — Options** | R11 (décalage pilotable), R12 (capteur de secours), R14a (entités « Lux filtré » et « Ambiance ») | arbitrage A1 | 2.10.0 |
| **7 — Soirée et autres réglages** | R15 (soirée), R16 (niveau noir compensé), R13 (gamma) ; R14b (ambiances intégrées) écarté pour l'instant (décision A8) | P5 bis, P9, P10 (P11 à l'essai réel) | 7a (R15) : 2.11.0 ; 7b : ultérieur |

Le lot 1 passe en premier pour les raisons du § 1.2 ; les rampes viennent
ensuite parce qu'elles sont le gain le plus visible une fois le signal
fiable ; les diagnostics précèdent la mise en route guidée parce que
celle-ci réutilise leurs détections.

**Lot 2 livré en 2.6.0 : choix de mise en œuvre.**

- La rampe vise la cible **lissée** du moment et ne s'arrête qu'à
  l'arrivée du filtre, au point près : une transition = une rampe, cible
  atteinte exactement. Le filtre garde son rôle anti-bruit et son
  asymétrie ; le prix est une queue de rampe d'environ 1 min en descente
  (τ 15 s, pas d'un point espacés), mesures mises de côté pendant ce temps.
- Débit tenu malgré la latence : un pas lent est rattrapé au suivant, sans
  dépasser deux fois la taille du pas.
- Historique : le **premier pas** est historisé normalement, dans la file,
  donc à sa place parmi les autres écritures (une reprise en main pendant
  la rampe vient après lui, et le retour à un instant donné reste juste) ;
  sa nouvelle valeur est complétée à la fin de la rampe.
- Écart minimal : retiré des options s'il valait 3 (migration 1.1 → 1.2
  de l'entrée), le formulaire l'ayant toujours enregistré.
- P4 se mesure avec `outils/scripts/mesure_rampe.py`.

**Lot 3 livré en 2.7.0 : choix de mise en œuvre.**

- Module pur `sante.py` (agrégats, rétroaction, diagnostics) et
  persistance `statistiques.py` : table `stats_luminosite` dans la base de
  l'historique, une ligne JSON par jour **et par capteur** (changer de
  capteur ne mélange pas les mesures), 30 jours. Les diagnostics sont
  structurés ; leurs textes vivent dans le panneau.
- Capteur trop grossier : le pas est rapporté au lux sombre habituel, mais
  pas sous « Pièce sombre », où la courbe est plate ; la règle « valeurs
  entières sous 10 lx » en devient le cas d'un pas de 1 lx.
- Capteur trop lent : simple information pour un capteur qui ne publie que
  sur variation (Zigbee), qu'une pièce stable fait taire.
- Courbe calée de travers : jugée avec les options du moment (le
  diagnostic disparaît dès la correction appliquée) ; proposition au
  90ᵉ centile seulement si la lumière varie (P90/P10 ≥ 1,5) ; borne basse
  en information seule (décision de l'utilisateur, 25/10/2026).
- Rétroaction : valeur « avant » prise 60 s avant la (dé)connexion du
  téléviseur, faute de connaître le délai entre l'écran et la connexion ;
  « après » = médiane des mesures entre 30 et 150 s ; allumage compté
  seulement après 3 min d'extinction vue ; événements retenus en pièce
  sombre (≤ 50 lx). Chaque mesure est notée au journal pour la vérifier à
  l'essai réel. Si le téléviseur garde la connexion en veille, ce
  diagnostic reste en observation.
- Aucune nouvelle Réparation (arbitrage A6).

**Lot 4 livré en 2.8.0 : choix de mise en œuvre.**

- Module pur `courbe.py` : courbe à 2 ou 3 points, linéaire par morceaux
  sur ln(lux), plate au-delà des extrémités, monotone (plateaux permis) ;
  `point_intermediaire` facultatif (`[lux, luminosité]`), sans migration.
  Copie JS alignée par des vecteurs partagés (`tests/vecteurs_courbe.json`,
  pytest et `npm test`).
- Point d'ancrage à un point : antécédent de la valeur sur la courbe (le
  plus proche du lux mesuré sur un plateau, donc aucun déplacement dans
  une partie plate), puis translation de tous les lux, point
  intermédiaire compris : forme et pente conservées.
- Deux points : transformation affine de ln(lux) qui envoie les deux
  antécédents sur les deux lux mesurés ; le point intermédiaire garde sa
  position relative. Combinés seulement à un facteur 4 au moins de lux
  (sinon le nouveau remplace l'ancien), au plus deux conservés.
- Arbitrages de l'utilisateur (25/10/2026) : valeur hors des bornes →
  borne élargie ; courbe poussée sous 1 lx ou au-delà de 100 000 lx →
  partie hors d'atteinte coupée (comportement identique pour tout lux
  mesurable) ; courbe retouchée → ancrages oubliés ; deuxième point
  contradictoire → le nouveau seul.
- Lux de la courbe au dixième sous 100 lx (à l'unité, un ancrage à 3 lx
  déplaçait la courbe de deux points) ; arrondi choisi pour rester au
  plus près des ancrages (écart ≤ 1 point).
- Pendant la mise en route (abonnement websocket, lié à la connexion) :
  état `mise_en_route`, aucune écriture de la fonction, toute
  modification de la luminosité (curseur, télécommande) ignorée par la
  reprise en main et les statistiques. L'ancrage lit la valeur notifiée
  par le téléviseur, jamais celle du curseur ; refusé dans un mode laissé
  de côté. Abandon sans ancrage : la fonction reprend sa courbe.

**Lot 5 livré en 2.9.0 : choix de mise en œuvre.**

- Module pur `reprise.py` (levée de la pause, corrections, suggestions)
  et persistance `corrections.py` : table `corrections` dans la base de
  l'historique, rattachée au capteur (le lux d'un autre capteur n'est pas
  comparable), un an et 500 lignes au plus. L'entrée HDMI n'est pas
  enregistrée : l'intégration ne la connaît pas (il faudrait un abonnement
  de plus dans `televiseur.py`, exclu pour les lots 1 à 5).
- Levée de la pause (R7) : lux ramenés dans la plage de la courbe
  (au-delà, la courbe est plate et reprendre réécrirait la valeur
  écartée) ; le lux filtré **et** la dernière mesure retenue doivent avoir
  franchi le facteur 2 dans le même sens, à 1 % près (le filtre ne fait
  qu'approcher la nouvelle mesure). La référence est la mesure retenue au
  moment de la reprise en main, vers laquelle allait le filtre : une
  reprise en main pendant une transition vaut pour l'éclairage d'arrivée
  (sans cela, la fin de la transition levait aussitôt la pause). Elle est
  conservée avec la cause de la pause au redémarrage. Une pause demandée
  depuis le panneau n'est jamais levée ainsi (le temps d'un film, lumière
  éteinte) ; toute autre l'est, presets et retours arrière compris.
- Correction retenue : valeur gardée 10 min (un nouveau réglage relance
  le compte), fonction toujours en pause, téléviseur connecté, même mode,
  luminosité relue égale ; lux filtré stable à un rapport 1,5 près, jugé
  une fois le lissage arrivé (4 constantes de temps, 1 min par défaut),
  lux enregistré = moyenne géométrique du minimum et du maximum. Avec une
  pause de moins de 10 min, aucune correction n'est retenue.
- Suggestions (R8) : écart mesuré à la courbe **actuelle** (une suggestion
  appliquée fait tomber ses corrections près de zéro et disparaît d'elle-
  même), 10 corrections les plus récentes par plage. Point visé : lux
  médian (géométrique), cible + écart médian. La luminosité de
  l'extrémité prend la valeur visée au-delà de la courbe ; dans le premier
  ou le dernier tiers d'un segment, le point le plus proche bouge juste
  assez (au plus 1,5 fois l'écart) ; dans le tiers central, ajout du point
  intermédiaire sur une courbe à deux points, translation du segment d'un
  bloc sur une courbe à trois points (le point le plus proche seul aurait
  bougé de deux fois l'écart). Voisins poussés si la monotonie l'exige,
  luminosité bornée à 0–100 (`approche`). Calcul côté intégration
  seulement : le panneau trace la courbe proposée qu'elle envoie, sans
  copie JS du calcul.
- Arbitrages de l'utilisateur (25/10/2026) : seuils de l'étude (3, 5
  points, 10 min) ; ancrages oubliés à l'application d'une suggestion ;
  corrections = réglages isolés (télécommande, autre application, Home
  Assistant, panneau) ; bouton « Ignorer », qui écarte toutes les
  corrections de la plage (gardées à l'affichage).

**Lot 6 livré en 2.10.0 : choix de mise en œuvre.**

- Décalage (R11) : entité `number` restaurée au redémarrage (état de la
  fonction, pas une option : une automatisation peut le changer souvent
  sans réécrire l'entrée de configuration). Cible = courbe + décalage,
  bornée à 0–100 ; un changement relance l'application sans condition
  d'hystérésis, une rampe en cours suit la nouvelle cible. Jamais de
  pause, et une pause en cours n'est pas levée (appliqué à la reprise).
- Arbitrages de l'utilisateur (25/10/2026) : corrections et ancrage
  mesurés à **courbe + décalage du moment** (colonne `decalage` de la
  table `corrections`, 0 pour les anciennes ; une correction en
  observation est écartée si le décalage change) ; seuils d'ambiance
  **tiers de la courbe par défaut, figeables** ; secours utilisé
  **seulement facteur appris et rapport stable** ; **Réparation
  `capteur_fige` conservée** quand le secours relaie (exception assumée à
  A6 : panne matérielle à réparer), texte adapté.
- Secours (R12) : module pur `secours.py`. Échantillons (principal,
  secours) une fois par minute au plus, principal en service, les deux
  disponibles et non figés, filtre arrivé et hors gel ; facteur = médiane
  de ln(l1/l2) sur ceux où les deux dépassent 2 lx, 1 000 gardés, 30 au
  moins ; rapport instable au-delà d'une dispersion robuste (IQR/1,349)
  de ln 1,5 ; incohérent dès 5 échantillons où l'un est à 0 quand l'autre
  dépasse 20 lx. Rapport conservé par paire (table `rapport_capteurs`).
  Un seul filtre pour le lux effectif : à la bascule, la mesure convertie
  entre dans le filtre et la référence d'hystérésis est gardée (aucune
  écriture si le facteur est juste) ; constantes du profil du secours
  pendant le relais. Statistiques du principal (cadence, résolution,
  plancher, plafond), rétroaction et corrections : principal seul ; le
  temps actif et l'histogramme du lux filtré continuent. Seuils de
  départ, à confirmer par P6.
- Ambiance (R14a) : module pur `ambiance.py` (déplace `AMBIANCES` et
  remplace `sante.ambiance`, pour une seule définition des seuils).
  Hystérésis ×1,25 autour du seuil franchi, 10 min continues avant
  publication, première valeur immédiate, état restauré au redémarrage.
  « Lux filtré » au dixième sous 100 lx, suivi tant que le filtre avance,
  quel que soit l'état de la fonction.

**Lot 7a livré en 2.11.0 : choix de mise en œuvre.**

P5 bis, P9 et P10 n'ayant pas été menés, le lot 7 est coupé en deux : 7a
(R15 Soirée, scripts et modes opératoires de la séance, portée de
`eyeComfortMode`) ; 7b (R13 gamma selon l'ambiance, R16 niveau noir
compensé, pilotes par réglage du § 5.1) attend leurs résultats
(`docs/essais-lot7.md`).

- Module pur `soiree.py` : plage quotidienne (passant minuit), sources
  heure, `input_datetime` (son heure, date ignorée), `binary_sensor` et
  `schedule` (début au passage à `on`, fin au retour à `off` ou à l'heure
  de fin) ; « Terminer la soirée » vaut jusqu'à la fin de la plage en
  cours, conservé au redémarrage ; pilote de la lumière bleue.
- Arbitrages de l'utilisateur (25/10/2026) : **baisse en fraction**,
  `(courbe + décalage)` bornée à 0–100 puis × (1 − r), r = 20 % par
  défaut (le plafond de −20 points en haut de la courbe), à confirmer par
  P11 ; un plafond absolu n'aurait eu aucun effet dans une pièce sombre,
  là où l'écran fournit l'essentiel de la lumière à l'œil. **Extinction =
  suspension** : rallumé dans la plage, la Soirée continue ; hors plage,
  la lumière bleue posée est restaurée à la connexion. **Soirée et pause
  indépendantes** : le début ne lève pas une pause (baisse appliquée à la
  reprise, comme le décalage), « Reprendre » ne termine pas la Soirée,
  bouton dédié « Terminer la soirée ». **Lumière bleue pas dans les modes
  laissés de côté** : base restaurée en y entrant, réactivée en sortant.
- Décisions par défaut, validées avec le plan : reprises en main de la
  Soirée **non retenues comme corrections** (une préférence du soir ne
  retouche pas la courbe du jour ; l'écart n'est donc mesuré ni avec ni
  sans la baisse), correction en observation abandonnée au début et à la
  fin ; point d'ancrage refusé pendant la Soirée ; aucune Réparation
  (diagnostic `soiree` de la page Santé : source inutilisable, lumière
  bleue refusée). Le diagnostic « courbe calée de travers », jugé sur
  l'histogramme du lux, n'est pas touché ; les rampes de début et de fin,
  espacées d'heures, ne font pas d'allers-retours.
- Lumière bleue : écrite par la file coalescente sans garde de mode,
  téléviseur connecté et écriture accordée ; « posée » seulement après
  confirmation ; restaurée quand la Soirée finit, quand la fonction est
  désactivée, ou à la connexion suivante ; jamais à l'arrêt de
  l'intégration (un rechargement en pleine Soirée la remettrait aussitôt).
  Reprise en main détectée par la notification (`manuel`,
  `autre_application`) ou par l'historique (entité, panneau, preset,
  retour arrière) ; une notification de notre client n'est pas réévaluée,
  l'historique dit ensuite son origine. Un refus n'est pas retenté avant
  l'événement suivant (connexion, mode, Soirée).
- Correction de `arbre.mode_dependant` (§ 8.3) faite sans P10 : le
  descripteur du téléviseur est la même source qui fonde « la luminosité
  est propre au mode » ; un test recoupe `CLES_GLOBALES` avec
  l'inventaire. Si P10 la contredit, une ligne à retirer.

---

## 8. Points ouverts

### 8.1 Arbitrages qui vous reviennent

| # | Question | Options | Ma recommandation |
|---|---|---|---|
| A1 | **Nombre de capteurs gérés** | un seul ; principal + secours ; fusion de N capteurs | **Principal + secours** (lot 6) : couvre la panne sans réglage de fusion ; la fusion n'apporte qu'à de rares installations |
| A2 | **Apprentissage** | aucun ; suggestions validées ; apprentissage automatique | **Suggestions validées** : le bénéfice d'Android, sans dérive silencieuse ; l'automatique se rediscute sur données réelles |
| A3 | **Complexité de l'interface** | tout visible ; simple + avancé replié ; simple seulement | **Simple + avancé replié** : les options avancées dérivent du profil et de l'emplacement ; l'expert garde la main |
| A4 | **Portée produit** | lots 1 à 5 ; lots 1 à 6 ; lots 1 à 3 seulement | **Lots 1 à 5**, puis le lot 6 au cas par cas : les lots 1 à 5 répondent à « tout utilisateur obtient un bon résultat » ; le lot 6 répond à des besoins particuliers |
| A5 | **Historique des rampes** (décision actée : chaque écriture est historisée) | une entrée par pas ; une entrée par rampe ; pas d'historique pour la fonction | **Une entrée par rampe** : l'historique reste lisible et le retour arrière a un sens ; amender la décision dans `CLAUDE.md` |
| A6 | **Diagnostics en Réparations Home Assistant** | aucun ; seulement les bloquants ; tous | **Seulement les bloquants** (conflit d'économie d'énergie, capteur figé) : le reste est de l'accompagnement, à sa place dans le panneau |
| A7 | **Reprise sur changement d'ambiance activée par défaut** (change le comportement des installations existantes) | oui ; non (option à cocher) | **Oui**, annoncé dans le CHANGELOG : c'est le comportement attendu par la plupart des utilisateurs |
| A8 | **Réglages adaptés au-delà de la luminosité** | aucun ; entités « Lux filtré » et « Ambiance » seulement ; + Soirée, niveau noir et gamma (lot 7) ; + ambiances intégrées pour les autres réglages discrets | **Entités + Soirée, niveau noir et gamma**, ces deux derniers seulement si P9 et P5 bis les justifient ; les ambiances intégrées seulement sur demande, faute de valeurs par défaut fondées |

**Décisions de l'utilisateur (25/10/2026).** Recommandations retenues :
A1 principal + secours ; A2 suggestions validées ; A3 interface simple,
options avancées repliées ; A5 une entrée d'historique par rampe (décision
de `CLAUDE.md` à amender au moment du lot 2) ; A6 Réparations pour les seuls
cas bloquants ; A7 reprise sur changement d'ambiance activée par défaut ;
A8 entités « Lux filtré » et « Ambiance », Soirée, niveau noir et gamma sous
réserve de P9 et P5 bis, sans ambiances intégrées (R14b écarté pour
l'instant). Portée (A4) qui en découle : lots 1 à 7, R14b excepté. Pas de
lot de mesures préalable : chaque essai accompagne le lot qu'il valide
(§ 6).

### 8.2 À vérifier

- Transposition au gamma SDR d'un téléviseur des formules de BT.2390 et
  BT.2408, établies pour le gamma système HLG en production
  (extrapolation, § 3.0).
- Réflectance diffuse de l'écran du G5 (non publiée), qui fixe l'amplitude
  utile du niveau noir compensé (P9).
- Réglages propres au mode ou globaux, hors des 7 clés dont le descripteur
  le dit (P10) ; comportement de Réduire la lumière bleue en FILMMAKER.
- Éclairement mélanopique d'un OLED au point de vue : l'équivalence avec
  l'éclairement photopique pour un blanc D65 est une approximation à
  vérifier.
- Correspondance « Luminosité des pixels OLED » → luminance du G5, par mode
  (P3). Conditionne le choix d'un modèle perceptif et la borne basse par
  défaut.
- Débit soutenable et effet visuel d'un pas d'écriture (P4).
- Comportement de « Fonction Économie d'énergie » Auto, du mode Éco, de
  « Paramètres de luminosité AI » et de « Lumière ambiante du MODE
  FILMMAKER » vis-à-vis de `backlight` (P5).
- Présence de Dolby Vision IQ sur le G5 et son réglage (le guide ne cite la
  marque qu'en mentions légales).
- Lecture de la valeur du capteur de lumière du téléviseur par une API
  quelconque : rien trouvé dans l'app Réglages ; `tv.model.digitalEye` lu
  par `com.webos.service.config` (accessible ou non à un client non signé :
  inconnu).
- Correspondance des valeurs API de `gamma` (P5 bis).
- Caractéristiques des capteurs marquées « à vérifier » au § 3.2 : plages
  Aqara, Hue, IKEA, Tuya, Fibaro, Aeotec, stations météo ; cadence réelle
  du capteur Hue ; unité du paramètre 43 de l'Aeotec.
- Valeurs de fabricant et de modèle exposées par chaque intégration (ZHA,
  Zigbee2MQTT, Hue, ESPHome, Z-Wave JS) pour la table des profils.
- Disponibilité de `async_track_state_report_event` et de `last_reported`
  dans la version minimale de Home Assistant visée par l'intégration.
- Réflexion des murs (de 20 à 60 %, à vérifier) pour le placement B ;
  réponse angulaire des capteurs (aucune donnée trouvée).
- Ordres de grandeur du § 3.4 (P2) et hypothèse d'une luminance
  proportionnelle à la valeur OLED.

### 8.3 Constat annexe

**Réduire la lumière bleue est global, l'arbre le traite comme propre au
mode.** `arbre.mode_dependant` déclarait propre au mode toute clé `picture`
sauf `pictureMode`. Or le descripteur de `eyeComfortMode` a une dimension
vide [Observé : inventaire]. Conséquences : un preset n'en rétablissait la
valeur que si le mode de la capture était actif, et la garde de mode d'un
retour arrière pouvait la refuser à tort. **Corrigé en 2.11.0**
(`arbre.CLES_GLOBALES`), à confirmer par P10. Même remarque, **non
corrigée** faute de descripteur, pour `energySaving`, rangé dans la
catégorie `picture` mais présenté dans Général : proposition, à trancher
par P10 (`essai_portee.py` le teste aussi).

**Historique jamais purgé.** L'historique SQLite n'est jamais purgé. Sans les rampes, la luminosité
adaptative ajoute quelques dizaines de lignes par jour, sans gravité ; avec
une entrée par pas de rampe, ce serait dix fois plus. Indépendamment de
cette étude, une purge (par exemple au-delà d'un an) mérite d'être décidée.

---

## 9. Sources

Normes et environnement de visionnage :

Textes ITU lus (versions officielles) :

- BT.2035 (07/2013) : <https://www.itu.int/dms_pubrec/itu-r/rec/bt/R-REC-BT.2035-0-201307-I!!PDF-E.pdf>
- BT.2100-3 (02/2025) : <https://www.itu.int/dms_pubrec/itu-r/rec/bt/R-REC-BT.2100-3-202502-I!!PDF-E.pdf>
- BT.1886 (03/2011) : <https://www.itu.int/dms_pubrec/itu-r/rec/bt/R-REC-BT.1886-0-201103-I!!PDF-E.pdf>
- BT.814-4 (07/2018) : <https://www.itu.int/dms_pubrec/itu-r/rec/bt/R-REC-BT.814-4-201807-I!!PDF-E.pdf>
- BT.500-15 (05/2023) : <https://www.itu.int/dms_pubrec/itu-r/rec/bt/R-REC-BT.500-15-202305-I!!PDF-E.pdf>
- BT.2022 (08/2012) : <https://itu.int/dms_pubrec/itu-r/rec/bt/R-REC-BT.2022-0-201208-W!!MSW-E.docx>
- Rapport BT.2390-11 (2023) : <https://www.itu.int/dms_pub/itu-r/opb/rep/R-REP-BT.2390-11-2023-PDF-E.pdf>
- Rapport BT.2408-8 (2024) : <https://www.itu.int/dms_pub/itu-r/opb/rep/R-REP-BT.2408-8-2024-PDF-E.pdf>

Lumière du soir et sommeil :

- Brown et al., *Recommendations for daytime, evening, and nighttime indoor
  light exposure…*, PLOS Biology 2022 : <https://pmc.ncbi.nlm.nih.gov/articles/PMC8929548/>
- Night Shift et sommeil (Duraccio et al., *Sleep Health* 2021, résumé
  secondaire) : <https://en.wikipedia.org/wiki/Night_Shift_(software)>,
  <https://www.slashgear.com/blue-light-filters-probably-arent-helping-you-get-better-sleep-at-night-28670677/>

Réglages LG (sources secondaires) :

- Protection des yeux (Motion Eye Care) : <https://www.slashgear.com/1908372/lg-tv-settings-should-change-explained>,
  réglages RTINGS : <https://www.rtings.com/tv/reviews/lg/c2-oled/settings>
- Réduire la lumière bleue (assistance LG) :
  <https://www.lg.com/uk/support/product-help/CT32002770-20150102727782>

Perception et préférences :

- Microsoft, *Understanding and Interpreting Lux Values* :
  <https://learn.microsoft.com/en-us/windows/win32/sensorsapi/understanding-and-interpreting-lux-values>
- Microsoft, ALRPoints (courbe de réponse à la lumière ambiante) :
  <https://learn.microsoft.com/en-us/previous-versions/windows/embedded/jj979773(v=winembedded.81)>
- *Effects of Average Luminance Level of Displayed Images, Viewers Age, and
  Screen Illuminance on Preferred Luminance of LCDs* :
  <https://www.researchgate.net/publication/251014248>
- *Perceptually Equivalent Luminance Level of Large-screen TVs* (IS&T CIC 24) :
  <https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/cic/24/1/art00023>
- Rempel et al., *Video Viewing Preferences for HDR Displays Under Varying
  Ambient Illumination* : <https://www.cl.cam.ac.uk/~rkm38/pdfs/rempel09vvp.pdf>
- US DOE, *Analysis of Room Illuminance and Televisions with Automatic
  Brightness Control* :
  <https://www1.eere.energy.gov/buildings/appliance_standards/pdfs/tv_tpnopr_room_illuminance_abc_031912.pdf>
- Gamma 2.2 / 2.4 selon la pièce (forums, blog ; pas une norme) :
  <https://hub.displaycal.net/forums/topic/calibration-settings-for-hdtv-content/>,
  <https://awolvision.com/blogs/awol-vision-blog/gamma-2-2-vs-2-4>

Fonctions natives (Android, Apple, Dolby, LG) :

- AOSP `config.xml` (valeurs par défaut de la luminosité automatique) :
  <https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/core/res/res/values/config.xml>
- Android Developers Blog, *Getting screen brightness right for every
  user* (2018) :
  <https://android-developers.googleblog.com/2018/11/getting-screen-brightness-right-for.html>
- Dolby Vision IQ : <https://displaydaily.com/dolby-vision-iq-explained/>,
  <https://www.techradar.com/news/how-game-of-thrones-inspired-panasonic-tvs-best-new-feature>,
  <https://www.whathifi.com/advice/dolby-vision-iq-everything-you-need-to-know>
- FILMMAKER MODE, compensation de la lumière ambiante (LG C5 / G5) :
  <https://www.techradar.com/televisions/the-new-lg-oled-tv-feature-im-most-excited-about-is-filmmaker-mode-with-ambient-light-compensation-heres-why>,
  <https://www.xatakahome.com/televisores/poder-ver-tele-salas-mucha-luz-que-se-degrade-calidad-imagen-asi-quiere-conseguirlo-nuevo-filmmaker-mode>
- True Tone (Apple, source secondaire) :
  <https://www.trustedreviews.com/explainer/what-is-true-tone-4244347>
- Guide LG webOS 25 (copie locale `outils/data/guide-webos25-fre.html`),
  § 6.2.4, 6.2.9, 6.6.2, 6.14 ; app Réglages du firmware 33.31.68
  (`outils/data/firmware/settings-main.js`, `settings-strings-fr.json`).

Capteurs :

- ROHM BH1750FVI, fiche technique :
  <https://www.rgbautomatyka.pl/it/p/file/1070/BH1750FVI-TR__ROHM_92_1_2.pdf> ;
  calcul de la plage : <https://wolles-elektronikkiste.de/en/bh1750fvi-gy-30-302-ambient-light-sensor>
- ESPHome : <https://esphome.io/components/sensor/bh1750/>,
  <https://esphome.io/components/sensor/tsl2591/>,
  <https://esphome.io/components/sensor/veml7700/>
- Zigbee2MQTT : Aqara GZCGQ11LM <https://www.zigbee2mqtt.io/devices/GZCGQ11LM.html>,
  Hue 9290012607 <https://www.zigbee2mqtt.io/devices/9290012607.html>,
  IKEA E2134 <https://zigbee2mqtt.io/devices/E2134.html>
- Cadence du capteur Hue (rapports d'utilisateurs) :
  <https://community.homey.app/t/measuring-lux-from-a-hue-motion-sensor/45373>
- Fibaro FGMS-001, paramètres 40 et 42 :
  <https://venustitan-guidance.readthedocs.io/en/latest/_sources/_static/src/motion_sensor/fibaro_home_motion.rst.txt>
- Aeotec MultiSensor 6, paramètres 43 et 111 :
  <https://venustitan-guidance.readthedocs.io/en/latest/_sources/_static/src/motion_sensor/aeon_gen6_multi.rst.txt>,
  <https://community.openhab.org/t/aeotec-multisensor-6-reporting/120364>

Home Assistant :

- `last_reported` et événement `state_reported` (blog développeurs,
  20/03/2024, miroir) :
  <https://www.hasscn.top/developers/blog/2024-03-20-state_reported_timestamp> ;
  objet d'état : <https://www.home-assistant.io/docs/configuration/state_object/>
- Écoute des événements : <https://developers.home-assistant.io/docs/integration_listen_events>

Usure OLED :

- RTINGS, *OLED Burn-In Hasn't Improved Like We Expected* :
  <https://www.rtings.com/tv/learn/oled-burn-in-hasnt-improved-like-we-expected>
- Mesure SDR 100 % du G5 (RTINGS, comparatif) :
  <https://www.rtings.com/tv/tools/compare/lg-g5-oled-vs-samsung-s95d-oled/88601/49702>
- Facteur d'accélération de la durée de vie (cours et brevets) :
  <https://organic-electronics.engin.umich.edu/book/week2-5.pdf>,
  <https://www.ossila.com/pages/oled-testing-guide>
