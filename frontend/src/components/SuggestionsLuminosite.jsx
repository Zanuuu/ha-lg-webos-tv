import { useState } from 'react'
import * as api from '../api.js'
import { LIBELLES_ORIGINE_CORRECTION } from '../luminosite.js'
import { AMBIANCES, signe } from '../sante.js'
import { libelleModeImage } from '../valeurs.js'

const formaterLux = (lux) => `${lux.toLocaleString('fr-FR')} lx`

// Ce que la suggestion change, point par point : la courbe proposée vient
// telle quelle de l'intégration (reprise.py), rien n'est recalculé ici.
function changements(options, proposees) {
  const lignes = []
  if (proposees.luminosite_min !== options.luminosite_min) {
    lignes.push(`luminosité minimale ${options.luminosite_min} → ${proposees.luminosite_min}`)
  }
  const avant = options.point_intermediaire
  const apres = proposees.point_intermediaire
  if (apres && !avant) {
    lignes.push(`point intermédiaire ajouté : luminosité ${apres[1]} à ${formaterLux(apres[0])}`)
  } else if (apres && avant && apres[1] !== avant[1]) {
    lignes.push(`point intermédiaire (${formaterLux(apres[0])}) ${avant[1]} → ${apres[1]}`)
  }
  if (proposees.luminosite_max !== options.luminosite_max) {
    lignes.push(`luminosité maximale ${options.luminosite_max} → ${proposees.luminosite_max}`)
  }
  return lignes
}

function dateCourte(iso) {
  return new Date(iso).toLocaleString('fr-FR', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

// Suggestions de courbe tirées des corrections retenues, et ces corrections
// (étude, § 3.8 et 4.7) : jamais appliquées sans l'accord de l'utilisateur.
// `apercu` : plage dont la courbe proposée est tracée en pointillé.
export default function SuggestionsLuminosite({
  index, donnees, options, ancrages, apercu, bloque, lectureSeule, onApercu, onAppliquee,
}) {
  const [envoi, setEnvoi] = useState(null)
  const [erreur, setErreur] = useState(null)

  if (!donnees?.chargees) return null
  const { suggestions, corrections } = donnees

  async function agir(cle, action) {
    setErreur(null)
    setEnvoi(cle)
    try {
      await action()
    } catch (err) {
      setErreur(err.message)
    } finally {
      setEnvoi(null)
    }
  }

  const desactive = lectureSeule || envoi !== null

  return (
    <div className="suggestions-luminosite" id="suggestions-luminosite">
      {suggestions.map((s) => (
        <div key={s.plage} className="message suggestion-courbe">
          <p>
            <strong>
              Suggestion : {signe(Math.round(s.ecart))} en {AMBIANCES[s.ambiance] || s.ambiance}
            </strong>
            , vers {formaterLux(s.lux)} ({s.nombre} correction{s.nombre > 1 ? 's' : ''} dans le
            même sens).
          </p>
          <ul className="changements-suggestion">
            {changements(options, s.options).map((ligne) => <li key={ligne}>{ligne}</li>)}
          </ul>
          {s.approche && (
            <p className="texte-attenue">
              La courbe ne peut qu'approcher vos réglages : la luminosité reste entre 0 et 100.
            </p>
          )}
          {ancrages.length > 0 && (
            <p className="texte-attenue">
              Vos points d'ancrage seront oubliés : ils ne décriraient plus la courbe.
            </p>
          )}
          {bloque && (
            <p className="texte-attenue">
              Enregistrez ou annulez d'abord vos retouches de la courbe.
            </p>
          )}
          <p className="actions-suggestion">
            <button type="button" className="bouton-secondaire" disabled={bloque}
              aria-pressed={apercu === s.plage}
              onClick={() => onApercu(apercu === s.plage ? null : s.plage)}>
              {apercu === s.plage ? 'Masquer l\'aperçu' : 'Aperçu'}
            </button>
            <button type="button" className="bouton-principal" disabled={bloque || desactive}
              onClick={() => agir(`appliquer-${s.plage}`, async () => {
                await api.appliquerSuggestion(s.plage)
                onApercu(null)
                onAppliquee()
              })}>
              {envoi === `appliquer-${s.plage}` ? 'Application…' : 'Appliquer'}
            </button>
            <button type="button" className="bouton-secondaire" disabled={desactive}
              onClick={() => agir(`ignorer-${s.plage}`, async () => {
                await api.ignorerSuggestion(s.plage)
                if (apercu === s.plage) onApercu(null)
              })}>
              Ignorer
            </button>
          </p>
        </div>
      ))}

      {corrections.length === 0 ? (
        <p className="texte-attenue">
          Aucune correction retenue pour l'instant. Un réglage de la luminosité gardé 10 minutes,
          sous un éclairage stable, est retenu ici ; dès 3 dans le même sens pour un même
          éclairage, une suggestion de courbe apparaît.
        </p>
      ) : (
        <details className="corrections-luminosite">
          <summary>Vos corrections ({corrections.length})</summary>
          <p className="texte-attenue">
            Réglages de la luminosité gardés au moins 10 minutes, comparés à la courbe actuelle.
            Oubliez ceux qui valaient pour un contenu particulier (un film très sombre…).
          </p>
          <ul className="journal-luminosite">
            {[...corrections].reverse().map((c) => (
              <li key={c.id} className={c.ecartee ? 'texte-attenue' : undefined}>
                <time dateTime={c.horodatage}>{dateCourte(c.horodatage)}</time>
                <span className="ligne-correction">
                  <span>
                    Luminosité {c.valeur} à {formaterLux(c.lux)} (courbe {signe(c.ecart)}) ·{' '}
                    {LIBELLES_ORIGINE_CORRECTION[c.origine] || c.origine}
                    {c.mode_image && ` · ${libelleModeImage(index, c.mode_image)}`}
                    {c.ecartee && ' · écartée des suggestions'}
                  </span>
                  <button type="button" className="bouton-secondaire" disabled={desactive}
                    onClick={() => agir(`oublier-${c.id}`, () => api.oublierCorrection(c.id))}>
                    Oublier
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {erreur && <p className="erreur-reglage" role="alert">{erreur}</p>}
    </div>
  )
}
