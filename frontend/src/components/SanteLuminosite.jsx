import { useState } from 'react'
import { duree, heures, NIVEAUX_ACTIFS, texteControle, texteDiagnostic } from '../sante.js'

const SYMBOLES = { bloquant: '⚠', avertissement: '⚠', info: 'ⓘ', ok: '✓', attente: '…' }

const formaterLux = (lux) => `${lux.toLocaleString('fr-FR')} lx`

function libelleJour(jour) {
  // Midi : à l'abri d'un changement d'heure.
  return new Date(`${jour}T12:00:00`).toLocaleDateString('fr-FR',
    { weekday: 'short', day: 'numeric', month: 'short' })
}

// Santé de l'installation (étude, § 4.5 et 4.7) : ce qui ne va pas, pourquoi,
// le chiffre et quoi faire, puis les contrôles passés et les statistiques des
// 7 derniers jours, mesurées par la fonction elle-même.
export default function SanteLuminosite({ sante, etat, options, lectureSeule, onAppliquer,
  onDesactiverEconomie }) {
  const [envoi, setEnvoi] = useState(null)
  const [erreur, setErreur] = useState(null)

  async function agir(id, action) {
    setErreur(null)
    setEnvoi(id)
    try {
      await action()
    } catch (err) {
      setErreur(err.message)
    } finally {
      setEnvoi(null)
    }
  }

  if (!sante) {
    return (
      <section className="carte-luminosite" aria-labelledby="titre-sante">
        <h3 id="titre-sante">Santé de l'installation</h3>
        <p className="texte-attenue">Chargement…</p>
      </section>
    )
  }

  const actifs = sante.diagnostics.filter((d) => NIVEAUX_ACTIFS.includes(d.niveau))
  // Le capteur figé n'a rien à dire tant qu'il ne l'est pas : la fréquence
  // des mesures en tient lieu.
  const passes = sante.diagnostics.filter((d) => d.niveau === 'ok' && d.id !== 'capteur_fige')
  const enObservation = sante.diagnostics.filter((d) => d.niveau === 'attente')

  return (
    <section className="carte-luminosite" aria-labelledby="titre-sante">
      <h3 id="titre-sante">Santé de l'installation</h3>
      <p className="texte-attenue">
        La fonction observe elle-même le capteur, le téléviseur et vos corrections, et dit ici ce
        qui gagnerait à être changé. Certains contrôles demandent quelques jours d'usage.
      </p>

      {actifs.length === 0 ? (
        <p className="ligne-carte">Rien à signaler.</p>
      ) : (
        <ul className="diagnostics-sante">
          {actifs.map((d) => (d.id === 'conflit' ? (
            <li key={d.id} className="diagnostic-sante diagnostic-bloquant">
              <ConflitLuminosite
                conflit={d.valeurs.cause}
                economieEnergie={etat?.economie_energie}
                desactive={lectureSeule || envoi !== null}
                onDesactiver={() => agir(d.id, onDesactiverEconomie)}
              />
            </li>
          ) : (
            <Diagnostic
              key={d.id}
              diagnostic={d}
              options={options}
              envoi={envoi === d.id}
              desactive={envoi !== null}
              onAppliquer={() => agir(d.id, () => onAppliquer(d.proposition))}
            />
          )))}
        </ul>
      )}
      {erreur && <p className="erreur-reglage" role="alert">{erreur}</p>}

      {(passes.length > 0 || enObservation.length > 0) && (
        <ul className="controles-sante">
          {passes.map((d) => (
            <li key={d.id}>
              <span className="symbole-sante symbole-ok" aria-hidden="true">{SYMBOLES.ok}</span>
              <span>{texteControle(d)}</span>
            </li>
          ))}
          {enObservation.map((d) => (
            <li key={d.id} className="texte-attenue">
              <span className="symbole-sante" aria-hidden="true">{SYMBOLES.attente}</span>
              <span><span className="sr-only">En observation : </span>{texteControle(d)}</span>
            </li>
          ))}
        </ul>
      )}

      <Statistiques resume={sante.resume} jours={sante.jours} chargees={sante.chargees} />
    </section>
  )
}

function Diagnostic({ diagnostic: d, options, envoi, desactive, onAppliquer }) {
  const { titre, pourquoi, action, libelleProposition, lienEmplacement } =
    texteDiagnostic(d, options)
  return (
    <li className={`diagnostic-sante diagnostic-${d.niveau}`}>
      <p className="titre-diagnostic">
        <span className="symbole-sante" aria-hidden="true">{SYMBOLES[d.niveau]}</span>
        {titre}
      </p>
      <p>{pourquoi}</p>
      {action && <p><strong>Que faire :</strong> {action}</p>}
      {(d.proposition || lienEmplacement) && (
        <p className="actions-diagnostic">
          {d.proposition && (
            <button type="button" className="bouton-principal" disabled={desactive}
              onClick={onAppliquer}>
              {envoi ? 'Application…' : libelleProposition}
            </button>
          )}
          {lienEmplacement && (
            <a
              href="#emplacement-capteur"
              onClick={(e) => {
                e.preventDefault()
                document.getElementById('emplacement-capteur')
                  ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
              }}
            >
              Voir le schéma des emplacements
            </a>
          )}
        </p>
      )}
    </li>
  )
}

function Statistiques({ resume, jours, chargees }) {
  if (!chargees) {
    return <p className="texte-attenue">Lecture des statistiques enregistrées…</p>
  }
  const plage = resume.lux_p10 != null
    ? `${formaterLux(resume.lux_p10)} à ${formaterLux(resume.lux_p90)}`
    : '—'
  return (
    <>
      <h4 className="titre-statistiques">
        Ces 7 derniers jours
        {resume.jours > 0 && resume.jours < 7 && (
          <span className="texte-attenue"> (depuis le {libelleJour(resume.depuis)})</span>
        )}
      </h4>
      <dl className="statistiques-sante">
        <div><dt>Téléviseur allumé</dt><dd>{heures(resume.allume_s)}</dd></div>
        <div><dt>Fonction active</dt><dd>{heures(resume.actif_s)}</dd></div>
        <div>
          <dt>Transitions</dt>
          <dd>{resume.transitions}
            <span className="texte-attenue"> ({resume.pas_confirmes} écritures)</span></dd>
        </div>
        <div><dt>Reprises en main</dt><dd>{resume.reprises}</dd></div>
        <div>
          <dt>Une mesure toutes les</dt>
          <dd>{resume.intervalle_s != null ? duree(resume.intervalle_s) : '—'}</dd>
        </div>
        <div>
          <dt>Pas en pièce sombre</dt>
          <dd>{resume.pas_sombre != null ? formaterLux(resume.pas_sombre) : '—'}</dd>
        </div>
        <div><dt>Lumière habituelle</dt><dd>{plage}</dd></div>
        <div><dt>Écritures non confirmées</dt><dd>{resume.non_confirmees}</dd></div>
      </dl>
      {jours.length > 0 && (
        <details className="jours-sante">
          <summary>Jour par jour</summary>
          <div className="tableau-defilant">
            <table>
              <thead>
                <tr>
                  <th scope="col">Jour</th>
                  <th scope="col">Allumé</th>
                  <th scope="col">Active</th>
                  <th scope="col">Transitions</th>
                  <th scope="col">Reprises</th>
                  <th scope="col">Refus</th>
                </tr>
              </thead>
              <tbody>
                {jours.map((jour) => (
                  <tr key={jour.jour}>
                    <th scope="row">{libelleJour(jour.jour)}</th>
                    <td>{heures(jour.allume_s)}</td>
                    <td>{heures(jour.actif_s)}</td>
                    <td>{jour.transitions}</td>
                    <td>{jour.reprises}</td>
                    <td>{jour.non_confirmees}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </>
  )
}

export function ConflitLuminosite({ conflit, economieEnergie, desactive, onDesactiver }) {
  if (conflit === 'mode_eco') {
    return (
      <p className="message message-conflit">
        En mode d'image Éco, le capteur du téléviseur ajuste lui-même la luminosité des pixels
        OLED selon l'éclairage ambiant : la luminosité adaptative n'écrit rien dans ce mode.
        Choisissez un autre mode d'image, ou laissez Éco de côté dans les réglages ci-dessous.
      </p>
    )
  }
  return (
    <div className="message message-conflit">
      <p>
        La « Fonction Économie d'énergie » du téléviseur (Général › Économie d'énergie) règle
        déjà la luminosité de l'écran
        {economieEnergie === 'auto' ? ' selon son propre capteur' : ''}. Les deux régulations se
        contrarieraient : la luminosité adaptative n'écrit plus rien tant qu'elle reste active.
      </p>
      <button type="button" className="bouton-principal" disabled={desactive} onClick={onDesactiver}>
        {economieEnergie === 'auto'
          ? 'Désactiver l\'économie d\'énergie automatique'
          : 'Désactiver l\'économie d\'énergie'}
      </button>
    </div>
  )
}
