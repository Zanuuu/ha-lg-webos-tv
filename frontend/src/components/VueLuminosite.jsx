import { useEffect, useState } from 'react'
import * as api from '../api.js'
import { useLuminositeAdaptative } from '../hooks/useLuminositeAdaptative.js'
import {
  BORNES, heure, LIBELLE_HDR, LIBELLES_CAUSE, LIBELLES_ETAT, MODE_HDR, validerOptions,
} from '../luminosite.js'
import { libelleChoix } from '../arbre.js'
import { libelleModeImage } from '../valeurs.js'
import Interrupteur from './controles/Interrupteur.jsx'
import CourbeLuminosite from './CourbeLuminosite.jsx'

const PAUSE_MANUELLE_MIN = 60

const RAISONS_REPRISE = {
  delai: 'fin du délai de pause',
  bouton: 'bouton Reprendre',
  rallumage: 'téléviseur rallumé',
}

const formaterLux = (lux) => `${lux.toLocaleString('fr-FR')} lx`

function libelleCapteur(capteur) {
  const valeur = capteur.unite ? `${capteur.valeur} ${capteur.unite}` : capteur.valeur
  return `${capteur.nom} (${valeur})`
}

export default function VueLuminosite({ index, luminosite, lectureSeule, onReprendre, onRecharge }) {
  const { configuration, erreur, details, journal, relire } =
    useLuminositeAdaptative(Boolean(luminosite))

  if (erreur) {
    return (
      <div className="message message-erreur" role="alert">
        Impossible de lire la configuration : {erreur}{' '}
        <button type="button" className="bouton-secondaire" onClick={relire}>Réessayer</button>
      </div>
    )
  }
  // `luminosite` vaut undefined tant que le canal principal n'a pas livré son
  // instantané : on ne sait pas encore si la fonction existe.
  if (!configuration || luminosite === undefined) {
    return <p className="texte-attenue">Chargement…</p>
  }

  async function enregistrer(options) {
    const { recharge } = await api.configurerLuminosite(options)
    if (recharge) onRecharge()
    relire()
  }

  return (
    <>
      <p className="texte-attenue intro-luminosite">
        Règle la luminosité des pixels OLED d'après un capteur de lumière ambiante, sur une
        échelle logarithmique proche de la perception de l'œil. Un réglage de la luminosité fait
        ailleurs (télécommande, Home Assistant, preset) la met en pause.
      </p>
      {luminosite === null ? (
        <MiseEnRoute capteurs={configuration.capteurs} onEnregistrer={enregistrer} />
      ) : (
        <>
          <EtatLuminosite
            index={index}
            etat={details || luminosite}
            lectureSeule={lectureSeule}
            onReprendre={onReprendre}
          />
          <ReglagesLuminosite
            index={index}
            configuration={configuration}
            lux={details?.lux ?? null}
            onEnregistrer={enregistrer}
          />
          <JournalLuminosite journal={journal} />
        </>
      )}
    </>
  )
}

function MiseEnRoute({ capteurs, onEnregistrer }) {
  const [capteur, setCapteur] = useState(capteurs[0]?.entity_id ?? '')
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState(null)

  async function activer(e) {
    e.preventDefault()
    setErreur(null)
    setEnvoi(true)
    try {
      await onEnregistrer({ capteur_lux: capteur })
    } catch (err) {
      setErreur(err.message)
      setEnvoi(false)
    }
  }

  if (capteurs.length === 0) {
    return (
      <div className="carte-luminosite">
        <h3>Aucun capteur de luminosité</h3>
        <p className="texte-attenue">
          La fonction a besoin d'un capteur de luminosité ambiante (classe « illuminance »)
          dans Home Assistant, placé dans la pièce du téléviseur.
        </p>
      </div>
    )
  }

  return (
    <form className="carte-luminosite" onSubmit={activer}>
      <h3>Mise en route</h3>
      <label className="champ-luminosite">
        <span>Capteur de luminosité ambiante</span>
        <select value={capteur} onChange={(e) => setCapteur(e.target.value)}>
          {capteurs.map((c) => (
            <option key={c.entity_id} value={c.entity_id}>{libelleCapteur(c)}</option>
          ))}
        </select>
      </label>
      <p className="texte-attenue">
        Les autres réglages partent des valeurs par défaut, modifiables ensuite sur cette page.
        L'intégration est rechargée pour créer les entités de la fonction.
      </p>
      <button type="submit" className="bouton-principal" disabled={envoi}>
        {envoi ? 'Activation…' : 'Activer la luminosité adaptative'}
      </button>
      {erreur && <p className="erreur-reglage" role="alert">{erreur}</p>}
    </form>
  )
}

function EtatLuminosite({ index, etat, lectureSeule, onReprendre }) {
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState(null)
  const active = etat.etat !== 'desactivee'
  const cause = etat.cause_pause

  async function agir(action) {
    setErreur(null)
    setEnvoi(true)
    try {
      await action()
    } catch (err) {
      setErreur(err.message)
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <section className="carte-luminosite" aria-labelledby="titre-etat-luminosite">
      <div className="entete-carte">
        <h3 id="titre-etat-luminosite" className={`etat-luminosite etat-luminosite-${etat.etat}`}>
          <span className="puce" aria-hidden="true" />
          {LIBELLES_ETAT[etat.etat] || etat.etat}
        </h3>
        <label className="bascule-luminosite">
          <span>Activée</span>
          <Interrupteur
            valeur={active}
            ecriture={!envoi}
            onEcrire={(valeur) => agir(() => api.activerLuminosite(valeur))}
          />
        </label>
      </div>

      <dl className="mesures-luminosite" aria-live="off">
        <div>
          <dt>Lumière ambiante</dt>
          <dd>{etat.lux !== undefined && etat.lux !== null ? formaterLux(etat.lux) : '—'}</dd>
        </div>
        <div>
          <dt>Luminosité calculée</dt>
          <dd>{etat.cible ?? '—'}</dd>
        </div>
        <div>
          <dt>Luminosité du téléviseur</dt>
          <dd>{etat.actuelle ?? '—'}</dd>
        </div>
      </dl>

      {etat.mode_image && (
        <p className="ligne-carte">
          Mode d'image : {libelleModeImage(index, etat.mode_image)}
          {etat.mode_exclu && <span className="texte-attenue"> — laissé de côté</span>}
        </p>
      )}

      <div aria-live="polite">
        {etat.etat === 'pause' && (
          <p className="ligne-carte">
            {cause
              ? `Pause depuis ${heure(cause.horodatage)} : ${LIBELLES_CAUSE[cause.origine] || cause.origine}. `
              : 'En pause. '}
            {etat.fin_pause && `Reprise à ${heure(etat.fin_pause)}.`}
            <button
              type="button"
              className="bouton-reprendre"
              disabled={lectureSeule || envoi}
              onClick={() => agir(onReprendre)}
            >
              Reprendre
            </button>
          </p>
        )}
      </div>
      {active && etat.etat !== 'pause' && (
        <p className="ligne-carte">
          <button
            type="button"
            className="bouton-secondaire"
            disabled={envoi}
            onClick={() => agir(() => api.pauseLuminosite(PAUSE_MANUELLE_MIN))}
          >
            Pause 1 h
          </button>{' '}
          <span className="texte-attenue">sans toucher à la luminosité, le temps d'un film.</span>
        </p>
      )}
      {etat.derniere_erreur && (
        <p className="erreur-reglage">Dernière écriture impossible : {etat.derniere_erreur}</p>
      )}
      {erreur && <p className="erreur-reglage" role="alert">{erreur}</p>}
    </section>
  )
}

function ReglagesLuminosite({ index, configuration, lux, onEnregistrer }) {
  const { options, capteurs, modes_proposes: modes } = configuration
  const [brouillon, setBrouillon] = useState(options)
  const [envoi, setEnvoi] = useState(false)
  const [message, setMessage] = useState(null)
  const modifie = JSON.stringify(brouillon) !== JSON.stringify(options)
  const erreurs = validerOptions(brouillon)
  const valide = Object.keys(erreurs).length === 0

  // Options relues (enregistrement, autre onglet) : le brouillon les suit
  // tant qu'il n'est pas modifié.
  useEffect(() => {
    if (!modifie) setBrouillon(options)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options])

  const changer = (valeurs) => {
    setMessage(null)
    setBrouillon((b) => ({ ...b, ...valeurs }))
  }

  function libelleMode(mode) {
    if (mode === MODE_HDR) return LIBELLE_HDR
    const entree = index?.get('image.mode-selection')
    return (entree && libelleChoix(entree, mode)) || mode
  }

  function basculerMode(mode, coche) {
    const exclus = new Set(brouillon.modes_exclus)
    if (coche) exclus.add(mode)
    else exclus.delete(mode)
    changer({ modes_exclus: modes.filter((m) => exclus.has(m)) })
  }

  async function enregistrer(e) {
    e.preventDefault()
    setMessage(null)
    setEnvoi(true)
    try {
      await onEnregistrer(brouillon)
      setMessage({ type: 'ok', texte: 'Réglages enregistrés.' })
    } catch (err) {
      setMessage({ type: 'erreur', texte: err.message })
    } finally {
      setEnvoi(false)
    }
  }

  function champNombre(cle, libelle, unite) {
    const [bas, haut] = BORNES[cle]
    return (
      <label className="champ-luminosite">
        <span>{libelle}</span>
        <span className="saisie-unite">
          <input
            type="number"
            min={bas}
            max={haut}
            step="1"
            value={Number.isNaN(brouillon[cle]) ? '' : brouillon[cle]}
            aria-invalid={erreurs[cle] ? true : undefined}
            onChange={(e) => changer({ [cle]: e.target.valueAsNumber })}
          />
          {unite && <span className="texte-attenue">{unite}</span>}
        </span>
        {erreurs[cle] && <span className="erreur-reglage">{erreurs[cle]}</span>}
      </label>
    )
  }

  const capteurConnu = capteurs.some((c) => c.entity_id === brouillon.capteur_lux)
  const retrait = !brouillon.capteur_lux

  return (
    <form className="carte-luminosite" onSubmit={enregistrer} aria-labelledby="titre-courbe">
      <h3 id="titre-courbe">Courbe</h3>
      <CourbeLuminosite
        options={valide ? brouillon : options}
        lux={lux}
        desactive={envoi}
        onChanger={changer}
      />
      <div className="grille-champs">
        {champNombre('lux_min', 'Pièce sombre', 'lx')}
        {champNombre('luminosite_min', 'Luminosité minimale')}
        {champNombre('lux_max', 'Pièce lumineuse', 'lx')}
        {champNombre('luminosite_max', 'Luminosité maximale')}
      </div>

      <h3>Réglages</h3>
      <div className="grille-champs">
        <label className="champ-luminosite champ-large">
          <span>Capteur de luminosité ambiante</span>
          <select
            value={brouillon.capteur_lux ?? ''}
            onChange={(e) => changer({ capteur_lux: e.target.value || null })}
          >
            {capteurs.map((c) => (
              <option key={c.entity_id} value={c.entity_id}>{libelleCapteur(c)}</option>
            ))}
            {!capteurConnu && brouillon.capteur_lux && (
              <option value={brouillon.capteur_lux}>{brouillon.capteur_lux} (introuvable)</option>
            )}
            <option value="">Aucun : désactiver la fonction</option>
          </select>
        </label>
        {champNombre('pause', 'Pause après un réglage manuel', 'min')}
        {champNombre('ecart_minimal', 'Écart minimal')}
      </div>
      <p className="texte-attenue">
        L'écart minimal évite de suivre chaque frémissement du capteur. La pause prend fin aussi
        au prochain allumage du téléviseur.
      </p>

      <fieldset className="modes-exclus">
        <legend>Modes d'image laissés de côté</legend>
        <p className="texte-attenue">La luminosité n'y est jamais modifiée (modes calibrés).</p>
        {modes.map((mode) => (
          <label key={mode} className="case-mode">
            <input
              type="checkbox"
              checked={brouillon.modes_exclus.includes(mode)}
              onChange={(e) => basculerMode(mode, e.target.checked)}
            />
            {libelleMode(mode)}
          </label>
        ))}
      </fieldset>

      {retrait && modifie && (
        <p className="message">
          Sans capteur, la fonction et ses entités sont retirées ; l'intégration est rechargée.
        </p>
      )}
      <div className="actions-reglages">
        <button type="submit" className="bouton-principal" disabled={!modifie || !valide || envoi}>
          {envoi ? 'Enregistrement…' : 'Enregistrer'}
        </button>
        <button
          type="button"
          className="bouton-secondaire"
          disabled={!modifie || envoi}
          onClick={() => {
            setMessage(null)
            setBrouillon(options)
          }}
        >
          Annuler
        </button>
        <span aria-live="polite" className={message?.type === 'erreur' ? 'erreur-reglage' : 'texte-attenue'}>
          {message?.texte}
        </span>
      </div>
    </form>
  )
}

function texteEvenement(evenement) {
  switch (evenement.type) {
    case 'application':
      return `Luminosité réglée à ${evenement.cible}`
        + (evenement.ancienne !== null ? ` (était ${evenement.ancienne})` : '')
        + ` pour ${formaterLux(evenement.lux)}`
    case 'erreur':
      return `Écriture de ${evenement.cible} impossible : ${evenement.raison}`
    case 'pause':
      return `Pause jusqu'à ${heure(evenement.fin)} : `
        + (LIBELLES_CAUSE[evenement.origine] || evenement.origine)
    case 'reprise':
      return `Reprise : ${RAISONS_REPRISE[evenement.raison] || evenement.raison}`
    case 'activation':
      return 'Fonction activée'
    case 'desactivation':
      return 'Fonction désactivée'
    default:
      return evenement.type
  }
}

function horodatage(iso) {
  const date = new Date(iso)
  const aujourdhui = date.toDateString() === new Date().toDateString()
  return aujourdhui
    ? date.toLocaleTimeString('fr-FR')
    : date.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'medium' })
}

function JournalLuminosite({ journal }) {
  return (
    <section className="carte-luminosite" aria-labelledby="titre-journal">
      <h3 id="titre-journal">Journal</h3>
      <p className="texte-attenue">
        Les 50 derniers événements depuis le démarrage de Home Assistant. Les écritures restent
        dans l'Historique.
      </p>
      {journal.length === 0 ? (
        <p className="texte-attenue">Aucun événement pour l'instant.</p>
      ) : (
        <ol className="journal-luminosite">
          {[...journal].reverse().map((evenement, i) => (
            <li key={`${evenement.horodatage}-${i}`}
              className={evenement.type === 'erreur' ? 'erreur-reglage' : undefined}>
              <time dateTime={evenement.horodatage}>{horodatage(evenement.horodatage)}</time>
              <span>{texteEvenement(evenement)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
