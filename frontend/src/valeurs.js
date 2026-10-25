import { libelleChoix } from './arbre.js'

// Valeur d'API rendue lisible avec le vocabulaire du menu, hors des
// contrôles (historique, aperçu d'un preset).
export function libelleValeur(entree, valeur) {
  if (valeur === null || valeur === undefined) return '—'
  if (typeof valeur === 'object') return JSON.stringify(valeur)
  if (entree?.controle === 'liste') return libelleChoix(entree, valeur) || String(valeur)
  if (entree?.controle === 'interrupteur') {
    if (valeur === 'on' || valeur === true) return 'Activé'
    if (valeur === 'off' || valeur === false) return 'Désactivé'
  }
  return String(valeur)
}

// Le téléviseur notifie parfois en chaîne ce qui a été écrit en nombre.
export function memeValeur(a, b) {
  if (a === b) return true
  if (a === null || a === undefined || b === null || b === undefined) return false
  if (typeof a === 'object' || typeof b === 'object') return JSON.stringify(a) === JSON.stringify(b)
  return String(a) === String(b)
}

export function libelleModeImage(index, mode) {
  if (!mode) return null
  const entree = index?.get('image.mode-selection')
  return (entree && libelleChoix(entree, mode)) || mode
}
