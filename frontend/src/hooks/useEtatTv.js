import { useCallback, useEffect, useRef, useState } from 'react'
import { ecrireReglage, ouvrirCanal, recupererArbre, recupererReglages } from '../api.js'

// Rafraîchissement périodique en filet de sécurité, indépendant du canal
// temps réel (décidé en phase 1 : abonnement fonctionnel + repli par lecture
// périodique tant que l'interface est ouverte).
const INTERVALLE_RAFRAICHISSEMENT_MS = 30000
const DELAI_RECONNEXION_MS = 3000

export function useEtatTv() {
  const [arbre, setArbre] = useState(null)
  const [reglages, setReglages] = useState({})
  const [connexion, setConnexion] = useState('connexion')
  const [modeImage, setModeImage] = useState(null)
  // null tant que le service ne l'a pas vérifié ; false sous webOS 11
  // (écriture réservée par le téléviseur aux clients signés par LG).
  const [ecriturePossible, setEcriturePossible] = useState(null)
  const canalRef = useRef(null)

  useEffect(() => {
    let annule = false
    recupererArbre().then((a) => {
      if (!annule) setArbre(a)
    })
    return () => {
      annule = true
    }
  }, [])

  useEffect(() => {
    let minuteurReconnexion
    let minuteurRafraichissement

    function connecter() {
      canalRef.current = ouvrirCanal({
        onMessage(msg) {
          if (msg.type === 'instantane') {
            setConnexion(msg.connexion)
            setEcriturePossible(msg.ecriture_possible)
            setModeImage(msg.mode_image)
            setReglages(msg.reglages)
          } else if (msg.type === 'connexion') {
            setConnexion(msg.etat)
          } else if (msg.type === 'ecriture') {
            setEcriturePossible(msg.possible)
          } else if (msg.type === 'changement') {
            setReglages((prev) => ({
              ...prev,
              [msg.categorie]: { ...prev[msg.categorie], ...msg.reglages },
            }))
            if (msg.categorie === 'picture' && 'pictureMode' in msg.reglages) {
              setModeImage(msg.reglages.pictureMode)
            }
          }
        },
        onFermeture() {
          minuteurReconnexion = setTimeout(connecter, DELAI_RECONNEXION_MS)
        },
      })
    }
    connecter()

    async function rafraichir() {
      try {
        const r = await recupererReglages()
        setReglages(r.reglages)
      } catch {
        // Le canal WebSocket gère déjà l'indicateur de connexion.
      }
    }
    minuteurRafraichissement = setInterval(rafraichir, INTERVALLE_RAFRAICHISSEMENT_MS)

    return () => {
      canalRef.current?.close()
      clearTimeout(minuteurReconnexion)
      clearInterval(minuteurRafraichissement)
    }
  }, [])

  const ecrire = useCallback(async (entreeId, valeur) => {
    const resultat = await ecrireReglage(entreeId, valeur)
    setReglages((prev) => ({
      ...prev,
      [resultat.categorie]: { ...prev[resultat.categorie], [resultat.cle]: resultat.nouvelle },
    }))
    return resultat
  }, [])

  return { arbre, reglages, connexion, modeImage, ecriturePossible, ecrire }
}
