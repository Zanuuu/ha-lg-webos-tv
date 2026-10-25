// Luminosité adaptative : vocabulaire et calcul communs au badge de la ligne
// OLED et à la page dédiée.

// États du capteur de la fonction (translations/fr.json).
export const LIBELLES_ETAT = {
  active: 'Active',
  mise_en_route: 'Mise en route en cours',
  pause: 'En pause',
  mode_exclu: 'Mode d\'image laissé de côté',
  conflit_economie_energie: 'En conflit avec l\'économie d\'énergie du téléviseur',
  capteur_indisponible: 'Capteur indisponible',
  capteur_fige: 'Capteur figé',
  consultation: 'Écriture impossible',
  desactivee: 'Désactivée',
  televiseur_deconnecte: 'Téléviseur déconnecté',
}

// Ce qui a mis la fonction en pause : origine notifiée par le téléviseur ou
// enregistrée dans l'historique, ou pause demandée depuis le panneau.
export const LIBELLES_CAUSE = {
  manuel: 'réglage sur le téléviseur',
  autre_application: 'réglage par une autre application',
  home_assistant: 'réglage depuis Home Assistant',
  panneau: 'réglage depuis ce panneau',
  preset: 'application d\'un preset',
  annulation: 'retour arrière dans l\'historique',
  pause_manuelle: 'pause demandée',
}

// Origine d'une correction retenue (les mêmes, sauf preset et retour
// arrière, qui n'en font pas).
export const LIBELLES_ORIGINE_CORRECTION = {
  manuel: 'télécommande',
  autre_application: 'autre application',
  home_assistant: 'Home Assistant',
  panneau: 'panneau',
}

// Pourquoi une correction n'a pas été retenue (reprise.SuiviCorrection).
export const RAISONS_CORRECTION_ECARTEE = {
  deconnecte: 'téléviseur éteint',
  pause_levee: 'pause levée avant 10 minutes',
  mode: 'mode d\'image changé',
  valeur_changee: 'luminosité changée entre-temps',
  lux_inconnu: 'aucune mesure du capteur',
  lux_instable: 'éclairage instable',
  mise_en_route: 'mise en route ouverte',
  preset: 'application d\'un preset',
  annulation: 'retour arrière dans l\'historique',
  secours: 'mesurée avec le capteur de secours',
  decalage: 'décalage changé entre-temps',
}

// Ambiances de la pièce (ambiance.AMBIANCES).
export const LIBELLES_AMBIANCE = {
  sombre: 'sombre',
  intermediaire: 'intermédiaire',
  claire: 'claire',
}

// Bornes du décalage pilotable (const.DECALAGE_MIN, DECALAGE_MAX).
export const DECALAGE = [-30, 30]

// Rapport habituel entre le principal et le secours (secours.RapportCapteurs
// .resume) : `facteur` = lux du principal / lux du secours.
export function texteRapportSecours(secours) {
  if (!secours) return null
  const { etat, facteur, echantillons, requis, dispersion } = secours
  const fois = (f) => f.toLocaleString('fr-FR', { maximumSignificantDigits: 2 })
  switch (etat) {
    case 'apprentissage':
      return `Rapport avec le capteur principal en apprentissage : ${echantillons} mesures communes `
        + `sur ${requis} (une par minute, lumière stable, au moins 2 lx sur chacun).`
    case 'stable': {
      const rapport = Math.abs(facteur - 1) < 0.05
        ? 'le secours mesure comme le principal'
        : facteur > 1
          ? `le secours mesure ${fois(facteur)} fois moins que le principal`
          : `le secours mesure ${fois(1 / facteur)} fois plus que le principal`
      return `Rapport habituel : ${rapport} (${echantillons} mesures, à ×${fois(dispersion)} près) ; `
        + 'ses mesures sont converties en conséquence pendant le relais.'
    }
    case 'instable':
      return `Rapport instable : il varie couramment d'un facteur ${fois(dispersion)}, le secours `
        + 'ne prendra pas le relais. Capteur extérieur, près d\'une fenêtre, ou dans une autre '
        + 'pièce ?'
    case 'incoherent':
      return 'Mesures incohérentes : l\'un des capteurs affiche 0 lx quand l\'autre dépasse '
        + '20 lx ; le secours ne prendra pas le relais.'
    default:
      return null
  }
}

// Option groupée des modes HDR et Dolby Vision (const.MODES_HDR), absente
// de l'arbre des menus.
export const MODE_HDR = 'hdr'
export const LIBELLE_HDR = 'Contenus HDR et Dolby Vision'

// Mêmes bornes que luminosite_adaptative.BORNES (vérifié par
// tests/test_luminosite_adaptative.py).
export const BORNES = {
  lux_min: [1, 1000],
  lux_max: [2, 100000],
  luminosite_min: [0, 100],
  luminosite_max: [0, 100],
  ecart_minimal: [1, 20],
  pause: [5, 720],
  lissage_montee_s: [0, 120],
  lissage_descente_s: [0, 300],
  hysteresis_montee: [0, 100],
  hysteresis_descente: [0, 90],
  confirmation_saut_s: [0, 60],
  gel_ecriture_s: [0, 120],
  rampe_pas: [1, 10],
  rampe_debit: [1, 20],
  ambiance_sombre: [1, 100000],
  ambiance_claire: [1, 100000],
}

// Seuils de l'ambiance (const.OPTIONS_AMBIANCE) : vides, les tiers de la
// courbe.
export const OPTIONS_AMBIANCE = ['ambiance_sombre', 'ambiance_claire']

// Options avancées (const.OPTIONS_AVANCEES) : vides (null), elles prennent
// leur valeur par défaut ou celle du profil du capteur. `auto` lit dans les
// détails de la fonction la valeur appliquée (les seuils sont des fractions
// côté intégration).
const constante = (champ, facteur = 1) => (details) => details.constantes[champ] * facteur
export const OPTIONS_AVANCEES = {
  ecart_minimal: { libelle: 'Écart minimal', unite: '', auto: (details) => details.ecart_minimal },
  lissage_montee_s: { libelle: 'Lissage à la hausse', unite: 's', auto: constante('lissage_montee_s') },
  lissage_descente_s: { libelle: 'Lissage à la baisse', unite: 's', auto: constante('lissage_descente_s') },
  hysteresis_montee: { libelle: 'Seuil à la hausse', unite: '%', auto: constante('hysteresis_montee', 100) },
  hysteresis_descente: { libelle: 'Seuil à la baisse', unite: '%', auto: constante('hysteresis_descente', 100) },
  confirmation_saut_s: { libelle: 'Confirmation des sauts', unite: 's', auto: constante('confirmation_saut_s') },
  gel_ecriture_s: { libelle: 'Pause de mesure après une transition', unite: 's', auto: constante('gel_s') },
  rampe_pas: { libelle: 'Taille des pas', unite: 'points', auto: (details) => details.parametres_rampe.pas },
  rampe_debit: { libelle: 'Vitesse de la transition', unite: 'points/s', auto: (details) => details.parametres_rampe.debit },
}

// Pourquoi une transition s'est arrêtée avant la cible (fin d'une rampe,
// journal) ; les états de la fonction ont leur libellé dans LIBELLES_ETAT.
export const FINS_RAMPE = {
  reprise_en_main: 'réglage fait ailleurs',
  pause_manuelle: 'pause demandée',
  mode: 'changement de mode d\'image',
  changement_exterieur: 'luminosité changée par le téléviseur (autre entrée ?)',
  non_confirmee: 'écriture non confirmée',
  preset: 'application d\'un preset',
  annulation: 'retour arrière dans l\'historique',
  arret: 'arrêt de l\'intégration',
  mise_en_route: 'mise en route ouverte',
}

// Profils du capteur (signal_lux.profil).
export const LIBELLES_PROFIL = {
  rapide: 'rapide',
  periodique: 'périodique',
  sur_variation: 'sur variation',
  lent: 'lent',
  inconnu: 'à déterminer',
}

// Plateformes courantes des capteurs de lux (registre des entités).
export const NOMS_PLATEFORME = {
  esphome: 'ESPHome', zha: 'ZHA', mqtt: 'MQTT', hue: 'Philips Hue', deconz: 'deCONZ',
  zwave_js: 'Z-Wave JS', matter: 'Matter',
}

// Emplacements du capteur (docs/etude-luminosite-adaptative.md, § 3.3 et
// 4.2), dans l'ordre du sélecteur du formulaire (const.EMPLACEMENTS).
export const EMPLACEMENTS = {
  inconnu: {
    libelle: 'Autre, ou je ne sais pas',
    texte: 'Choisir l\'emplacement adapte les réglages et signale les cas à éviter.',
  },
  a: {
    libelle: 'A — À côté de l\'écran, tourné vers la pièce (recommandé)',
    texte: 'Il mesure la lumière qui tombe sur l\'écran, celle qui crée les reflets et fait '
      + 'paraître l\'image terne. L\'écran l\'éclaire peu. Évitez qu\'une fenêtre ou une lampe '
      + 'le vise directement.',
  },
  b: {
    libelle: 'B — Derrière le téléviseur, tourné vers le mur',
    texte: 'Il mesure la clarté du mur autour de l\'image, ce que vos yeux voient autour de '
      + 'l\'écran. Les valeurs sont plus basses : calez la courbe en conséquence.',
  },
  c: {
    libelle: 'C — Au plafond, tourné vers le bas',
    texte: 'Convient, surtout loin d\'une suspension. Une lampe proche peut dominer la mesure.',
  },
  d: {
    libelle: 'D — Au canapé, tourné vers l\'écran (déconseillé)',
    texte: 'À éviter : l\'écran éclaire le capteur, et la luminosité suivrait les scènes claires '
      + 'et sombres. Si vous ne pouvez pas le déplacer, la fonction attend plus longtemps après '
      + 'chaque changement (20 s au lieu de 5 s).',
    avertissement: true,
  },
  e: {
    libelle: 'E — Au canapé, tourné vers le haut',
    texte: 'Convient ; une lampe de lecture proche peut fausser la mesure.',
  },
  f: {
    libelle: 'F — Près d\'une fenêtre (déconseillé seul)',
    texte: 'Il voit surtout le jour ; le soir, il ignore vos lampes. Préférez un capteur '
      + 'intérieur.',
    avertissement: true,
  },
  g: {
    libelle: 'G — À l\'extérieur (déconseillé seul)',
    texte: 'Il ne mesure pas votre pièce : la luminosité suivrait le jour, pas vos lampes.',
    avertissement: true,
  },
}

// Précision des lux de la courbe (courbe._encadrer) : au dixième sous
// 100 lx, à l'unité au-delà.
export function arrondirLux(lux) {
  return lux < 100 ? Math.round(lux * 10) / 10 : Math.round(lux)
}

export function heure(iso) {
  return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

// Points de la courbe, du plus sombre au plus lumineux : extrémités et
// point intermédiaire facultatif (courbe.points).
export function pointsCourbe(options) {
  const points = [[options.lux_min, options.luminosite_min]]
  if (options.point_intermediaire) points.push(options.point_intermediaire)
  points.push([options.lux_max, options.luminosite_max])
  return points
}

// Portage de courbe.calculer_cible (vecteurs partagés :
// tests/vecteurs_courbe.json) : interpolation par morceaux sur le logarithme
// du lux, plate au-delà des extrémités, plus le décalage pilotable, arrondi
// 0,5 vers le haut, borné à 0–100.
export function calculerCible(lux, options, decalage = 0) {
  const courbe = pointsCourbe(options).map(([l, v]) => [Math.log(l), v])
  const x = Math.log(Math.max(lux, 1))
  let valeur = courbe[courbe.length - 1][1]
  if (x <= courbe[0][0]) {
    valeur = courbe[0][1]
  } else {
    for (let i = 1; i < courbe.length; i += 1) {
      const [x0, v0] = courbe[i - 1]
      const [x1, v1] = courbe[i]
      if (x <= x1) {
        valeur = v0 + ((x - x0) / (x1 - x0)) * (v1 - v0)
        break
      }
    }
  }
  return Math.min(Math.max(Math.floor(valeur + decalage + 0.5), 0), 100)
}

// Tiers de la plage de la courbe en ln(lux) (ambiance.seuils_courbe) :
// seuils de l'ambiance quand ils ne sont pas figés.
export function seuilsCourbe(options) {
  const bas = Math.log(options.lux_min)
  const haut = Math.log(options.lux_max)
  return [Math.exp(bas + (haut - bas) / 3), Math.exp(bas + (2 * (haut - bas)) / 3)]
}

const estNombre = (v) => typeof v === 'number' && !Number.isNaN(v)

// Mêmes contrôles que luminosite_adaptative.valider_options ; renvoie un
// message par option fautive.
export function validerOptions(options) {
  const erreurs = {}
  for (const [cle, [bas, haut]] of Object.entries(BORNES)) {
    const valeur = options[cle]
    if ((cle in OPTIONS_AVANCEES || OPTIONS_AMBIANCE.includes(cle))
        && (valeur === null || valeur === undefined)) continue
    if (!estNombre(valeur) || valeur < bas || valeur > haut) {
      erreurs[cle] = `Entre ${bas} et ${haut}.`
    }
  }
  if (Object.keys(erreurs).length === 0) {
    if (options.lux_max <= options.lux_min) {
      erreurs.lux_max = 'Doit dépasser la valeur « Pièce sombre ».'
    }
    if (options.luminosite_max < options.luminosite_min) {
      erreurs.luminosite_max = 'Doit être au moins égale à la luminosité minimale.'
    }
  }
  const point = options.point_intermediaire
  if (Object.keys(erreurs).length === 0 && point !== null && point !== undefined) {
    // courbe.valider_point_intermediaire
    if (Array.isArray(point) && point.length === 2 && point.some((v) => v == null)) {
      erreurs.point_intermediaire = 'Indiquez le lux et la luminosité du point intermédiaire, '
        + 'ou aucun des deux.'
    } else if (!Array.isArray(point) || point.length !== 2 || !point.every(estNombre)
        || point[0] < 1 || point[0] > BORNES.lux_max[1] || point[1] < 0 || point[1] > 100) {
      erreurs.point_intermediaire = 'Lux entre 1 et 100 000, luminosité entre 0 et 100.'
    } else if (!(options.lux_min < point[0] && point[0] < options.lux_max
        && options.luminosite_min <= point[1] && point[1] <= options.luminosite_max)) {
      erreurs.point_intermediaire = 'Doit tomber entre la pièce sombre et la pièce lumineuse, '
        + 'et entre les luminosités minimale et maximale.'
    }
  }
  if (Object.keys(erreurs).length === 0) {
    const [sombre, claire] = seuilsCourbe(options)
    if ((options.ambiance_sombre ?? sombre) >= (options.ambiance_claire ?? claire)) {
      erreurs[options.ambiance_claire != null ? 'ambiance_claire' : 'ambiance_sombre'] = 'Le seuil '
        + 'de l\'ambiance claire doit dépasser celui de l\'ambiance sombre.'
    }
  }
  if (options.capteur_secours && options.capteur_secours === options.capteur_lux) {
    erreurs.capteur_secours = 'Doit être différent du capteur principal.'
  }
  if (options.emplacement_capteur !== undefined && !(options.emplacement_capteur in EMPLACEMENTS)) {
    erreurs.emplacement_capteur = 'Emplacement inconnu.'
  }
  if (options.reprise_sur_changement !== undefined
      && typeof options.reprise_sur_changement !== 'boolean') {
    erreurs.reprise_sur_changement = 'Cochée ou non.'
  }
  return erreurs
}
