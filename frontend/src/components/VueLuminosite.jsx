import { useEffect, useRef, useState } from 'react'
import * as api from '../api.js'
import { useLuminositeAdaptative } from '../hooks/useLuminositeAdaptative.js'
import {
  ACTIONS_LUMIERE_BLEUE, BORNES, DECALAGE, EMPLACEMENTS, FINS_RAMPE, FINS_SOIREE, heure,
  LIBELLE_HDR, LIBELLES_AMBIANCE, LIBELLES_CAUSE, LIBELLES_ETAT, LIBELLES_PROFIL, MODE_HDR,
  NOMS_PLATEFORME, OPTIONS_AMBIANCE, OPTIONS_AVANCEES, RAISONS_CORRECTION_ECARTEE,
  RAISONS_LUMIERE_BLEUE, seuilsCourbe, texteRapportSecours, validerOptions,
} from '../luminosite.js'
import { libelleChoix } from '../arbre.js'
import { duree } from '../sante.js'
import { libelleModeImage } from '../valeurs.js'
import Interrupteur from './controles/Interrupteur.jsx'
import CourbeLuminosite from './CourbeLuminosite.jsx'
import MiseEnRoute from './MiseEnRoute.jsx'
import SanteLuminosite from './SanteLuminosite.jsx'
import SchemaEmplacement from './SchemaEmplacement.jsx'
import SuggestionsLuminosite from './SuggestionsLuminosite.jsx'

const PAUSE_MANUELLE_MIN = 60

const RAISONS_REPRISE = {
  delai: 'fin du délai de pause',
  bouton: 'bouton Reprendre',
  rallumage: 'téléviseur rallumé',
  changement_eclairage: 'l\'éclairage a nettement changé',
}

const formaterLux = (lux) => `${lux.toLocaleString('fr-FR')} lx`
const signe = (v) => (v > 0 ? `+${v}` : `${v}`)
const RAISONS_BASCULE = { indisponible: 'capteur principal indisponible', fige: 'capteur principal figé' }

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

// Les options avancées et les seuils d'ambiance vides (null) suivent le
// profil ou la courbe, un point intermédiaire, un secours ou une entité de
// début de Soirée vide est absent :
// sans effet sur la comparaison avec les options enregistrées, où ils
// n'apparaissent pas.
function normaliser(options, cles = null) {
  return JSON.stringify(Object.fromEntries(Object.entries(options)
    .filter(([cle, valeur]) => !((cle in OPTIONS_AVANCEES || OPTIONS_AMBIANCE.includes(cle)
      || cle === 'point_intermediaire' || cle === 'capteur_secours' || cle === 'soiree_entite')
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

// D'après Brown et al. (2022), sans promesse de santé (étude, § 3.6.2).
const TEXTE_SOIREE = 'Le soir, la luminosité calculée est baissée d\'une fraction et, si vous le '
  + 'cochez, « Réduire la lumière bleue » est activé. D\'après un consensus de chercheurs (Brown '
  + 'et al., 2022), limiter la lumière reçue le soir passe d\'abord par baisser la luminosité des '
  + 'écrans ; réduire la lumière bleue n\'en retire qu\'une partie. Aucun effet sur le sommeil '
  + 'n\'est promis.'

const DOMAINES_SOURCE = {
  input_datetime: 'heure',
  binary_sensor: 'capteur binaire',
  schedule: 'planning',
}

function libelleSource(source) {
  return `${source.nom} (${DOMAINES_SOURCE[source.domaine] || source.domaine})`
}

// Début de la Soirée, en clair : heure fixe ou entité.
function texteDebutSoiree(options, sources) {
  const entite = options.soiree_entite
  if (!entite) return `à ${options.soiree_debut}`
  const source = sources.find((s) => s.entity_id === entite)
  const nom = source ? `« ${source.nom} »` : entite
  return entite.startsWith('input_datetime.') ? `à l'heure de ${nom}` : `quand ${nom} passe à « on »`
}

function libelleCapteur(capteur) {
  const valeur = capteur.unite ? `${capteur.valeur} ${capteur.unite}` : capteur.valeur
  return `${capteur.nom} (${valeur})`
}

export default function VueLuminosite({
  index, luminosite, lectureSeule, connexion, ecriturePossible, reglages, onEcrire, onReprendre,
  onRecharge,
}) {
  const { configuration, erreur, details, journal, sante, suggestions, relire } =
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
            options={configuration.options}
            sources={configuration.sources_soiree ?? []}
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
            suggestions={suggestions?.suggestions.length ?? 0}
            lectureSeule={lectureSeule}
            onAppliquer={enregistrer}
            onDesactiverEconomie={api.desactiverEconomieEnergie}
          />
          <ReglagesLuminosite
            index={index}
            configuration={configuration}
            lux={details?.lux_filtre ?? details?.lux ?? null}
            details={details}
            suggestions={suggestions}
            lectureSeule={lectureSeule}
            onEnregistrer={enregistrer}
            onRelire={relire}
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

function EtatLuminosite({ index, etat, options, sources, lectureSeule, onReprendre }) {
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
          <dd>
            {etat.cible ?? '—'}
            {etat.decalage || etat.soiree?.active ? (
              <span className="texte-attenue detail-cible">
                {' '}courbe {etat.cible_courbe ?? '—'}
                {etat.decalage ? `, décalage ${signe(etat.decalage)}` : ''}
                {etat.soiree?.active ? `, Soirée −${etat.soiree.reduction} %` : ''}
              </span>
            ) : null}
          </dd>
        </div>
        <div>
          <dt>Luminosité du téléviseur</dt>
          <dd>{etat.actuelle ?? '—'}</dd>
        </div>
        <div>
          <dt>Ambiance de la pièce</dt>
          <dd>
            {etat.ambiance ? LIBELLES_AMBIANCE[etat.ambiance] : '—'}
            {etat.ambiance && etat.ambiance_depuis && (
              <span className="texte-attenue detail-cible"> depuis {heure(etat.ambiance_depuis)}</span>
            )}
          </dd>
        </div>
      </dl>

      <DecalageLuminosite decalage={etat.decalage ?? 0} desactive={lectureSeule} />

      <EtatSoiree
        soiree={etat.soiree}
        sourceOk={etat.source_soiree_ok}
        modeExclu={etat.mode_exclu}
        options={options}
        sources={sources}
        desactive={lectureSeule || envoi}
        onTerminer={() => agir(api.terminerSoiree)}
      />

      {etat.rampe && <TransitionLuminosite rampe={etat.rampe} cible={etat.cible}
        actuelle={etat.actuelle} />}

      {etat.capteur_actif === 'secours' && (
        <p className="ligne-carte message message-conflit">
          Le capteur de secours a pris le relais : capteur principal{' '}
          {etat.lux_principal == null ? 'indisponible' : 'figé'}. Ses mesures sont converties avec
          leur rapport habituel ; le principal reprendra la main dès sa prochaine mesure.
        </p>
      )}
      {(etat.lux_principal ?? etat.lux) != null && (
        <p className="ligne-carte texte-attenue">
          Dernière mesure du capteur{etat.secours ? ' principal' : ''} :{' '}
          {formaterLux(etat.lux_principal ?? etat.lux)}
          {etat.derniere_mesure && ` à ${heure(etat.derniere_mesure)}`}.
          {' '}{texteProfil(etat.profil)}
        </p>
      )}
      {etat.secours && (
        <p className="ligne-carte texte-attenue">
          Capteur de secours :{' '}
          {etat.secours.lux != null ? formaterLux(etat.secours.lux) : 'indisponible'}
          {etat.secours.derniere_mesure && ` à ${heure(etat.secours.derniere_mesure)}`}.
          {' '}{texteRapportSecours(etat.secours)}
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
            {etat.fin_pause && `Reprise à ${heure(etat.fin_pause)}`}
            {etat.fin_pause && texteRepriseLux(etat.reprise_lux)}
            {etat.fin_pause && '.'}
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

// Au clavier, le décalage part une fois les flèches relâchées un instant :
// chaque position traversée relancerait une transition et noterait une ligne
// au journal.
const ATTENTE_CLAVIER_MS = 700

// Décalage pilotable (R11) : ajouté à la cible de la courbe. Envoyé au
// relâchement du curseur, pas à chaque position traversée.
function DecalageLuminosite({ decalage, desactive }) {
  const [valeur, setValeur] = useState(decalage)
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState(null)
  const minuterie = useRef(null)
  useEffect(() => {
    if (!envoi && minuterie.current === null) setValeur(decalage)
  }, [decalage, envoi])
  useEffect(() => () => clearTimeout(minuterie.current), [])

  function differer(nouvelle) {
    clearTimeout(minuterie.current)
    minuterie.current = setTimeout(() => {
      minuterie.current = null
      regler(nouvelle)
    }, ATTENTE_CLAVIER_MS)
  }

  async function regler(nouvelle) {
    clearTimeout(minuterie.current)
    minuterie.current = null
    if (nouvelle === decalage) return
    setErreur(null)
    setEnvoi(true)
    try {
      await api.reglerDecalage(nouvelle)
    } catch (err) {
      setErreur(err.message)
      setValeur(decalage)
    } finally {
      setEnvoi(false)
    }
  }

  const [bas, haut] = DECALAGE
  return (
    <div className="ligne-carte decalage-luminosite">
      <label className="champ-decalage">
        <span>Décalage</span>
        <span className="controle-curseur">
          <input
            type="range"
            min={bas}
            max={haut}
            step="1"
            value={valeur}
            disabled={desactive}
            aria-valuetext={signe(valeur)}
            onChange={(e) => setValeur(e.target.valueAsNumber)}
            onPointerUp={(e) => regler(e.currentTarget.valueAsNumber)}
            onKeyUp={(e) => differer(e.currentTarget.valueAsNumber)}
            onBlur={(e) => regler(e.currentTarget.valueAsNumber)}
          />
          <output className="valeur-curseur valeur-decalage">{signe(valeur)}</output>
        </span>
      </label>
      <button type="button" className="bouton-secondaire" disabled={desactive || envoi
        || decalage === 0} onClick={() => {
        setValeur(0)
        regler(0)
      }}>
        Remettre à 0
      </button>
      <p className="texte-attenue">
        Ajouté à la luminosité calculée (de {bas} à +{haut}, résultat borné à 0–100). Vos
        automatisations peuvent régler l'entité « Décalage de la luminosité adaptative » selon
        l'heure, la présence ou l'application ; le changer ne met jamais la fonction en pause, et
        pendant une pause il s'appliquera à la reprise.
      </p>
      {erreur && <p className="erreur-reglage" role="alert">{erreur}</p>}
    </div>
  )
}

// Soirée (soiree.py) : en cours, terminée à la main, ou à venir ; état de
// « Réduire la lumière bleue » d'après la valeur notifiée par le téléviseur.
function EtatSoiree({ soiree, sourceOk, modeExclu, options, sources, desactive, onTerminer }) {
  if (!soiree?.configuree) return null
  const bleue = soiree.lumiere_bleue
  let texteBleue = null
  if (soiree.active && bleue.option) {
    if (bleue.reprise) {
      texteBleue = '« Réduire la lumière bleue » réglé ailleurs : laissé tel quel jusqu\'à la fin.'
    } else if (modeExclu) {
      texteBleue = '« Réduire la lumière bleue » n\'est pas activé dans ce mode laissé de côté.'
    } else if (bleue.refusee) {
      texteBleue = '« Réduire la lumière bleue » : écriture refusée par le téléviseur.'
    } else if (bleue.valeur === 'on') {
      texteBleue = '« Réduire la lumière bleue » activé.'
    }
  }
  return (
    <div className="ligne-carte etat-soiree" aria-live="polite">
      {soiree.active ? (
        <p>
          <span className="badge-soiree">Soirée</span>{' '}
          Jusqu'à {heure(soiree.fin)} : luminosité −{soiree.reduction} %.
          {texteBleue && ` ${texteBleue}`}
          <button type="button" className="bouton-reprendre" disabled={desactive}
            onClick={onTerminer}>
            Terminer la soirée
          </button>
        </p>
      ) : (
        <p className="texte-attenue">
          {soiree.terminee_jusqua
            ? `Soirée terminée jusqu'à ${heure(soiree.terminee_jusqua)}.`
            : `Soirée ${texteDebutSoiree(options, sources)}, jusqu'à ${options.soiree_fin} : `
              + `luminosité −${soiree.reduction} %${bleue.option
                ? ' et « Réduire la lumière bleue »' : ''}.`}
        </p>
      )}
      {sourceOk === false && (
        <p className="message message-conflit">
          La Soirée ne peut pas commencer : l'entité de début est introuvable, indisponible, ou
          ne donne pas d'heure. Le détail est dans Santé de l'installation.
        </p>
      )}
    </div>
  )
}

// Limites d'éclairage qui lèveront la pause (reprise.bornes_reprise) ; l'une
// manque quand la courbe est plate de ce côté.
function texteRepriseLux(limites) {
  if (!limites) return ''
  const { bas, haut } = limites
  if (bas != null && haut != null) {
    return `, ou dès que l'éclairage passe sous ${formaterLux(bas)} ou au-delà de `
      + `${formaterLux(haut)}`
  }
  if (bas != null) return `, ou dès que l'éclairage passe sous ${formaterLux(bas)}`
  if (haut != null) return `, ou dès que l'éclairage dépasse ${formaterLux(haut)}`
  return ''
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

function ReglagesLuminosite({
  index, configuration, lux, details, suggestions, lectureSeule, onEnregistrer, onRelire,
}) {
  const { options, capteurs, modes_proposes: modes } = configuration
  const sources = configuration.sources_soiree ?? []
  const [brouillon, setBrouillon] = useState(options)
  // Plage de la suggestion dont la courbe est tracée en tirets.
  const [apercu, setApercu] = useState(null)
  const [envoi, setEnvoi] = useState(false)
  const [message, setMessage] = useState(null)
  const modifie = normaliser(brouillon) !== normaliser(options)
  const ancrages = options.ancrages ?? []
  const courbeModifiee = normaliser(brouillon, CLES_COURBE) !== normaliser(options, CLES_COURBE)
  const erreurs = validerOptions(brouillon)
  const valide = Object.keys(erreurs).length === 0
  // Suggestion calculée sur la courbe enregistrée : sans aperçu pendant une
  // retouche.
  const suggestionApercue = courbeModifiee ? null
    : suggestions?.suggestions.find((s) => s.plage === apercu) ?? null

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

  // Heure « HH:MM » (Soirée), dans le fuseau de Home Assistant.
  function champHeure(cle, libelle) {
    return (
      <label className="champ-luminosite">
        <span>{libelle}</span>
        <input
          type="time"
          className="saisie-heure"
          value={brouillon[cle] ?? ''}
          aria-invalid={erreurs[cle] ? true : undefined}
          onChange={(e) => changer({ [cle]: e.target.value || null })}
        />
        {erreurs[cle] && <span className="erreur-reglage">{erreurs[cle]}</span>}
      </label>
    )
  }

  // Seuil de l'ambiance : vide, il suit la courbe (affiché en indication).
  function champSeuil(cle, libelle, indice) {
    const [bas, haut] = BORNES[cle]
    const valeur = brouillon[cle]
    const courbe = seuilsCourbe(brouillon)[indice]
    return (
      <label key={cle} className="champ-luminosite">
        <span>{libelle}</span>
        <span className="saisie-unite">
          <input
            type="number"
            min={bas}
            max={haut}
            step="0.1"
            value={valeur == null || Number.isNaN(valeur) ? '' : valeur}
            placeholder={courbe != null && Number.isFinite(courbe)
              ? `courbe : ${(Math.round(courbe * 10) / 10).toLocaleString('fr-FR')}` : 'courbe'}
            aria-invalid={erreurs[cle] ? true : undefined}
            onChange={(e) => changer({ [cle]: e.target.value === '' ? null : e.target.valueAsNumber })}
          />
          <span className="texte-attenue">lx</span>
        </span>
        {erreurs[cle] && <span className="erreur-reglage">{erreurs[cle]}</span>}
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
  const secoursConnu = capteurs.some((c) => c.entity_id === brouillon.capteur_secours)
  const retrait = !brouillon.capteur_lux
  const sourceConnue = sources.some((s) => s.entity_id === brouillon.soiree_entite)
  // Rapport appris : seulement pour la paire enregistrée.
  const rapport = details?.secours && brouillon.capteur_secours === options.capteur_secours
    && brouillon.capteur_lux === options.capteur_lux ? texteRapportSecours(details.secours) : null

  return (
    <form className="carte-luminosite" onSubmit={enregistrer} aria-labelledby="titre-courbe">
      <h3 id="titre-courbe">Courbe</h3>
      <CourbeLuminosite
        options={valide ? brouillon : options}
        lux={lux}
        ancrages={courbeModifiee ? [] : ancrages}
        corrections={suggestions?.corrections ?? []}
        apercu={suggestionApercue?.options ?? null}
        decalage={details?.decalage ?? 0}
        reduction={details?.soiree?.active ? details.soiree.reduction : 0}
        seuils={seuilsAmbiance(valide ? brouillon : options)}
        desactive={envoi}
        onChanger={changer}
      />
      <SuggestionsLuminosite
        index={index}
        donnees={suggestions}
        options={options}
        ancrages={ancrages}
        apercu={suggestionApercue ? apercu : null}
        bloque={courbeModifiee}
        lectureSeule={lectureSeule}
        onApercu={setApercu}
        onAppliquee={onRelire}
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
          <span>Capteur de secours (facultatif)</span>
          <select
            value={brouillon.capteur_secours ?? ''}
            aria-invalid={erreurs.capteur_secours ? true : undefined}
            onChange={(e) => changer({ capteur_secours: e.target.value || null })}
          >
            <option value="">Aucun</option>
            {capteurs.filter((c) => c.entity_id !== brouillon.capteur_lux).map((c) => (
              <option key={c.entity_id} value={c.entity_id}>{libelleCapteur(c)}</option>
            ))}
            {!secoursConnu && brouillon.capteur_secours && (
              <option value={brouillon.capteur_secours}>{brouillon.capteur_secours} (introuvable)</option>
            )}
          </select>
          {erreurs.capteur_secours && (
            <span className="erreur-reglage">{erreurs.capteur_secours}</span>
          )}
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
      {brouillon.capteur_secours && (
        <p className="texte-attenue">
          Le secours prend le relais quand le capteur principal est indisponible ou figé, une
          fois appris leur rapport habituel (une demi-heure de mesures communes dans une lumière
          stable). Un secours dont le rapport varie trop (extérieur, près d'une fenêtre) n'est
          pas utilisé.{rapport && ` ${rapport}`}
        </p>
      )}
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
      <label className="case-mode case-reprise">
        <input
          type="checkbox"
          checked={brouillon.reprise_sur_changement ?? true}
          onChange={(e) => changer({ reprise_sur_changement: e.target.checked })}
        />
        Reprendre quand l'éclairage change nettement
      </label>
      <p className="texte-attenue">
        La pause prend fin aussi au prochain allumage du téléviseur
        {(brouillon.reprise_sur_changement ?? true)
          && ', et dès que la lumière de la pièce double ou diminue de moitié depuis votre '
            + 'réglage (sauf la pause « 1 h » demandée ici, faite pour durer)'}
        . Un réglage gardé 10 minutes est retenu comme correction.
      </p>

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
        <p className="texte-attenue">
          Entité « Ambiance » (pour vos automatisations) : sombre, intermédiaire ou claire, avec
          une marge de 25 % autour de chaque seuil et 10 minutes avant tout changement. Vides, les
          seuils sont les tiers de la courbe et suivent ses retouches ; remplis, ils restent fixes.
        </p>
        <div className="grille-champs">
          {champSeuil('ambiance_sombre', 'Ambiance sombre en dessous de', 0)}
          {champSeuil('ambiance_claire', 'Ambiance claire au-delà de', 1)}
        </div>
      </details>

      <details className="reglages-avances reglages-soiree">
        <summary>Soirée{options.soiree ? ' (activée)' : ''}</summary>
        <p className="texte-attenue">{TEXTE_SOIREE}</p>
        <label className="case-mode">
          <input
            type="checkbox"
            checked={brouillon.soiree ?? false}
            onChange={(e) => changer({ soiree: e.target.checked })}
          />
          Activer la Soirée
        </label>
        <fieldset className="champs-soiree" disabled={!brouillon.soiree}>
          <div className="grille-champs">
            <label className="champ-luminosite champ-large">
              <span>Début</span>
              <select
                value={brouillon.soiree_entite ?? ''}
                aria-invalid={erreurs.soiree_entite ? true : undefined}
                onChange={(e) => changer({ soiree_entite: e.target.value || null })}
              >
                <option value="">À heure fixe</option>
                {sources.map((s) => (
                  <option key={s.entity_id} value={s.entity_id}>{libelleSource(s)}</option>
                ))}
                {!sourceConnue && brouillon.soiree_entite && (
                  <option value={brouillon.soiree_entite}>
                    {brouillon.soiree_entite} (introuvable)
                  </option>
                )}
              </select>
              {erreurs.soiree_entite && (
                <span className="erreur-reglage">{erreurs.soiree_entite}</span>
              )}
            </label>
            {!brouillon.soiree_entite && champHeure('soiree_debut', 'Heure de début')}
            {champHeure('soiree_fin', 'Heure de fin')}
            {champNombre('soiree_reduction', 'Baisse de la luminosité', '%')}
          </div>
          <p className="texte-attenue">
            {brouillon.soiree_entite?.startsWith('input_datetime.')
              ? 'La Soirée commence chaque jour à l\'heure de cette entité. '
              : brouillon.soiree_entite
                ? 'La Soirée commence quand cette entité passe à « on » et finit quand elle '
                  + 'repasse à « off ». '
                : ''}
            Elle finit à l'heure de fin ou par « Terminer la soirée » ; téléviseur éteint puis
            rallumé avant, elle continue. La baisse est retirée de la luminosité calculée,
            décalage compris (20 % : 100 devient 80, 40 devient 32) ; une pause après un réglage
            manuel est respectée, la baisse s'applique à la reprise.
          </p>
          <label className="case-mode">
            <input
              type="checkbox"
              checked={brouillon.soiree_lumiere_bleue ?? false}
              onChange={(e) => changer({ soiree_lumiere_bleue: e.target.checked })}
            />
            Activer aussi « Réduire la lumière bleue »
          </label>
          <p className="texte-attenue">
            Réglage commun à tous les modes d'image : il n'est pas activé dans les modes laissés
            de côté, et retrouve sa valeur d'avant à la fin de la Soirée. Si vous le changez
            pendant la Soirée, il n'est plus touché jusqu'à la fin.
          </p>
        </fieldset>
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

// Seuils de l'ambiance (ambiance.seuils) : figés, sinon tiers de la courbe.
function seuilsAmbiance(options) {
  const [sombre, claire] = seuilsCourbe(options)
  return [options.ambiance_sombre ?? sombre, options.ambiance_claire ?? claire]
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
        + (evenement.raison === 'changement_eclairage'
          ? ` (${formaterLux(evenement.lux_depart)} → ${formaterLux(evenement.lux)})` : '')
    case 'correction':
      return `Correction retenue : luminosité ${evenement.valeur} à `
        + `${formaterLux(evenement.lux)} (la courbe donnait ${evenement.cible})`
    case 'correction_ecartee':
      return `Correction non retenue (${evenement.valeur}) : `
        + (RAISONS_CORRECTION_ECARTEE[evenement.raison] || evenement.raison)
    case 'suggestion_appliquee':
      return `Suggestion appliquée : ${evenement.ecart > 0 ? '+' : ''}${Math.round(evenement.ecart)} vers `
        + `${formaterLux(evenement.lux)} (${evenement.corrections} corrections)`
    case 'suggestion_ignoree':
      return `Suggestion ignorée (${evenement.corrections} corrections écartées)`
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
        + `${evenement.points > 1 ? 's' : ''}`
        + `${evenement.decalage ? `, décalage ${signe(evenement.decalage)} déduit` : ''})`
    case 'decalage':
      return `Décalage ${signe(evenement.ancien)} → ${signe(evenement.nouveau)} `
        + `(${LIBELLES_CAUSE[evenement.origine]?.replace('réglage ', '') || evenement.origine})`
    case 'bascule':
      return `Capteur de secours en relais : ${RAISONS_BASCULE[evenement.raison] || evenement.raison}`
        + ` (mesures × ${evenement.facteur.toLocaleString('fr-FR')})`
    case 'retour':
      return 'Retour au capteur principal'
    case 'secours_perdu':
      return 'Capteur de secours perdu à son tour : luminosité gardée'
    case 'rapport_secours':
      return evenement.etat === 'stable'
        ? `Rapport des capteurs appris : le secours peut prendre le relais (× `
          + `${evenement.facteur.toLocaleString('fr-FR')})`
        : 'Rapport des capteurs devenu instable : le secours ne prendra plus le relais'
    case 'ambiance':
      return `Ambiance ${LIBELLES_AMBIANCE[evenement.valeur]} (${formaterLux(evenement.lux)}), `
        + `après ${LIBELLES_AMBIANCE[evenement.ancienne]}`
    case 'soiree_debut':
      return `Soirée : luminosité −${evenement.reduction} % jusqu'à ${heure(evenement.fin)}`
    case 'soiree_fin':
      return `Fin de la Soirée : ${FINS_SOIREE[evenement.raison] || evenement.raison}`
        + (evenement.origine
          ? ` (${LIBELLES_CAUSE[evenement.origine]?.replace('réglage ', '') || evenement.origine})`
          : '')
    case 'lumiere_bleue':
      return `« Réduire la lumière bleue » ${ACTIONS_LUMIERE_BLEUE[evenement.action]
        || evenement.action}`
        + (evenement.raison ? ` (${RAISONS_LUMIERE_BLEUE[evenement.raison] || evenement.raison})` : '')
        + (evenement.origine
          ? ` (${LIBELLES_CAUSE[evenement.origine]?.replace('réglage ', '') || evenement.origine})`
          : '')
        + (evenement.erreur ? ` : ${evenement.erreur}` : '')
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
