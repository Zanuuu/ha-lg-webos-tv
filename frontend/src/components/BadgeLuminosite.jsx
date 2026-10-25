import { useState } from 'react'
import { heure, LIBELLES_ETAT } from '../luminosite.js'

// États signalés sur la ligne. Désactivée et téléviseur déconnecté ne le
// sont pas : rien n'agit sur la ligne, et le bandeau dit déjà que la TV est
// injoignable.
const ETATS_SIGNALES = [
  'active', 'pause', 'mode_exclu', 'conflit_economie_energie', 'capteur_indisponible',
  'capteur_fige', 'consultation',
]

export default function BadgeLuminosite({ luminosite, lectureSeule, onReprendre, onDetails }) {
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState(null)
  const { etat, cible, fin_pause: finPause, rampe } = luminosite
  let texte = ETATS_SIGNALES.includes(etat)
    ? `Luminosité adaptative : ${LIBELLES_ETAT[etat].toLowerCase()}`
    : null
  if (etat === 'active' && rampe && cible !== null) {
    texte += ` (transition ${rampe.depart ?? '?'} → ${cible})`
  } else if (etat === 'active' && cible !== null) {
    texte += ` (cible ${cible})`
  }
  if (etat === 'pause' && finPause) texte += ` jusqu'à ${heure(finPause)}`

  async function reprendre() {
    setErreur(null)
    setEnvoi(true)
    try {
      await onReprendre()
    } catch (e) {
      setErreur(e.message)
    } finally {
      setEnvoi(false)
    }
  }

  return (
    // Zone live toujours présente : le passage en pause qui suit un
    // mouvement du curseur est annoncé.
    <div className="badge-luminosite-zone" aria-live="polite">
      {texte && (
        <p
          className={`badge-luminosite badge-luminosite-${etat}`}
          title={etat === 'active' ? 'Un réglage manuel la met en pause.' : undefined}
        >
          <span className="puce" aria-hidden="true" />
          {texte}
          {etat === 'pause' && (
            <button
              type="button"
              className="bouton-reprendre"
              disabled={lectureSeule || envoi}
              onClick={reprendre}
            >
              Reprendre
            </button>
          )}
          {onDetails && (
            <button type="button" className="lien-details" onClick={onDetails}>
              Détails
            </button>
          )}
        </p>
      )}
      {erreur && <p className="erreur-reglage" role="alert">{erreur}</p>}
    </div>
  )
}
