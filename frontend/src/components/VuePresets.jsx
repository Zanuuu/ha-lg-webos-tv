import { useEffect, useState } from 'react'
import * as api from '../api.js'
import { libelleModeImage, libelleValeur, memeValeur } from '../valeurs.js'
import Confirmation from './Confirmation.jsx'

function telecharger(nomFichier, donnees) {
  const blob = new Blob([JSON.stringify(donnees, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const lien = document.createElement('a')
  lien.href = url
  lien.download = nomFichier
  lien.click()
  URL.revokeObjectURL(url)
}

// Ce que l'application changerait, avec les règles de l'intégration
// (restauration.appliquer_preset) : le mode d'image du preset est écrit en
// premier, puis les réglages propres à un autre mode sont refusés.
function comparer(preset, reglages, modeImage) {
  const entreeMode = preset.entrees.find((e) => e.categorie === 'picture' && e.cle === 'pictureMode')
  const modeFinal = entreeMode ? entreeMode.valeur : modeImage
  const changeMode = Boolean(entreeMode) && !memeValeur(entreeMode.valeur, modeImage)
  const changements = []
  const identiques = []
  const refuses = []
  for (const entree of preset.entrees) {
    if (entree.mode_image && entree.mode_image !== modeFinal) {
      refuses.push(entree)
      continue
    }
    // Après un changement de mode, les valeurs affichées sont celles du mode
    // quitté : elles ne disent rien de celles du mode d'arrivée.
    const inconnue = changeMode && Boolean(entree.mode_image)
    const actuelle = inconnue ? undefined : reglages?.[entree.categorie]?.[entree.cle]
    if (!inconnue && memeValeur(actuelle, entree.valeur)) identiques.push(entree)
    else changements.push({ ...entree, actuelle, inconnue })
  }
  return { changements, identiques, refuses, modeFinal }
}

export default function VuePresets({ index, reglages, modeImage, lectureSeule, revision }) {
  const [presets, setPresets] = useState(null)
  const [nomNouveau, setNomNouveau] = useState('')
  const [message, setMessage] = useState(null)
  const [compteRendu, setCompteRendu] = useState(null)
  // Dialogue ouvert : { type: 'appliquer', nom, preset } ou { type: 'supprimer', nom }.
  const [dialogue, setDialogue] = useState(null)
  const [occupe, setOccupe] = useState(false)

  const libelleEntree = (e) => index?.get(e.entree_id)?.libelle || `${e.categorie}.${e.cle}`

  async function rafraichir() {
    try {
      setPresets(await api.recupererPresets())
    } catch (err) {
      setPresets((p) => p || [])
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  useEffect(() => {
    rafraichir()
  }, [revision])

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

  async function preparerApplication(nom) {
    setMessage(null)
    setCompteRendu(null)
    try {
      setDialogue({ type: 'appliquer', nom, preset: await api.recupererPreset(nom) })
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    }
  }

  async function confirmer() {
    setOccupe(true)
    try {
      if (dialogue.type === 'appliquer') {
        setCompteRendu(await api.appliquerPreset(dialogue.nom))
      } else {
        await api.supprimerPreset(dialogue.nom)
        await rafraichir()
      }
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    } finally {
      setOccupe(false)
      setDialogue(null)
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

  if (!presets) return <p className="texte-attenue" role="status">Chargement…</p>

  return (
    <div className="vue-presets">
      <form className="form-nouveau-preset" onSubmit={creer}>
        <input
          type="text"
          placeholder="Nom du preset"
          aria-label="Nom du preset"
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

      {message && <p className={`message message-${message.type}`} role="alert">{message.texte}</p>}

      {presets.length === 0 ? (
        <p className="texte-attenue">Aucun preset enregistré.</p>
      ) : (
        <table className="table-presets">
          <thead>
            <tr>
              <th>Nom</th>
              <th>Créé le</th>
              <th>Réglages</th>
              <th><span className="visuellement-masque">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {presets.map((p) => (
              <tr key={p.nom}>
                <td data-libelle="Nom" className="cellule-titre">{p.nom}</td>
                <td data-libelle="Créé le">{new Date(p.cree_le * 1000).toLocaleString('fr-FR')}</td>
                <td data-libelle="Réglages">{p.nombre_reglages}</td>
                <td className="actions-preset">
                  {!lectureSeule && (
                    <button type="button" onClick={() => preparerApplication(p.nom)}>Appliquer…</button>
                  )}
                  <button type="button" onClick={() => exporter(p.nom)}>Exporter</button>
                  <button
                    type="button"
                    className="bouton-danger"
                    onClick={() => setDialogue({ type: 'supprimer', nom: p.nom })}
                  >
                    Supprimer…
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {compteRendu && (
        <div className="compte-rendu" role="status">
          <h3>Application de « {compteRendu.nom} »</h3>
          <p>{compteRendu.appliques.length} réglage(s) appliqué(s)</p>
          {compteRendu.echecs.length > 0 && (
            <>
              <p>{compteRendu.echecs.length} échec(s) :</p>
              <ul>
                {compteRendu.echecs.map((e, i) => (
                  <li key={i}>{libelleEntree(e)} — {e.raison}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {dialogue?.type === 'supprimer' && (
        <Confirmation
          titre={`Supprimer le preset « ${dialogue.nom} » ?`}
          libelleAction="Supprimer"
          danger
          occupe={occupe}
          onConfirmer={confirmer}
          onAnnuler={() => setDialogue(null)}
        >
          <p>Pensez à l'exporter d'abord si vous voulez pouvoir le réimporter.</p>
        </Confirmation>
      )}

      {dialogue?.type === 'appliquer' && (
        <Confirmation
          titre={`Appliquer « ${dialogue.nom} » ?`}
          libelleAction="Appliquer"
          occupe={occupe}
          onConfirmer={confirmer}
          onAnnuler={() => setDialogue(null)}
        >
          <Apercu
            {...comparer(dialogue.preset, reglages, modeImage)}
            modeImage={modeImage}
            index={index}
            libelleEntree={libelleEntree}
          />
        </Confirmation>
      )}
    </div>
  )
}

function Apercu({ changements, identiques, refuses, modeFinal, modeImage, index, libelleEntree }) {
  return (
    <>
      {changements.length === 0 ? (
        <p>Le téléviseur a déjà toutes les valeurs de ce preset.</p>
      ) : (
        <>
          <p>{changements.length} réglage(s) modifié(s) :</p>
          <ul className="liste-apercu">
            {changements.map((e) => {
              const entree = index?.get(e.entree_id)
              return (
                <li key={`${e.categorie}.${e.cle}`}>
                  <span>{libelleEntree(e)}</span>
                  <span className="apercu-valeurs">
                    {!e.inconnue && <>{libelleValeur(entree, e.actuelle)} → </>}
                    <strong>{libelleValeur(entree, e.valeur)}</strong>
                  </span>
                </li>
              )
            })}
          </ul>
        </>
      )}
      {identiques.length > 0 && (
        <p className="texte-attenue">{identiques.length} réglage(s) déjà à la bonne valeur.</p>
      )}
      {refuses.length > 0 && (
        <p className="texte-attenue">
          {refuses.length} réglage(s) d'image enregistré(s) pour un autre mode d'image ne
          seront pas appliqués (mode d'image : {libelleModeImage(index, modeFinal) || '—'}
          {modeFinal !== modeImage ? ', après application' : ''}).
        </p>
      )}
    </>
  )
}
