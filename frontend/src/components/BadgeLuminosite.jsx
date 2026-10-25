import { useState } from 'react'

// Libellés des états du capteur (translations/fr.json). Désactivée et
// téléviseur déconnecté ne sont pas signalés : rien n'agit sur la ligne, et
// le bandeau dit déjà que la TV est injoignable.
const LIBELLES = {
  active: 'Luminosité adaptative : active',
  pause: 'Luminosité adaptative : en pause',
  mode_exclu: 'Luminosité adaptative : mode d\'image laissé de côté',
  capteur_indisponible: 'Luminosité adaptative : capteur indisponible',
  consultation: 'Luminosité adaptative : écriture impossible',
}

function heure(iso) {
  return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

export default function BadgeLuminosite({ luminosite, lectureSeule, onReprendre }) {
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState(null)
  const { etat, cible, fin_pause: finPause } = luminosite
  let texte = LIBELLES[etat]
  if (etat === 'active' && cible !== null) texte += ` (cible ${cible})`
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
        </p>
      )}
      {erreur && <p className="erreur-reglage" role="alert">{erreur}</p>}
    </div>
  )
}
