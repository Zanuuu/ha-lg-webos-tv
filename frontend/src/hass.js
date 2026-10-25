// Objet `hass` fourni par Home Assistant au panneau (propriété de l'élément
// personnalisé, voir panneau.jsx). Il est remplacé à chaque changement d'état
// dans HA : on garde seulement le dernier, sans refaire le rendu de l'app.
let hassCourant = null
const enAttente = []

export function definirHass(hass) {
  hassCourant = hass
  while (enAttente.length) enAttente.shift()(hass)
}

// Résolu dès que HA a transmis l'objet hass (immédiatement s'il l'a déjà fait).
export function obtenirHass() {
  if (hassCourant) return Promise.resolve(hassCourant)
  return new Promise((resoudre) => enAttente.push(resoudre))
}

// `narrow` de HA : vrai quand sa barre latérale est repliée (mobile). Lu par
// useSyncExternalStore, qui ne refait le rendu que si la valeur change.
let etroit = false
const abonnesEtroit = new Set()

export function definirEtroit(valeur) {
  if (valeur === etroit) return
  etroit = valeur
  for (const abonne of abonnesEtroit) abonne()
}

export function abonnerEtroit(abonne) {
  abonnesEtroit.add(abonne)
  return () => abonnesEtroit.delete(abonne)
}

export const estEtroit = () => etroit
