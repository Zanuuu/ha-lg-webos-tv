import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { indexerParId } from './arbre.js'
import BarreLaterale from './components/BarreLaterale.jsx'
import Entete from './components/Entete.jsx'
import PanneauMenu from './components/PanneauMenu.jsx'
import VueHistorique from './components/VueHistorique.jsx'
import VuePresets from './components/VuePresets.jsx'
import { abonnerEtroit, estEtroit } from './hass.js'
import { useEtatTv } from './hooks/useEtatTv.js'

export default function App() {
  const {
    arbre, erreurArbre, rechargerArbre, reglages, connexion, modeImage, ecriturePossible,
    revisions, ecrire,
  } = useEtatTv()
  const etroit = useSyncExternalStore(abonnerEtroit, estEtroit)
  // Vue de la barre latérale : 'menu' (arbre des réglages), 'presets' ou 'historique'.
  const [vue, setVue] = useState('menu')
  const [chemin, setChemin] = useState([])
  const titreRef = useRef(null)
  // Posé par une navigation dans le menu : le titre du nouveau nœud reçoit le
  // focus (clavier, lecteur d'écran). Un clic dans la barre latérale le
  // laisse sur la barre.
  const focaliserTitre = useRef(false)

  const index = useMemo(() => (arbre ? indexerParId(arbre) : null), [arbre])

  const sections = arbre?.sections || []
  const cheminEffectif = chemin.length > 0 ? chemin : sections.slice(0, 1)

  // Échap remonte d'un niveau, comme la touche Retour de la télécommande.
  useEffect(() => {
    function surTouche(e) {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      if (document.querySelector('dialog[open]')) return
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return
      if (vue !== 'menu' || chemin.length < 2) return
      focaliserTitre.current = true
      setChemin((c) => c.slice(0, -1))
    }
    document.addEventListener('keydown', surTouche)
    return () => document.removeEventListener('keydown', surTouche)
  }, [vue, chemin.length])

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
    setVue('menu')
    setChemin([section])
  }

  function entrer(entree) {
    focaliserTitre.current = true
    setChemin((c) => [...(c.length > 0 ? c : sections.slice(0, 1)), entree])
  }

  function revenir(profondeur) {
    focaliserTitre.current = true
    setChemin((c) => c.slice(0, profondeur + 1))
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
        <BarreLaterale
          sections={sections}
          vue={vue}
          sectionActiveId={cheminEffectif[0]?.id}
          onChoisirSection={choisirSection}
          onChoisirVue={setVue}
        />
        {vue === 'menu' && (
          <PanneauMenu
            chemin={cheminEffectif}
            reglages={reglages}
            lectureSeule={lectureSeule}
            horsLigne={horsLigne}
            titreRef={titreRef}
            onEcrire={ecrire}
            onEntrer={entrer}
            onRevenir={revenir}
          />
        )}
        {vue === 'presets' && (
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
        {vue === 'historique' && (
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
