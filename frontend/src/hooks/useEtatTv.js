import { useCallback, useEffect, useState } from 'react'
import { ecrireReglage, ouvrirCanal, recupererArbre, recupererReglages } from '../api.js'

// Rafraîchissement périodique en filet de sécurité, indépendant du canal
// temps réel (décidé en phase 1 : abonnement fonctionnel + repli par lecture
// périodique tant que l'interface est ouverte).
const INTERVALLE_RAFRAICHISSEMENT_MS = 30000

export function useEtatTv() {
  const [arbre, setArbre] = useState(null)
  const [erreurArbre, setErreurArbre] = useState(null)
  const [tentativeArbre, setTentativeArbre] = useState(0)
  const [reglages, setReglages] = useState({})
  // null tant que l'instantané n'est pas arrivé : rien à signaler encore.
  const [connexion, setConnexion] = useState(null)
  const [modeImage, setModeImage] = useState(null)
  // null tant que le service ne l'a pas vérifié ; false si le téléviseur
  // n'accorde ni l'écriture directe ni le pont par alerte.
  const [ecriturePossible, setEcriturePossible] = useState(null)
  // Incrémentées quand l'intégration signale un changement de l'historique
  // ou des presets : les vues concernées relisent leur liste.
  const [revisions, setRevisions] = useState({ historique: 0, presets: 0 })

  useEffect(() => {
    let annule = false
    setErreurArbre(null)
    recupererArbre().then(
      (a) => {
        if (!annule) setArbre(a)
      },
      (err) => {
        if (!annule) setErreurArbre(err.message)
      },
    )
    return () => {
      annule = true
    }
  }, [tentativeArbre])

  useEffect(() => {
    const fermerCanal = ouvrirCanal({
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
        } else if (msg.type === 'historique' || msg.type === 'presets') {
          setRevisions((prev) => ({ ...prev, [msg.type]: prev[msg.type] + 1 }))
        }
      },
    })

    async function rafraichir() {
      try {
        const r = await recupererReglages()
        setReglages(r.reglages)
      } catch {
        // Le canal WebSocket gère déjà l'indicateur de connexion.
      }
    }
    const minuteurRafraichissement = setInterval(rafraichir, INTERVALLE_RAFRAICHISSEMENT_MS)

    return () => {
      fermerCanal()
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

  const rechargerArbre = useCallback(() => setTentativeArbre((n) => n + 1), [])

  return {
    arbre, erreurArbre, rechargerArbre, reglages, connexion, modeImage, ecriturePossible,
    revisions, ecrire,
  }
}
