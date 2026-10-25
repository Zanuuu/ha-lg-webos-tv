import { useCallback, useEffect, useState } from 'react'
import { recupererConfigLuminosite, suivreLuminosite } from '../api.js'

// Page Luminosité adaptative : options de l'entrée (relues après chaque
// enregistrement) et, si la fonction existe, son état complet et son journal,
// suivis tant que la page est ouverte, avec la santé de l'installation.
export function useLuminositeAdaptative(configuree) {
  const [configuration, setConfiguration] = useState(null)
  const [erreur, setErreur] = useState(null)
  const [tentative, setTentative] = useState(0)
  const [details, setDetails] = useState(null)
  // Plus récents en dernier, comme côté intégration.
  const [journal, setJournal] = useState([])
  const [sante, setSante] = useState(null)

  useEffect(() => {
    let annule = false
    setErreur(null)
    recupererConfigLuminosite().then(
      (c) => {
        if (!annule) setConfiguration(c)
      },
      (err) => {
        if (!annule) setErreur(err.message)
      },
    )
    return () => {
      annule = true
    }
  }, [tentative])

  useEffect(() => {
    setDetails(null)
    setJournal([])
    setSante(null)
    if (!configuree) return undefined
    return suivreLuminosite(
      (msg) => {
        if (msg.type === 'instantane') {
          setDetails(msg.details)
          setJournal(msg.journal)
          setSante(msg.sante)
        } else if (msg.type === 'sante') {
          setSante(msg.sante)
        } else if (msg.type === 'details') {
          setDetails(msg.details)
        } else if (msg.type === 'journal') {
          setJournal((j) => [...j, msg.evenement].slice(-50))
        }
      },
      // Fonction retirée entre-temps : le canal principal le dira.
      () => {},
    )
  }, [configuree])

  const relire = useCallback(() => setTentative((n) => n + 1), [])

  return { configuration, erreur, details, journal, sante, relire }
}
