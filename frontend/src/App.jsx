import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { indexerParId } from './arbre.js'
import BarreLaterale from './components/BarreLaterale.jsx'
import Entete from './components/Entete.jsx'
import PanneauMenu from './components/PanneauMenu.jsx'
import Recherche from './components/Recherche.jsx'
import VueHistorique from './components/VueHistorique.jsx'
import VuePresets from './components/VuePresets.jsx'
import VueRecherche from './components/VueRecherche.jsx'
import { abonnerEtroit, estEtroit } from './hass.js'
import { useEtatTv } from './hooks/useEtatTv.js'
import { aplatir } from './recherche.js'

export default function App() {
  const {
    arbre, erreurArbre, rechargerArbre, reglages, connexion, modeImage, ecriturePossible,
    revisions, ecrire, luminosite, reprendre,
  } = useEtatTv()
  const etroit = useSyncExternalStore(abonnerEtroit, estEtroit)
  // Vue de la barre latérale : 'menu' (arbre des réglages), 'presets' ou 'historique'.
  const [vue, setVue] = useState('menu')
  const [chemin, setChemin] = useState([])
  // Non vide : la vue de recherche remplace la vue choisie, retrouvée quand
  // le champ est vidé.
  const [requete, setRequete] = useState('')
  // Réglage ouvert depuis la recherche, mis en évidence dans le menu.
  const [entreeRevelee, setEntreeRevelee] = useState(null)
  const titreRef = useRef(null)
  const champRechercheRef = useRef(null)
  // Posé par une navigation dans le menu : le titre du nouveau nœud reçoit le
  // focus (clavier, lecteur d'écran). Un clic dans la barre latérale le
  // laisse sur la barre.
  const focaliserTitre = useRef(false)

  const index = useMemo(() => (arbre ? indexerParId(arbre) : null), [arbre])
  const entreesRecherche = useMemo(() => (arbre ? aplatir(arbre) : []), [arbre])
  const enRecherche = requete.trim() !== ''

  const sections = arbre?.sections || []
  const cheminEffectif = chemin.length > 0 ? chemin : sections.slice(0, 1)

  // Échap remonte d'un niveau, comme la touche Retour de la télécommande, ou
  // quitte la recherche ; « / » place le curseur dans la recherche.
  useEffect(() => {
    function surTouche(e) {
      if (e.defaultPrevented || !['Escape', '/'].includes(e.key)) return
      if (document.querySelector('dialog[open]')) return
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return
      if (e.key === '/') {
        e.preventDefault()
        champRechercheRef.current?.focus()
      } else if (enRecherche) {
        setRequete('')
      } else if (vue === 'menu' && chemin.length >= 2) {
        focaliserTitre.current = true
        setEntreeRevelee(null)
        setChemin((c) => c.slice(0, -1))
      }
    }
    document.addEventListener('keydown', surTouche)
    return () => document.removeEventListener('keydown', surTouche)
  }, [vue, chemin.length, enRecherche])

  useEffect(() => {
    if (focaliserTitre.current) {
      focaliserTitre.current = false
      titreRef.current?.focus()
    }
  }, [chemin])

  if (!arbre) {
    return (
      <div className="app">
        <Entete connexion={connexion} etroit={etroit} />
        <div className="etat-panneau" role={erreurArbre ? 'alert' : 'status'}>
          {erreurArbre ? (
            <>
              <p>Impossible de charger le menu des réglages : {erreurArbre}</p>
              <button type="button" className="bouton-principal" onClick={rechargerArbre}>
                Réessayer
              </button>
            </>
          ) : (
            <p className="texte-attenue">Chargement du menu…</p>
          )}
        </div>
      </div>
    )
  }

  const horsLigne = connexion !== null && connexion !== 'connecte'
  const consultation = ecriturePossible === false
  const lectureSeule = horsLigne || consultation

  function choisirSection(section) {
    setRequete('')
    setEntreeRevelee(null)
    setVue('menu')
    setChemin([section])
  }

  function choisirVue(id) {
    setRequete('')
    setVue(id)
  }

  function entrer(entree) {
    focaliserTitre.current = true
    setEntreeRevelee(null)
    setChemin((c) => [...(c.length > 0 ? c : sections.slice(0, 1)), entree])
  }

  function revenir(profondeur) {
    focaliserTitre.current = true
    setEntreeRevelee(null)
    setChemin((c) => c.slice(0, profondeur + 1))
  }

  // Depuis un résultat : le menu s'ouvre sur le nœud qui contient le réglage
  // (qui reçoit le focus), ou sur le sous-menu choisi (son titre le reçoit).
  function ouvrirDepuisRecherche(nouveauChemin, entreeId = null) {
    focaliserTitre.current = entreeId === null
    setEntreeRevelee(entreeId)
    setRequete('')
    setVue('menu')
    setChemin(nouveauChemin)
  }

  return (
    <div className="app">
      <Entete
        connexion={connexion}
        modeImage={modeImage}
        entreeModeImage={index.get('image.mode-selection')}
        etroit={etroit}
      />
      <Bandeau connexion={connexion} horsLigne={horsLigne} consultation={consultation} />
      <div className="corps">
        <div className="colonne-nav">
          <Recherche requete={requete} champRef={champRechercheRef} onChanger={setRequete} />
          <BarreLaterale
            sections={sections}
            vue={enRecherche ? 'recherche' : vue}
            sectionActiveId={cheminEffectif[0]?.id}
            onChoisirSection={choisirSection}
            onChoisirVue={choisirVue}
          />
        </div>
        {enRecherche && (
          <VueRecherche
            entrees={entreesRecherche}
            requete={requete}
            reglages={reglages}
            lectureSeule={lectureSeule}
            horsLigne={horsLigne}
            luminosite={luminosite}
            onEcrire={ecrire}
            onReprendre={reprendre}
            onOuvrir={ouvrirDepuisRecherche}
          />
        )}
        {!enRecherche && vue === 'menu' && (
          <PanneauMenu
            chemin={cheminEffectif}
            reglages={reglages}
            lectureSeule={lectureSeule}
            horsLigne={horsLigne}
            luminosite={luminosite}
            entreeRevelee={entreeRevelee}
            titreRef={titreRef}
            onEcrire={ecrire}
            onReprendre={reprendre}
            onEntrer={entrer}
            onRevenir={revenir}
          />
        )}
        {!enRecherche && vue === 'presets' && (
          <section className="panneau-service" aria-labelledby="titre-presets">
            <h2 id="titre-presets" className="titre-noeud">Presets</h2>
            <VuePresets
              index={index}
              reglages={reglages}
              modeImage={modeImage}
              lectureSeule={lectureSeule}
              revision={revisions.presets}
            />
          </section>
        )}
        {!enRecherche && vue === 'historique' && (
          <section className="panneau-service" aria-labelledby="titre-historique">
            <h2 id="titre-historique" className="titre-noeud">Historique</h2>
            <VueHistorique
              index={index}
              lectureSeule={lectureSeule}
              revision={revisions.historique}
            />
          </section>
        )}
      </div>
    </div>
  )
}

function Bandeau({ connexion, horsLigne, consultation }) {
  let texte = null
  if (connexion === 'appairage_requis') {
    texte = 'Le téléviseur a refusé la clé d\'appairage : relancez l\'appairage depuis '
      + 'Paramètres › Appareils et services. Les valeurs affichées sont les dernières connues.'
  } else if (horsLigne) {
    // Même texte pendant les tentatives de reconnexion : la boucle alterne
    // « connexion » et « déconnecté » tant que la TV est éteinte.
    texte = 'Téléviseur éteint ou injoignable : les valeurs affichées sont les dernières '
      + 'connues, modifiables une fois la TV allumée.'
  } else if (consultation) {
    texte = 'Le téléviseur n\'autorise pas la modification des réglages : ils restent '
      + 'consultables ici, à régler sur la TV.'
  }
  if (!texte) return null
  return <p className="bandeau-consultation" role="status">{texte}</p>
}
