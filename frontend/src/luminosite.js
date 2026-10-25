// Luminosité adaptative : vocabulaire et calcul communs au badge de la ligne
// OLED et à la page dédiée.

// États du capteur de la fonction (translations/fr.json).
export const LIBELLES_ETAT = {
  active: 'Active',
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
}

// Options avancées du signal (const.OPTIONS_AVANCEES) : vides (null), elles
// suivent le profil du capteur. Champ de details.constantes correspondant et
// facteur d'affichage (les seuils sont des fractions côté intégration).
export const OPTIONS_AVANCEES = {
  lissage_montee_s: { libelle: 'Lissage à la hausse', unite: 's', constante: 'lissage_montee_s', facteur: 1 },
  lissage_descente_s: { libelle: 'Lissage à la baisse', unite: 's', constante: 'lissage_descente_s', facteur: 1 },
  hysteresis_montee: { libelle: 'Seuil à la hausse', unite: '%', constante: 'hysteresis_montee', facteur: 100 },
  hysteresis_descente: { libelle: 'Seuil à la baisse', unite: '%', constante: 'hysteresis_descente', facteur: 100 },
  confirmation_saut_s: { libelle: 'Confirmation des sauts', unite: 's', constante: 'confirmation_saut_s', facteur: 1 },
  gel_ecriture_s: { libelle: 'Pause de mesure après écriture', unite: 's', constante: 'gel_s', facteur: 1 },
}

// Profils du capteur (signal_lux.profil).
export const LIBELLES_PROFIL = {
  rapide: 'rapide',
  periodique: 'périodique',
  sur_variation: 'sur variation',
  lent: 'lent',
  inconnu: 'à déterminer',
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

export function heure(iso) {
  return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

// Portage de luminosite_adaptative.calculer_cible : interpolation sur le
// logarithme du lux, bornée aux extrêmes, arrondi 0,5 vers le haut.
export function calculerCible(lux, options) {
  const { lux_min: luxMin, lux_max: luxMax, luminosite_min: bas, luminosite_max: haut } = options
  let t = (Math.log(Math.max(lux, 1)) - Math.log(luxMin)) / (Math.log(luxMax) - Math.log(luxMin))
  t = Math.min(Math.max(t, 0), 1)
  return Math.floor(bas + t * (haut - bas) + 0.5)
}

// Mêmes contrôles que luminosite_adaptative.valider_options ; renvoie un
// message par option fautive.
export function validerOptions(options) {
  const erreurs = {}
  for (const [cle, [bas, haut]] of Object.entries(BORNES)) {
    const valeur = options[cle]
    if (cle in OPTIONS_AVANCEES && (valeur === null || valeur === undefined)) continue
    if (typeof valeur !== 'number' || Number.isNaN(valeur) || valeur < bas || valeur > haut) {
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
  if (options.emplacement_capteur !== undefined && !(options.emplacement_capteur in EMPLACEMENTS)) {
    erreurs.emplacement_capteur = 'Emplacement inconnu.'
  }
  return erreurs
}
