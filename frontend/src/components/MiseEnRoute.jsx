import { useEffect, useState } from 'react'
import * as api from '../api.js'
import { valeurDe } from '../arbre.js'
import {
  EMPLACEMENTS, LIBELLES_PROFIL, NOMS_PLATEFORME, pointsCourbe,
} from '../luminosite.js'
import { duree } from '../sante.js'
import { libelleModeImage } from '../valeurs.js'
import Curseur from './controles/Curseur.jsx'
import CourbeLuminosite from './CourbeLuminosite.jsx'
import { ConflitLuminosite } from './SanteLuminosite.jsx'
import SchemaEmplacement from './SchemaEmplacement.jsx'

// Parcours de mise en route (docs/etude-luminosite-adaptative.md, § 4.6) :
// d'abord ce qui conditionne la réussite (capteur, emplacement,
// vérifications), ensuite la préférence (point d'ancrage), enfin
// l'activation. Relançable ; `depart` = 'ancrage' pour refaire un point seul
// (deuxième point, le soir dans le noir).
const ETAPES = ['Capteur', 'Emplacement', 'Vérifications', 'Point d\'ancrage', 'Activation']
const ETAPE_ANCRAGE = 3

const formaterLux = (lux) => `${lux.toLocaleString('fr-FR')} lx`

const PHRASE_SANTE = 'Dans les prochains jours, la page vous dira si l\'installation fonctionne bien.'

function age(secondes) {
  return secondes < 60 ? 'à l\'instant' : `il y a ${duree(secondes)}`
}

export default function MiseEnRoute({
  index, configuration, luminosite, details, connexion, ecriturePossible, reglages, depart,
  onEnregistrer, onEcrire, onTerminer,
}) {
  const { options, capteurs } = configuration
  const [etape, setEtape] = useState(depart === 'ancrage' ? ETAPE_ANCRAGE : 0)
  const [capteur, setCapteur] = useState(options.capteur_lux || capteurs[0]?.entity_id || '')
  const [emplacement, setEmplacement] = useState(options.emplacement_capteur)
  const [secours, setSecours] = useState(options.capteur_secours || '')
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState(null)
  const [ancrage, setAncrage] = useState(null)
  const configuree = Boolean(luminosite)

  // Pendant le réglage du point d'ancrage, la fonction n'écrit pas et ne se
  // met pas en pause ; l'abonnement prend fin avec l'étape ou la page.
  useEffect(() => {
    if (etape !== ETAPE_ANCRAGE || !configuree) return undefined
    return api.suivreMiseEnRoute()
  }, [etape, configuree])

  async function agir(action) {
    setErreur(null)
    setEnvoi(true)
    try {
      await action()
      return true
    } catch (err) {
      setErreur(err.message)
      return false
    } finally {
      setEnvoi(false)
    }
  }

  async function enregistrerCapteur() {
    // Un secours égal au nouveau principal n'a plus lieu d'être.
    const secoursRetenu = secours && secours !== capteur ? secours : null
    const inchange = capteur === options.capteur_lux
      && emplacement === options.emplacement_capteur
      && secoursRetenu === (options.capteur_secours || null)
    if (inchange || await agir(() => onEnregistrer({
      capteur_lux: capteur, emplacement_capteur: emplacement, capteur_secours: secoursRetenu,
    }))) setEtape(2)
  }

  async function ancrer() {
    await agir(async () => setAncrage(await api.ancrerLuminosite()))
  }

  async function activer() {
    if (await agir(() => api.activerLuminosite(true))) setEtape(5)
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

  const pret = configuree && details
  let contenu
  if (etape === 0) {
    contenu = (
      <EtapeCapteur capteurs={capteurs} pieceTv={configuration.piece_televiseur}
        choisi={capteur} onChoisir={setCapteur} secours={secours} onChoisirSecours={setSecours} />
    )
  } else if (etape === 1) {
    contenu = <EtapeEmplacement choisi={emplacement} onChoisir={setEmplacement} desactive={envoi} />
  } else if (!pret) {
    contenu = <p className="texte-attenue" role="status">Préparation de la fonction…</p>
  } else if (etape === 2) {
    contenu = (
      <EtapeVerifications index={index} details={details} connexion={connexion}
        ecriturePossible={ecriturePossible} desactive={envoi}
        onDesactiverEconomie={() => agir(api.desactiverEconomieEnergie)} />
    )
  } else if (etape === ETAPE_ANCRAGE) {
    contenu = (
      <EtapeAncrage index={index} details={details} reglages={reglages}
        options={options} ancrage={ancrage} envoi={envoi}
        bloquee={bloquage(details, connexion, ecriturePossible) !== null}
        onEcrire={onEcrire} onAncrer={ancrer} />
    )
  } else if (etape === 4) {
    contenu = (
      <div className="etape-mise-en-route">
        <p>
          {luminosite.etat === 'desactivee' || luminosite.etat === 'pause'
            ? 'Tout est prêt. La luminosité suivra désormais la lumière de la pièce, en douceur.'
            : 'La fonction est déjà active : elle suit la courbe calée sur votre réglage.'}
        </p>
        <p className="texte-attenue">{PHRASE_SANTE}</p>
      </div>
    )
  } else {
    contenu = (
      <div className="etape-mise-en-route" role="status">
        <p>La luminosité adaptative est active.</p>
        <p className="texte-attenue">{PHRASE_SANTE}</p>
        {(ancrage?.options.ancrages?.length ?? 0) < 2 && (
          <p>
            Ce soir, dans le noir, revenez sur cette page pour refaire le réglage : avec ce
            deuxième point, la courbe suivra aussi votre préférence dans l'obscurité.
          </p>
        )}
      </div>
    )
  }

  const bloque = etape >= 2 && pret && bloquage(details, connexion, ecriturePossible)
  const suivant = {
    0: { libelle: 'Suivant', action: () => setEtape(1), actif: Boolean(capteur) },
    1: { libelle: 'Enregistrer et continuer', action: enregistrerCapteur, actif: true },
    2: { libelle: 'Suivant', action: () => setEtape(ETAPE_ANCRAGE), actif: pret && !bloque },
    3: { libelle: 'Suivant', action: () => setEtape(4), actif: Boolean(ancrage) },
    4: luminosite?.etat === 'desactivee' || luminosite?.etat === 'pause'
      ? { libelle: 'Activer la luminosité adaptative', action: activer, actif: true }
      : { libelle: 'Terminer', action: onTerminer, actif: true },
    5: { libelle: 'Fermer', action: onTerminer, actif: true },
  }[etape]
  const premiere = depart === 'ancrage' ? ETAPE_ANCRAGE : 0

  return (
    <section className="carte-luminosite mise-en-route" aria-labelledby="titre-mise-en-route">
      <div className="entete-carte">
        <h3 id="titre-mise-en-route">
          {depart === 'ancrage' ? 'Nouveau point d\'ancrage' : 'Mise en route'}
        </h3>
        {configuree && (
          <button type="button" className="bouton-secondaire" onClick={onTerminer}>
            {etape === 5 ? 'Fermer' : 'Quitter'}
          </button>
        )}
      </div>
      <ol className="etapes-mise-en-route" aria-label="Étapes">
        {ETAPES.map((nom, i) => (i < premiere ? null : (
          <li key={nom} aria-current={i === Math.min(etape, 4) ? 'step' : undefined}
            className={i < etape ? 'etape-faite' : undefined}>
            {nom}
          </li>
        )))}
      </ol>
      <h4 className="titre-etape">{ETAPES[Math.min(etape, 4)]}</h4>
      {contenu}
      {erreur && <p className="erreur-reglage" role="alert">{erreur}</p>}
      <div className="actions-reglages">
        {etape === ETAPE_ANCRAGE && !ancrage && (
          <button type="button" className="bouton-secondaire" disabled={envoi}
            onClick={() => setEtape(4)}>
            Passer cette étape
          </button>
        )}
        {etape > premiere && etape < 5 && (
          <button type="button" className="bouton-secondaire" disabled={envoi}
            onClick={() => setEtape(etape - 1)}>
            Retour
          </button>
        )}
        <button type="button" className="bouton-principal" disabled={!suivant.actif || envoi}
          onClick={suivant.action}>
          {envoi ? 'Un instant…' : suivant.libelle}
        </button>
      </div>
    </section>
  )
}

// Ce qui empêche de régler le point d'ancrage, ou null.
function bloquage(details, connexion, ecriturePossible) {
  if (connexion !== 'connecte') return 'deconnecte'
  if (ecriturePossible === false) return 'consultation'
  if (details.mode_exclu) return 'mode_exclu'
  if (details.conflit) return 'conflit'
  if (details.lux == null) return 'capteur'
  return null
}

function EtapeCapteur({ capteurs, pieceTv, choisi, onChoisir, secours, onChoisirSecours }) {
  const autres = capteurs.filter((c) => c.entity_id !== choisi)
  return (
    <>
      <fieldset className="etape-mise-en-route">
        <legend className="texte-attenue">
          {pieceTv
            ? `Les capteurs de la pièce du téléviseur (${pieceTv}) sont proposés en premier, puis ceux
              qui ont donné une mesure dans l'heure.`
            : 'Les capteurs qui ont donné une mesure dans l\'heure sont proposés en premier. '
              + 'Rangez le téléviseur dans une pièce (Paramètres › Appareils) pour voir d\'abord '
              + 'les capteurs de cette pièce.'}
        </legend>
        <ul className="liste-capteurs">
          {capteurs.map((c) => {
            const plateforme = c.plateforme && (NOMS_PLATEFORME[c.plateforme] || c.plateforme)
            return (
              <li key={c.entity_id}>
                <label className={`choix-capteur${choisi === c.entity_id ? ' choix-capteur-choisi' : ''}`}>
                  <input type="radio" name="capteur" value={c.entity_id}
                    checked={choisi === c.entity_id} onChange={() => onChoisir(c.entity_id)} />
                  <span className="nom-capteur">{c.nom}</span>
                  <span className="texte-attenue">
                    {c.piece ?? 'Pièce non renseignée'}
                    {c.meme_piece && <strong className="badge-piece"> · même pièce que le téléviseur</strong>}
                  </span>
                  <span>
                    {c.unite ? `${c.valeur} ${c.unite}` : c.valeur}, {age(c.age_s)}
                  </span>
                  <span className="texte-attenue">
                    Profil pressenti : {LIBELLES_PROFIL[c.profil] || c.profil}
                    {plateforme && ` (${plateforme})`}
                  </span>
                </label>
              </li>
            )
          })}
        </ul>
      </fieldset>
      {autres.length > 0 && (
        <label className="champ-luminosite champ-large choix-secours">
          <span>Capteur de secours (facultatif)</span>
          <select value={secours === choisi ? '' : secours}
            onChange={(e) => onChoisirSecours(e.target.value)}>
            <option value="">Aucun</option>
            {autres.map((c) => (
              <option key={c.entity_id} value={c.entity_id}>
                {c.nom}{c.piece ? ` (${c.piece})` : ''}
              </option>
            ))}
          </select>
          <span className="texte-attenue">
            Il prend le relais si le capteur choisi tombe en panne (pile, réseau), une fois appris
            leur rapport habituel. Choisissez-le dans la même pièce, à l'abri du jour direct : un
            capteur extérieur ou près d'une fenêtre ne sera pas utilisé.
          </span>
        </label>
      )}
    </>
  )
}

function EtapeEmplacement({ choisi, onChoisir, desactive }) {
  const emplacement = EMPLACEMENTS[choisi] || EMPLACEMENTS.inconnu
  return (
    <div className="etape-mise-en-route">
      <p>Où se trouve ce capteur ? Touchez sa place sur le schéma, ou choisissez dans la liste.</p>
      <div className="emplacement-capteur">
        <SchemaEmplacement choisi={choisi} desactive={desactive} onChoisir={onChoisir} />
        <div>
          <select value={choisi} disabled={desactive} aria-label="Emplacement du capteur"
            onChange={(e) => onChoisir(e.target.value)}>
            {Object.entries(EMPLACEMENTS).map(([cle, { libelle }]) => (
              <option key={cle} value={cle}>{libelle}</option>
            ))}
          </select>
          <p className={emplacement.avertissement ? 'message message-conflit' : 'texte-attenue'}
            role={emplacement.avertissement ? 'alert' : undefined}>
            {emplacement.texte}
          </p>
        </div>
      </div>
    </div>
  )
}

function Controle({ ok, children }) {
  return (
    <li className={ok ? undefined : 'controle-a-corriger'}>
      <span className={`symbole-sante${ok ? ' symbole-ok' : ''}`} aria-hidden="true">
        {ok ? '✓' : '⚠'}
      </span>
      <div>{children}</div>
    </li>
  )
}

function EtapeVerifications({ index, details, connexion, ecriturePossible, desactive,
  onDesactiverEconomie }) {
  const mode = details.mode_image && libelleModeImage(index, details.mode_image)
  const ageMesure = details.derniere_mesure
    ? (Date.now() - new Date(details.derniere_mesure).getTime()) / 1000
    : null
  return (
    <ul className="controles-sante controles-mise-en-route">
      <Controle ok={connexion === 'connecte'}>
        {connexion === 'connecte'
          ? 'Téléviseur allumé et connecté.'
          : 'Téléviseur éteint ou injoignable : allumez-le pour continuer.'}
      </Controle>
      <Controle ok={ecriturePossible !== false}>
        {ecriturePossible !== false
          ? 'Le téléviseur accepte les changements de réglages.'
          : 'Le téléviseur n\'accepte pas l\'écriture des réglages : la fonction ne pourrait rien '
            + 'changer (voir Paramètres › Réparations).'}
      </Controle>
      <Controle ok={!details.conflit}>
        {details.conflit
          ? <ConflitLuminosite conflit={details.conflit} economieEnergie={details.economie_energie}
            desactive={desactive} onDesactiver={onDesactiverEconomie} />
          : 'Aucune fonction du téléviseur ne règle la luminosité en même temps '
            + '(économie d\'énergie, mode Éco).'}
      </Controle>
      <Controle ok={!details.mode_exclu}>
        {details.mode_exclu
          ? `Mode d'image actuel : ${mode || 'inconnu'}, laissé de côté (mode calibré). Passez dans `
            + 'le mode que vous utilisez au quotidien (Standard, par exemple) pour régler le point '
            + 'd\'ancrage.'
          : `Mode d'image actuel : ${mode || 'inconnu'}. La luminosité est propre à chaque mode : `
            + 'la courbe s\'applique à tous ceux qui ne sont pas laissés de côté.'}
      </Controle>
      <Controle ok={details.lux != null && details.etat !== 'capteur_fige'}>
        {details.lux == null
          ? 'Le capteur ne donne pas de mesure : vérifiez qu\'il est disponible dans Home Assistant.'
          : `Le capteur répond : ${formaterLux(details.lux)}`
            + (ageMesure != null ? `, dernière mesure ${age(ageMesure)}.` : '.')}
      </Controle>
    </ul>
  )
}

const TEXTES_BORNE = {
  min: 'la luminosité minimale a été abaissée à votre réglage',
  max: 'la luminosité maximale a été relevée à votre réglage',
  min_max: 'les luminosités minimale et maximale ont été élargies',
}

function texteCompteRendu({ compte_rendu: cr, options }) {
  const phrases = [cr.points === 2
    ? 'La courbe passe par vos deux points : sa pente suit aussi votre préférence.'
    : 'La courbe a été décalée pour passer par votre réglage, sa pente conservée.']
  if (cr.borne_etendue) phrases.push(`Au passage, ${TEXTES_BORNE[cr.borne_etendue]}.`)
  if (cr.coupee) {
    phrases.push('La partie de la courbe hors de portée du capteur (sous 1 lx ou au-delà de '
      + '100 000 lx) a été coupée.')
  }
  if (cr.approche) {
    phrases.push(`La pièce sombre est plafonnée à ${formaterLux(options.lux_min)} : la courbe `
      + 'n\'approche votre réglage qu\'à quelques points près.')
  }
  if (cr.decalage) {
    phrases.push(`Un décalage de ${cr.decalage > 0 ? '+' : ''}${cr.decalage} est en place (réglé `
      + 'par une automatisation ou sur la page) : la courbe est calée sans lui, et lui ajoutée '
      + 'redonne votre réglage.')
  }
  if (cr.ancien_oublie) {
    phrases.push('Votre point précédent contredisait celui-ci (moins de lumière, luminosité plus '
      + 'haute) : seul le nouveau est retenu.')
  } else if (cr.remplace) {
    phrases.push('Votre point précédent, pris dans un éclairage voisin, est remplacé par '
      + 'celui-ci.')
  }
  return phrases.join(' ')
}

function EtapeAncrage({ index, details, reglages, options, ancrage, envoi, bloquee, onEcrire,
  onAncrer }) {
  const entree = index?.get(details.entree_id)
  const valeur = entree ? valeurDe(reglages, entree.api) : undefined
  const ancrages = ancrage?.options.ancrages ?? options.ancrages ?? []
  return (
    <div className="etape-mise-en-route">
      <p>
        <strong>Réglez maintenant la luminosité qui vous convient dans l'éclairage actuel</strong>,
        sur une image habituelle. Le curseur change la luminosité des pixels OLED tout de suite ;
        la télécommande convient aussi. La fonction n'intervient pas pendant ce réglage.
      </p>
      {bloquee ? (
        <p className="message message-conflit">
          Réglage impossible pour l'instant : revenez aux vérifications.
        </p>
      ) : (
        <>
          {details.decalage ? (
            <p className="texte-attenue">
              Décalage en place : {details.decalage > 0 ? '+' : ''}{details.decalage}. Il est
              déduit de votre réglage pour caler la courbe, puis s'y ajoute : vous retrouverez la
              luminosité choisie.
            </p>
          ) : null}
          <dl className="mesures-luminosite">
            <div>
              <dt>Lumière ambiante (lissée)</dt>
              <dd>{details.lux_filtre != null ? formaterLux(details.lux_filtre) : '—'}</dd>
            </div>
            <div>
              <dt>Luminosité du téléviseur</dt>
              <dd>{valeur ?? '—'}</dd>
            </div>
          </dl>
          {entree && (
            <label className="champ-luminosite champ-ancrage">
              <span>{entree.libelle}</span>
              <Curseur entree={entree} valeur={valeur} ecriture={!envoi}
                onEcrire={(v) => onEcrire(details.entree_id, v)} />
            </label>
          )}
          <p>
            <button type="button" className="bouton-principal" disabled={envoi || valeur == null}
              onClick={onAncrer}>
              {ancrage ? 'Retenir à nouveau ce réglage' : 'Retenir ce réglage'}
            </button>
          </p>
        </>
      )}
      {ancrage && (
        <div role="status">
          <p className="message">{texteCompteRendu(ancrage)}</p>
          <CourbeLuminosite options={ancrage.options} lux={details.lux_filtre}
            ancrages={ancrages} decalage={details.decalage ?? 0} />
          <p className="texte-attenue">
            Courbe : {pointsCourbe(ancrage.options)
              .map(([l, v]) => `${formaterLux(l)} → ${v}`).join(', ')}.
          </p>
        </div>
      )}
    </div>
  )
}
