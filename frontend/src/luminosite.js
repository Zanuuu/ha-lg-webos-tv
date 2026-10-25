// Luminosité adaptative : vocabulaire et calcul communs au badge de la ligne
// OLED et à la page dédiée.

// États du capteur de la fonction (translations/fr.json).
export const LIBELLES_ETAT = {
  active: 'Active',
  pause: 'En pause',
  mode_exclu: 'Mode d\'image laissé de côté',
  capteur_indisponible: 'Capteur indisponible',
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

// Mêmes bornes que luminosite_adaptative.BORNES.
export const BORNES = {
  lux_min: [1, 1000],
  lux_max: [2, 100000],
  luminosite_min: [0, 100],
  luminosite_max: [0, 100],
  ecart_minimal: [1, 20],
  pause: [5, 720],
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
  return erreurs
}
