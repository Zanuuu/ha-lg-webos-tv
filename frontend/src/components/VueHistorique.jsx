import { useEffect, useState } from 'react'
import * as api from '../api.js'
import { libelleModeImage, libelleValeur } from '../valeurs.js'
import Confirmation from './Confirmation.jsx'

// Valeurs de historique.ORIGINES côté intégration.
const LIBELLES_ORIGINE = {
  home_assistant: 'Home Assistant',
  panneau: 'Panneau',
  preset: 'Preset',
  annulation: 'Retour arrière',
  luminosite_adaptative: 'Luminosité adaptative',
}

const formaterDate = (horodatage) => new Date(horodatage * 1000).toLocaleString('fr-FR')

export default function VueHistorique({ index, lectureSeule, revision }) {
  const [lignes, setLignes] = useState(null)
  const [message, setMessage] = useState(null)
  // Ligne dont on confirme le retour à l'instant, avec le nombre d'écritures
  // postérieures qui seront annulées.
  const [retour, setRetour] = useState(null)
  const [occupe, setOccupe] = useState(false)

  async function rafraichir() {
    try {
      setLignes(await api.recupererHistorique(100))
    } catch (err) {
      setLignes((l) => l || [])
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  // Relu à chaque écriture signalée par l'intégration, d'où qu'elle vienne.
  useEffect(() => {
    rafraichir()
  }, [revision])

  async function annuler(id) {
    setMessage(null)
    try {
      const resultat = await api.annulerEcriture(id)
      if (!resultat.ok) setMessage({ type: 'erreur', texte: resultat.raison })
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  async function revenir() {
    setMessage(null)
    setOccupe(true)
    try {
      const { resultats } = await api.revenirA(retour.ligne.horodatage)
      const echecs = resultats.filter((r) => !r.ok)
      if (echecs.length > 0) {
        setMessage({
          type: 'erreur',
          texte: `${echecs.length} réglage(s) non restauré(s) : ${echecs.map((e) => e.raison).join(' · ')}`,
        })
      }
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    } finally {
      setOccupe(false)
      setRetour(null)
    }
  }

  if (!lignes) return <p className="texte-attenue" role="status">Chargement…</p>

  return (
    <div className="vue-historique">
      {message && <p className={`message message-${message.type}`} role="alert">{message.texte}</p>}
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
              <th>Origine</th>
              <th><span className="visuellement-masque">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {lignes.map((l) => {
              const entree = index?.get(l.entree_id)
              const posterieures = lignes.filter((autre) => autre.horodatage > l.horodatage).length
              return (
                <tr key={l.id}>
                  <td data-libelle="Date">{formaterDate(l.horodatage)}</td>
                  <td data-libelle="Réglage" className="cellule-titre">
                    {entree?.libelle || `${l.categorie}.${l.cle}`}
                  </td>
                  <td data-libelle="Valeur">
                    {libelleValeur(entree, l.ancienne)} → {libelleValeur(entree, l.nouvelle)}
                  </td>
                  <td data-libelle="Mode d'image">{libelleModeImage(index, l.mode_image) || '—'}</td>
                  <td data-libelle="Origine">{LIBELLES_ORIGINE[l.origine] || l.origine || '—'}</td>
                  <td className="actions-historique">
                    {!lectureSeule && (
                      <>
                        <button type="button" onClick={() => annuler(l.id)}>Annuler</button>
                        {posterieures > 0 && (
                          <button type="button" onClick={() => setRetour({ ligne: l, posterieures })}>
                            Revenir à cet instant…
                          </button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      {retour && (
        <Confirmation
          titre="Revenir à cet instant ?"
          libelleAction="Revenir"
          occupe={occupe}
          onConfirmer={revenir}
          onAnnuler={() => setRetour(null)}
        >
          <p>
            Les {retour.posterieures} modification(s) faite(s) après le{' '}
            {formaterDate(retour.ligne.horodatage)} seront annulées, de la plus récente à la
            plus ancienne. Chaque annulation est elle-même enregistrée et peut être défaite.
          </p>
        </Confirmation>
      )}
    </div>
  )
}
