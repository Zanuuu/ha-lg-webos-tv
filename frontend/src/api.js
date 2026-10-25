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

export const reprendreLuminosite = () => commande('luminosite_adaptative/reprendre')
export const activerLuminosite = (active) => commande('luminosite_adaptative/activer', { active })
export const pauseLuminosite = (minutes) => commande('luminosite_adaptative/pause', { minutes })
export const recupererConfigLuminosite = () => commande('luminosite_adaptative/configuration')
export const configurerLuminosite = (options) =>
  commande('luminosite_adaptative/configurer', { options })
export const ancrerLuminosite = () => commande('luminosite_adaptative/ancrer')
// Décalage pilotable : même effet que l'entité, sans pause.
export const reglerDecalage = (valeur) => commande('luminosite_adaptative/decalage', { valeur })
export const desactiverEconomieEnergie = () =>
  commande('luminosite_adaptative/desactiver_economie_energie')
// Corrections retenues et suggestions de courbe : calculées par
// l'intégration, qui recalcule aussi la suggestion appliquée.
export const appliquerSuggestion = (plage) =>
  commande('luminosite_adaptative/appliquer_suggestion', { plage })
export const ignorerSuggestion = (plage) =>
  commande('luminosite_adaptative/ignorer_suggestion', { plage })
export const oublierCorrection = (id) =>
  commande('luminosite_adaptative/oublier_correction', { correction_id: id })

export const recupererHistorique = (limite = 100) => commande('historique', { limite })
export const annulerEcriture = (id) => commande('historique/annuler', { ecriture_id: id })
export const revenirA = (horodatage) => commande('historique/revenir', { horodatage })

// Flux temps réel. La connexion de HA se rétablit seule et renouvelle
// l'abonnement, qui renvoie alors un instantané : pas de reconnexion à gérer.
// Renvoie une fonction de désabonnement.
function abonner(type, onMessage, onErreur) {
  let desabonner = null
  let ferme = false
  obtenirHass()
    .then((hass) => hass.connection.subscribeMessage(onMessage, { type: `lg_webos_tv/${type}` }))
    .then(
      (fn) => {
        if (ferme) fn()
        else desabonner = fn
      },
      (err) => onErreur?.(new Error(err?.message || `Échec (${err?.code ?? 'inconnu'})`)),
    )
  return () => {
    ferme = true
    desabonner?.()
  }
}

export const ouvrirCanal = (gestionnaires) => abonner('abonner', gestionnaires.onMessage)

// Page Luminosité adaptative : lux et journal, seulement pendant qu'elle est
// ouverte.
export const suivreLuminosite = (onMessage, onErreur) =>
  abonner('luminosite_adaptative/suivre', onMessage, onErreur)

// Assistant de mise en route ouvert : la fonction n'écrit pas et ne se met
// pas en pause tant que l'abonnement dure.
export const suivreMiseEnRoute = () => abonner('luminosite_adaptative/mise_en_route', () => {})
