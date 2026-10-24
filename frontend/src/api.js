// Accès à l'intégration par l'API websocket de Home Assistant (commandes
// lg_webos_tv/…, calquées sur l'ancienne API REST de l'app) : même découpage
// et mêmes réponses, les composants n'en savent rien.
import { obtenirHass } from './hass.js'

async function commande(type, donnees = {}) {
  const hass = await obtenirHass()
  try {
    return await hass.callWS({ type: `lg_webos_tv/${type}`, ...donnees })
  } catch (err) {
    // HA rejette avec { code, message } : les composants affichent err.message.
    throw new Error(err?.message || `Échec (${err?.code ?? 'inconnu'})`)
  }
}

export const recupererArbre = () => commande('arbre')
export const recupererReglages = () => commande('reglages')
export const ecrireReglage = (entreeId, valeur) =>
  commande('ecrire', { entree_id: entreeId, valeur })

export const recupererPresets = () => commande('presets')
export const recupererPreset = (nom) => commande('presets/obtenir', { nom })
export const creerPreset = (nom) => commande('presets/creer', { nom })
export const importerPreset = (donnees, remplacer = false) =>
  commande('presets/importer', { nom: donnees.nom, entrees: donnees.entrees, remplacer })
export const supprimerPreset = (nom) => commande('presets/supprimer', { nom })
export const appliquerPreset = (nom) => commande('presets/appliquer', { nom })

export const recupererHistorique = (limite = 100) => commande('historique', { limite })
export const annulerEcriture = (id) => commande('historique/annuler', { ecriture_id: id })
export const revenirA = (horodatage) => commande('historique/revenir', { horodatage })

// Flux temps réel. La connexion de HA se rétablit seule et renouvelle
// l'abonnement, qui renvoie alors un instantané : pas de reconnexion à gérer.
// Renvoie une fonction de désabonnement.
export function ouvrirCanal(gestionnaires) {
  let desabonner = null
  let ferme = false
  obtenirHass()
    .then((hass) =>
      hass.connection.subscribeMessage(gestionnaires.onMessage, { type: 'lg_webos_tv/abonner' }),
    )
    .then((fn) => {
      if (ferme) fn()
      else desabonner = fn
    })
  return () => {
    ferme = true
    desabonner?.()
  }
}
