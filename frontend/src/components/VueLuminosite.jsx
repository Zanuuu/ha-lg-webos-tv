import { useEffect, useState } from 'react'
import * as api from '../api.js'
import { useLuminositeAdaptative } from '../hooks/useLuminositeAdaptative.js'
import {
  BORNES, EMPLACEMENTS, FINS_RAMPE, heure, LIBELLE_HDR, LIBELLES_CAUSE, LIBELLES_ETAT,
  LIBELLES_PROFIL, MODE_HDR, NOMS_PLATEFORME, OPTIONS_AVANCEES, validerOptions,
} from '../luminosite.js'
import { libelleChoix } from '../arbre.js'
import { duree } from '../sante.js'
import { libelleModeImage } from '../valeurs.js'
import Interrupteur from './controles/Interrupteur.jsx'
import CourbeLuminosite from './CourbeLuminosite.jsx'
import MiseEnRoute from './MiseEnRoute.jsx'
import SanteLuminosite from './SanteLuminosite.jsx'
import SchemaEmplacement from './SchemaEmplacement.jsx'

const PAUSE_MANUELLE_MIN = 60

const RAISONS_REPRISE = {
  delai: 'fin du délai de pause',
  bouton: 'bouton Reprendre',
  rallumage: 'téléviseur rallumé',
}

const formaterLux = (lux) => `${lux.toLocaleString('fr-FR')} lx`

function texteProfil(profil) {
  if (!profil) return null
  const plateforme = profil.plateforme && (NOMS_PLATEFORME[profil.plateforme] || profil.plateforme)
  let texte = `Profil du capteur : ${LIBELLES_PROFIL[profil.nom] || profil.nom}`
  if (plateforme) texte += ` (${plateforme})`
  texte += profil.intervalle_s
    ? `, une mesure toutes les ${duree(profil.intervalle_s)}.`
    : ', fréquence des mesures pas encore observée.'
  return texte
}

// Les options avancées vides (null) suivent le profil, un point
// intermédiaire vide est absent : sans effet sur la comparaison avec les
// options enregistrées, où ils n'apparaissent pas.
function normaliser(options, cles = null) {
  return JSON.stringify(Object.fromEntries(Object.entries(options)
    .filter(([cle, valeur]) => !((cle in OPTIONS_AVANCEES || cle === 'point_intermediaire')
      && valeur == null))
    .filter(([cle]) => cles === null || cles.includes(cle))
    .sort(([a], [b]) => a.localeCompare(b))))
}

// Clés de la courbe (const.CLES_COURBE) : les retoucher fait oublier les
// points d'ancrage.
const CLES_COURBE = ['lux_min', 'lux_max', 'luminosite_min', 'luminosite_max',
  'point_intermediaire']

// Avec un seul point d'ancrage, le deuxième se prend dans une ambiance au
// moins 4 fois plus sombre (courbe.FACTEUR_DEUX_POINTS).
const FACTEUR_DEUX_POINTS = 4

function libelleCapteur(capteur) {
  const valeur = capteur.unite ? `${capteur.valeur} ${capteur.unite}` : capteur.valeur
  return `${capteur.nom} (${valeur})`
}

export default function VueLuminosite({
  index, luminosite, lectureSeule, connexion, ecriturePossible, reglages, onEcrire, onReprendre,
  onRecharge,
}) {
  const { configuration, erreur, details, journal, sante, relire } =
    useLuminositeAdaptative(Boolean(luminosite))
  // Parcours de mise en route ouvert : { depart: 'capteur' | 'ancrage' }.
  // Toujours ouvert tant que la fonction n'existe pas ; il reste ouvert à
  // travers le rechargement qui la crée.
  const [miseEnRoute, setMiseEnRoute] = useState(null)
  useEffect(() => {
    if (luminosite === null && miseEnRoute === null) setMiseEnRoute({ depart: 'capteur' })
  }, [luminosite, miseEnRoute])

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
        échelle logarithmique proche de la perception de l'œil. La mesure est lissée, et une
        variation brève ou isolée est ignorée, et chaque changement se fait en douceur, point par
        point. Un réglage de la luminosité fait ailleurs (télécommande, Home Assistant, preset)
        la met en pause.
      </p>
      {miseEnRoute || luminosite === null ? (
        <MiseEnRoute
          index={index}
          configuration={configuration}
          luminosite={luminosite}
          details={details}
          connexion={connexion}
          ecriturePossible={ecriturePossible}
          reglages={reglages}
          depart={miseEnRoute?.depart ?? 'capteur'}
          onEnregistrer={enregistrer}
          onEcrire={onEcrire}
          onTerminer={() => {
            setMiseEnRoute(null)
            relire()
          }}
        />
      ) : (
        <>
          <EtatLuminosite
            index={index}
            etat={details || luminosite}
            lectureSeule={lectureSeule}
            onReprendre={onReprendre}
          />
          <CarteMiseEnRoute
            ancrages={configuration.options.ancrages ?? []}
            lux={details?.lux_filtre ?? null}
            lectureSeule={lectureSeule}
            onOuvrir={(depart) => setMiseEnRoute({ depart })}
          />
          <SanteLuminosite
            sante={sante}
            etat={details || luminosite}
            options={configuration.options}
            lectureSeule={lectureSeule}
            onAppliquer={enregistrer}
            onDesactiverEconomie={api.desactiverEconomieEnergie}
          />
          <ReglagesLuminosite
            index={index}
            configuration={configuration}
            lux={details?.lux_filtre ?? details?.lux ?? null}
            details={details}
            onEnregistrer={enregistrer}
          />
          <AideFonctionsTeleviseur />
          <JournalLuminosite journal={journal} />
        </>
      )}
    </>
  )
}

// Relance du parcours, et invitation au deuxième point (étude, § 4.6,
// étape 6) : un seul ancrage cale la position de la courbe, pas sa pente.
function CarteMiseEnRoute({ ancrages, lux, lectureSeule, onOuvrir }) {
  const [ancrage] = ancrages
  const invitation = ancrages.length === 1
  const moment = invitation && lux !== null && lux * FACTEUR_DEUX_POINTS <= ancrage.lux
  return (
    <section className="carte-luminosite" aria-labelledby="titre-carte-mise-en-route">
      <h3 id="titre-carte-mise-en-route">Mise en route</h3>
      {invitation && (
        <div className={moment ? 'message invitation-ancrage' : 'ligne-carte'}>
          <p>
            {moment
              ? `C'est le moment : il fait bien plus sombre qu'à votre premier réglage `
                + `(${formaterLux(ancrage.lux)}). Refaites-le maintenant pour caler aussi la pente `
                + 'de la courbe.'
              : `Votre réglage du ${new Date(ancrage.horodatage).toLocaleDateString('fr-FR')} `
                + `(${formaterLux(ancrage.lux)} → ${ancrage.luminosite}) cale la courbe. Ce soir, `
                + 'dans le noir, refaites le réglage : avec ce deuxième point, la courbe suivra '
                + 'aussi votre préférence dans l\'obscurité.'}
          </p>
          <button type="button" className={moment ? 'bouton-principal' : 'bouton-secondaire'}
            disabled={lectureSeule} onClick={() => onOuvrir('ancrage')}>
            Refaire le réglage
          </button>
        </div>
      )}
      {ancrages.length === 2 && (
        <p className="ligne-carte texte-attenue">
          Courbe calée sur vos deux réglages ({ancrages.map((a) => `${formaterLux(a.lux)} → `
            + `${a.luminosite}`).join(', ')}).
        </p>
      )}
      <p className="ligne-carte">
        <button type="button" className="bouton-secondaire" onClick={() => onOuvrir('capteur')}>
          Relancer la mise en route
        </button>{' '}
        <span className="texte-attenue">capteur, emplacement, vérifications et point d'ancrage.</span>
      </p>
    </section>
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
          <dt>Lumière ambiante (lissée)</dt>
          <dd>{etat.lux_filtre != null ? formaterLux(etat.lux_filtre) : '—'}</dd>
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

      {etat.rampe && <TransitionLuminosite rampe={etat.rampe} cible={etat.cible}
        actuelle={etat.actuelle} />}

      {etat.lux != null && (
        <p className="ligne-carte texte-attenue">
          Dernière mesure du capteur : {formaterLux(etat.lux)}
          {etat.derniere_mesure && ` à ${heure(etat.derniere_mesure)}`}.
          {' '}{texteProfil(etat.profil)}
        </p>
      )}
      {etat.mode_image && (
        <p className="ligne-carte">
          Mode d'image : {libelleModeImage(index, etat.mode_image)}
          {etat.mode_exclu && <span className="texte-attenue"> — laissé de côté</span>}
        </p>
      )}

      {(etat.conflit || etat.etat === 'capteur_fige') && (
        <p className="ligne-carte texte-attenue">
          Le détail et la correction sont dans Santé de l'installation, ci-dessous.
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

// Rampe en cours : progression d'après la valeur notifiée par le téléviseur,
// jamais d'après les pas demandés.
function TransitionLuminosite({ rampe, cible, actuelle }) {
  const { depart } = rampe
  const etendue = cible - depart
  const progression = actuelle != null && depart != null && etendue !== 0
    ? Math.min(Math.max((actuelle - depart) / etendue, 0), 1)
    : null
  return (
    <div className="ligne-carte transition-luminosite">
      <span>Transition en cours : {depart ?? '?'} → {cible}</span>
      {progression !== null && (
        <progress max="1" value={progression} aria-label="Progression de la transition" />
      )}
    </div>
  )
}

function ReglagesLuminosite({ index, configuration, lux, details, onEnregistrer }) {
  const { options, capteurs, modes_proposes: modes } = configuration
  const [brouillon, setBrouillon] = useState(options)
  const [envoi, setEnvoi] = useState(false)
  const [message, setMessage] = useState(null)
  const modifie = normaliser(brouillon) !== normaliser(options)
  const ancrages = options.ancrages ?? []
  const courbeModifiee = normaliser(brouillon, CLES_COURBE) !== normaliser(options, CLES_COURBE)
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

  // Lux au dixième : le point d'ancrage cale la courbe à cette précision.
  function champNombre(cle, libelle, unite, pas = '1') {
    const [bas, haut] = BORNES[cle]
    return (
      <label className="champ-luminosite">
        <span>{libelle}</span>
        <span className="saisie-unite">
          <input
            type="number"
            min={bas}
            max={haut}
            step={pas}
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

  // Point intermédiaire : deux champs, vides tous deux pour s'en passer.
  function champIntermediaire(indice, libelle, unite) {
    const valeur = brouillon.point_intermediaire?.[indice]
    return (
      <label className="champ-luminosite">
        <span>{libelle}</span>
        <span className="saisie-unite">
          <input
            type="number"
            min={indice === 0 ? 1 : 0}
            max={indice === 0 ? BORNES.lux_max[1] : 100}
            step={indice === 0 ? '0.1' : '1'}
            value={valeur == null || Number.isNaN(valeur) ? '' : valeur}
            placeholder="facultatif"
            aria-invalid={erreurs.point_intermediaire ? true : undefined}
            onChange={(e) => {
              const point = [...(brouillon.point_intermediaire ?? [null, null])]
              point[indice] = e.target.value === '' ? null : e.target.valueAsNumber
              changer({ point_intermediaire: point.every((v) => v == null) ? null : point })
            }}
          />
          {unite && <span className="texte-attenue">{unite}</span>}
        </span>
      </label>
    )
  }

  function champAvance(cle) {
    const { libelle, unite, auto: valeurAuto } = OPTIONS_AVANCEES[cle]
    const [bas, haut] = BORNES[cle]
    const auto = details ? Math.round(valeurAuto(details)) : null
    const valeur = brouillon[cle]
    return (
      <label key={cle} className="champ-luminosite">
        <span>{libelle}</span>
        <span className="saisie-unite">
          <input
            type="number"
            min={bas}
            max={haut}
            step="1"
            value={valeur == null || Number.isNaN(valeur) ? '' : valeur}
            placeholder={auto !== null ? `auto : ${auto}` : 'auto'}
            aria-invalid={erreurs[cle] ? true : undefined}
            onChange={(e) => changer({ [cle]: e.target.value === '' ? null : e.target.valueAsNumber })}
          />
          <span className="texte-attenue">{unite}</span>
        </span>
        {erreurs[cle] && <span className="erreur-reglage">{erreurs[cle]}</span>}
      </label>
    )
  }

  const emplacement = EMPLACEMENTS[brouillon.emplacement_capteur] || EMPLACEMENTS.inconnu
  const capteurConnu = capteurs.some((c) => c.entity_id === brouillon.capteur_lux)
  const retrait = !brouillon.capteur_lux

  return (
    <form className="carte-luminosite" onSubmit={enregistrer} aria-labelledby="titre-courbe">
      <h3 id="titre-courbe">Courbe</h3>
      <CourbeLuminosite
        options={valide ? brouillon : options}
        lux={lux}
        ancrages={courbeModifiee ? [] : ancrages}
        desactive={envoi}
        onChanger={changer}
      />
      {/* Une ligne par point de la courbe : lux, puis luminosité. */}
      <div className="grille-champs grille-points">
        {champNombre('lux_min', 'Pièce sombre', 'lx', '0.1')}
        {champNombre('luminosite_min', 'Luminosité minimale')}
        {champIntermediaire(0, 'Pièce intermédiaire', 'lx')}
        {champIntermediaire(1, 'Luminosité intermédiaire')}
        {champNombre('lux_max', 'Pièce lumineuse', 'lx', '0.1')}
        {champNombre('luminosite_max', 'Luminosité maximale')}
      </div>
      {erreurs.point_intermediaire && (
        <p className="erreur-reglage">{erreurs.point_intermediaire}</p>
      )}
      {courbeModifiee && ancrages.length > 0 && (
        <p className="message">
          Courbe retouchée : vos points d'ancrage seront oubliés à l'enregistrement. Le prochain
          réglage de la mise en route repartira d'un seul point.
        </p>
      )}

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
        <label className="champ-luminosite champ-large">
          <span>Emplacement du capteur</span>
          <select
            value={brouillon.emplacement_capteur}
            disabled={envoi}
            onChange={(e) => changer({ emplacement_capteur: e.target.value })}
          >
            {Object.entries(EMPLACEMENTS).map(([cle, { libelle }]) => (
              <option key={cle} value={cle}>{libelle}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="emplacement-capteur" id="emplacement-capteur">
        <SchemaEmplacement
          choisi={brouillon.emplacement_capteur}
          desactive={envoi}
          onChoisir={(cle) => changer({ emplacement_capteur: cle })}
        />
        <p className={emplacement.avertissement ? 'message message-conflit' : 'texte-attenue'}>
          {emplacement.texte}
        </p>
      </div>
      <div className="grille-champs">
        {champNombre('pause', 'Pause après un réglage manuel', 'min')}
      </div>
      <p className="texte-attenue">La pause prend fin aussi au prochain allumage du téléviseur.</p>

      <details className="reglages-avances">
        <summary>Réglages avancés</summary>
        <p className="texte-attenue">
          La mesure est lissée (plus vite à la hausse qu'à la baisse), une variation trop petite
          par rapport à la dernière application est ignorée, une mesure isolée plus de 4 fois
          plus forte ou plus faible attend d'être confirmée. La luminosité change ensuite par
          petits pas réguliers, chacun confirmé par le téléviseur, jusqu'à la cible ; les mesures
          sont mises de côté pendant la transition et juste après. Laissés vides, ces réglages
          suivent leur valeur par défaut, le profil du capteur et son emplacement.
        </p>
        <div className="grille-champs">
          {Object.keys(OPTIONS_AVANCEES).map(champAvance)}
        </div>
      </details>

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

const CAUSES_CONFLIT = {
  economie_energie: 'Fonction Économie d\'énergie du téléviseur active',
  mode_eco: 'mode d\'image Éco',
}

function texteEvenement(evenement) {
  switch (evenement.type) {
    case 'application':
      return texteTransition(evenement)
    case 'saut_ecarte':
      return 'Mesure isolée écartée (saut de lumière non confirmé)'
    case 'conflit':
      return `En retrait : ${CAUSES_CONFLIT[evenement.cause] || evenement.cause}`
    case 'capteur_fige':
      return 'Capteur figé : aucune mesure depuis bien plus longtemps que d\'habitude'
    case 'erreur':
      return `Écriture de ${evenement.cible} impossible : ${evenement.raison}`
    case 'pause':
      return `Pause jusqu'à ${heure(evenement.fin)} : `
        + (LIBELLES_CAUSE[evenement.origine] || evenement.origine)
    case 'reprise':
      return `Reprise : ${RAISONS_REPRISE[evenement.raison] || evenement.raison}`
    case 'retroaction':
      return `Effet de l'écran mesuré à ${evenement.sens === 'allumage' ? 'l\'allumage' : 'l\'extinction'}`
        + ` : ${formaterLux(evenement.avant)} avant, ${formaterLux(evenement.apres)} après`
    case 'allers_retours':
      return 'Allers-retours : 3 changements de sens en 10 minutes'
    case 'mise_en_route':
      return 'Mise en route ouverte : la fonction n\'écrit pas pendant le réglage'
    case 'fin_mise_en_route':
      return 'Mise en route fermée'
    case 'ancrage':
      return `Point d'ancrage : luminosité ${evenement.luminosite} à `
        + `${formaterLux(evenement.lux)} (courbe calée sur ${evenement.points} point`
        + `${evenement.points > 1 ? 's' : ''})`
    case 'activation':
      return 'Fonction activée'
    case 'desactivation':
      return 'Fonction désactivée'
    default:
      return evenement.type
  }
}

// Une ligne par rampe (transition), du départ à l'arrivée.
function texteTransition(evenement) {
  const { ancienne, cible, pas, duree_s: duree, fin, lux, lux_brut: luxBrut } = evenement
  let texte = ancienne != null
    ? `Luminosité ${ancienne} → ${cible} en ${dureeCourte(duree)} (${pas} pas)`
    : `Luminosité réglée à ${cible}`
  if (fin && fin !== 'arrivee') {
    texte += `, interrompue : ${FINS_RAMPE[fin] || LIBELLES_ETAT[fin]?.toLowerCase() || fin}`
  }
  if (lux != null) {
    texte += ` ; lumière lissée ${formaterLux(lux)}`
      + (luxBrut != null ? ` (mesure ${formaterLux(luxBrut)})` : '')
  }
  return texte
}

function dureeCourte(secondes) {
  return secondes < 10
    ? `${secondes.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} s`
    : duree(secondes)
}

function horodatage(iso) {
  const date = new Date(iso)
  const aujourdhui = date.toDateString() === new Date().toDateString()
  return aujourdhui
    ? date.toLocaleTimeString('fr-FR')
    : date.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'medium' })
}

// Réglages du téléviseur qui touchent aussi à la luminosité mais que l'API
// ne laisse pas lire : l'intégration ne peut ni les détecter ni les signaler.
function AideFonctionsTeleviseur() {
  return (
    <section className="carte-luminosite" aria-labelledby="titre-aide-tv">
      <h3 id="titre-aide-tv">Fonctions du téléviseur que l'intégration ne peut pas lire</h3>
      <details className="aide-luminosite">
        <summary>Lumière ambiante du MODE FILMMAKER</summary>
        <p>
          Image › Paramètres avancés › Luminosité, en FILMMAKER MODE seulement : le téléviseur
          optimise l'image « en fonction de la luminosité détectée par le capteur de lumière
          ambiante ». FILMMAKER MODE est laissé de côté par défaut : dans ce mode, c'est cette
          compensation du téléviseur qu'il faut utiliser, pas la luminosité adaptative.
        </p>
      </details>
      <details className="aide-luminosite">
        <summary>Paramètres de luminosité AI</summary>
        <p>
          Général › Service d'AI : l'IA « exprime efficacement les zones plus sombres en fonction
          de l'environnement et des caractéristiques du contenu ». Activée, elle s'ajoute à la
          luminosité adaptative ; son effet exact n'est pas connu. Si la luminosité vous semble
          varier sans raison, désactivez-la pour comparer.
        </p>
      </details>
    </section>
  )
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
