import { useEffect, useRef, useState } from 'react'
import { estLisible, estPilotable, valeurDe } from '../arbre.js'
import BadgeLuminosite from './BadgeLuminosite.jsx'
import Curseur from './controles/Curseur.jsx'
import Interrupteur from './controles/Interrupteur.jsx'
import Liste from './controles/Liste.jsx'
import NonPilotable from './controles/NonPilotable.jsx'
import Texte from './controles/Texte.jsx'

export default function LigneReglage({
  entree, reglages, lectureSeule, horsLigne, luminosite, revelee, onEcrire, onReprendre,
  onDetailsLuminosite, onEntrer,
}) {
  const [erreur, setErreur] = useState(null)
  const [envoi, setEnvoi] = useState(false)
  // Change à chaque échec : le contrôle est recréé et repart de la valeur du
  // téléviseur au lieu de garder celle qui a été refusée.
  const [generation, setGeneration] = useState(0)
  const api = entree.api
  const ligneRef = useRef(null)

  // Arrivée depuis la recherche : la ligne est amenée à l'écran et reçoit le
  // focus, qui sinon se perdrait avec le résultat cliqué.
  useEffect(() => {
    if (!revelee) return
    ligneRef.current?.scrollIntoView({ block: 'center' })
    ligneRef.current?.focus({ preventScroll: true })
  }, [revelee])

  async function ecrire(valeur) {
    setErreur(null)
    setEnvoi(true)
    try {
      await onEcrire(entree.id, valeur)
    } catch (e) {
      setErreur(e.message)
      setGeneration((n) => n + 1)
    } finally {
      setEnvoi(false)
    }
  }

  if (entree.controle === 'sous-menu') {
    return (
      <button
        type="button"
        ref={ligneRef}
        className={`ligne-reglage ligne-navigable${revelee ? ' ligne-revelee' : ''}`}
        onClick={() => onEntrer(entree)}
      >
        <Libelle entree={entree} />
        <span className="fleche" aria-hidden="true">›</span>
      </button>
    )
  }

  const valeur = valeurDe(reglages, api)
  const pilotable = estPilotable(api)
  const lisible = estLisible(api)
  // Le curseur reste manipulable pendant un envoi (l'utilisateur continue de
  // glisser) ; une liste ou un interrupteur renverrait une valeur périmée.
  const ecriture = pilotable && !lectureSeule && (!envoi || entree.controle === 'curseur')

  function controle() {
    if (!lisible) return <NonPilotable />
    if (valeur === undefined && horsLigne) return <span className="valeur-lecture-seule">—</span>
    const proprietes = { entree, valeur, ecriture, onEcrire: ecrire }
    switch (entree.controle) {
      case 'curseur':
        return <Curseur key={generation} {...proprietes} />
      case 'liste':
        return <Liste key={generation} {...proprietes} />
      case 'interrupteur':
        return pilotable
          ? <Interrupteur key={generation} {...proprietes} />
          : <span className="valeur-lecture-seule">{String(valeur)}</span>
      case 'texte':
        return <Texte key={generation} {...proprietes} />
      default:
        return <NonPilotable />
    }
  }

  return (
    <div
      ref={ligneRef}
      className={`ligne-reglage${revelee ? ' ligne-revelee' : ''}`}
      tabIndex={revelee ? -1 : undefined}
    >
      <Libelle entree={entree}>
        {/* Toujours présent : une zone live n'est annoncée que si elle existait déjà. */}
        <span className="etat-envoi" aria-live="polite">{envoi ? 'Envoi…' : ''}</span>
        {luminosite && entree.id === luminosite.entree_id && (
          <BadgeLuminosite
            luminosite={luminosite}
            lectureSeule={lectureSeule}
            onReprendre={onReprendre}
            onDetails={onDetailsLuminosite}
          />
        )}
      </Libelle>
      <div className="controle">{controle()}</div>
      {erreur && <p className="erreur-reglage" role="alert">{erreur}</p>}
    </div>
  )
}

function Libelle({ entree, children }) {
  return (
    <div className="libelle-reglage">
      <span className="libelle">{entree.libelle}</span>
      {children}
      {entree.description && <p className="description">{entree.description}</p>}
    </div>
  )
}
