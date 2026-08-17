import { useState } from 'react'
import { estLisible, estPilotable, valeurDe } from '../arbre.js'
import Curseur from './controles/Curseur.jsx'
import Interrupteur from './controles/Interrupteur.jsx'
import Liste from './controles/Liste.jsx'
import NonPilotable from './controles/NonPilotable.jsx'
import Texte from './controles/Texte.jsx'

export default function LigneReglage({ entree, reglages, onEcrire, onEntrer }) {
  const [erreur, setErreur] = useState(null)
  const api = entree.api

  async function ecrire(valeur) {
    setErreur(null)
    try {
      await onEcrire(entree.id, valeur)
    } catch (e) {
      setErreur(e.message)
    }
  }

  if (entree.controle === 'sous-menu') {
    return (
      <button type="button" className="ligne-reglage ligne-navigable" onClick={() => onEntrer(entree)}>
        <Libelle entree={entree} />
        <span className="fleche">›</span>
      </button>
    )
  }

  const valeur = valeurDe(reglages, api)
  const pilotable = estPilotable(api)
  const lisible = estLisible(api)

  return (
    <div className="ligne-reglage">
      <Libelle entree={entree} />
      <div className="controle">
        {(() => {
          if (!lisible) return <NonPilotable />
          switch (entree.controle) {
            case 'curseur':
              return <Curseur entree={entree} valeur={valeur} onEcrire={ecrire} />
            case 'liste':
              return <Liste entree={entree} valeur={valeur} ecriture={pilotable} onEcrire={ecrire} />
            case 'interrupteur':
              return pilotable
                ? <Interrupteur valeur={valeur} onEcrire={ecrire} />
                : <span className="valeur-lecture-seule">{String(valeur)}</span>
            case 'texte':
              return <Texte valeur={valeur} ecriture={pilotable} onEcrire={ecrire} />
            default:
              return <NonPilotable />
          }
        })()}
      </div>
      {erreur && <p className="erreur-reglage">{erreur}</p>}
    </div>
  )
}

function Libelle({ entree }) {
  return (
    <div className="libelle-reglage">
      <span className="libelle">{entree.libelle}</span>
      {entree.description && <p className="description">{entree.description}</p>}
    </div>
  )
}
