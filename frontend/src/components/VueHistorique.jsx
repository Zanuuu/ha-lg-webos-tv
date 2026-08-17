import { useEffect, useState } from 'react'
import * as api from '../api.js'

function formaterValeur(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export default function VueHistorique({ index }) {
  const [lignes, setLignes] = useState(null)
  const [message, setMessage] = useState(null)

  async function rafraichir() {
    setLignes(await api.recupererHistorique(100))
  }

  useEffect(() => {
    rafraichir()
  }, [])

  async function annuler(id) {
    setMessage(null)
    try {
      const resultat = await api.annulerEcriture(id)
      if (!resultat.ok) {
        setMessage({ type: 'erreur', texte: resultat.raison })
      } else {
        await rafraichir()
      }
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  async function revenir(horodatage) {
    setMessage(null)
    try {
      const { resultats } = await api.revenirA(horodatage)
      const echecs = resultats.filter((r) => !r.ok)
      if (echecs.length > 0) {
        setMessage({
          type: 'erreur',
          texte: `${echecs.length} réglage(s) non restauré(s) : ${echecs.map((e) => e.raison).join(' · ')}`,
        })
      }
      await rafraichir()
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  if (!lignes) return null

  return (
    <div className="vue-historique">
      {message && <p className={`message message-${message.type}`}>{message.texte}</p>}
      {lignes.length === 0 ? (
        <p className="texte-attenue">Aucune modification enregistrée.</p>
      ) : (
        <table className="table-historique">
          <thead>
            <tr>
              <th>Date</th>
              <th>Réglage</th>
              <th>Valeur</th>
              <th>Mode d'image</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {lignes.map((l) => (
              <tr key={l.id}>
                <td>{new Date(l.horodatage * 1000).toLocaleString('fr-FR')}</td>
                <td>{index?.get(l.entree_id)?.libelle || `${l.categorie}.${l.cle}`}</td>
                <td>{formaterValeur(l.ancienne)} → {formaterValeur(l.nouvelle)}</td>
                <td>{l.mode_image || '—'}</td>
                <td className="actions-historique">
                  <button type="button" onClick={() => annuler(l.id)}>Annuler</button>
                  <button type="button" onClick={() => revenir(l.horodatage)}>
                    Revenir à cet instant
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
