import { useEffect, useState } from 'react'
import * as api from '../api.js'

function telecharger(nomFichier, donnees) {
  const blob = new Blob([JSON.stringify(donnees, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const lien = document.createElement('a')
  lien.href = url
  lien.download = nomFichier
  lien.click()
  URL.revokeObjectURL(url)
}

export default function VuePresets({ lectureSeule }) {
  const [presets, setPresets] = useState(null)
  const [nomNouveau, setNomNouveau] = useState('')
  const [message, setMessage] = useState(null)
  const [compteRendu, setCompteRendu] = useState(null)

  async function rafraichir() {
    setPresets(await api.recupererPresets())
  }

  useEffect(() => {
    rafraichir()
  }, [])

  async function creer(e) {
    e.preventDefault()
    setMessage(null)
    try {
      await api.creerPreset(nomNouveau.trim())
      setNomNouveau('')
      await rafraichir()
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  async function appliquer(nom) {
    setMessage(null)
    setCompteRendu(null)
    try {
      const resultat = await api.appliquerPreset(nom)
      setCompteRendu(resultat)
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  async function supprimer(nom) {
    try {
      await api.supprimerPreset(nom)
      await rafraichir()
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  async function exporter(nom) {
    try {
      const preset = await api.recupererPreset(nom)
      telecharger(`preset-${nom}.json`, preset)
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  async function importer(e) {
    const fichier = e.target.files?.[0]
    e.target.value = ''
    if (!fichier) return
    setMessage(null)
    try {
      const donnees = JSON.parse(await fichier.text())
      await api.importerPreset(donnees)
      await rafraichir()
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  if (!presets) return null

  return (
    <div className="vue-presets">
      <form className="form-nouveau-preset" onSubmit={creer}>
        <input
          type="text"
          placeholder="Nom du preset"
          value={nomNouveau}
          onChange={(e) => setNomNouveau(e.target.value)}
          required
        />
        <button type="submit">Enregistrer les réglages actuels</button>
        <label className="bouton-importer">
          Importer un fichier…
          <input type="file" accept="application/json" onChange={importer} hidden />
        </label>
      </form>

      {message && <p className={`message message-${message.type}`}>{message.texte}</p>}

      {presets.length === 0 ? (
        <p className="texte-attenue">Aucun preset enregistré.</p>
      ) : (
        <table className="table-presets">
          <thead>
            <tr>
              <th>Nom</th>
              <th>Créé le</th>
              <th>Réglages</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {presets.map((p) => (
              <tr key={p.nom}>
                <td>{p.nom}</td>
                <td>{new Date(p.cree_le * 1000).toLocaleString('fr-FR')}</td>
                <td>{p.nombre_reglages}</td>
                <td className="actions-preset">
                  {!lectureSeule && (
                    <button type="button" onClick={() => appliquer(p.nom)}>Appliquer</button>
                  )}
                  <button type="button" onClick={() => exporter(p.nom)}>Exporter</button>
                  <button type="button" className="bouton-danger" onClick={() => supprimer(p.nom)}>
                    Supprimer
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {compteRendu && (
        <div className="compte-rendu">
          <h3>Application de « {compteRendu.nom} »</h3>
          <p>{compteRendu.appliques.length} réglage(s) appliqué(s)</p>
          {compteRendu.echecs.length > 0 && (
            <>
              <p>{compteRendu.echecs.length} échec(s) :</p>
              <ul>
                {compteRendu.echecs.map((e, i) => (
                  <li key={i}>{e.entree_id || `${e.categorie}.${e.cle}`} — {e.raison}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  )
}
