import { useMemo, useState } from 'react'
import './App.css'
import { indexerParId } from './arbre.js'
import BarreLaterale from './components/BarreLaterale.jsx'
import Entete from './components/Entete.jsx'
import PanneauMenu from './components/PanneauMenu.jsx'
import PanneauService from './components/PanneauService.jsx'
import { useEtatTv } from './hooks/useEtatTv.js'

export default function App() {
  const { arbre, reglages, connexion, modeImage, ecrire } = useEtatTv()
  const [chemin, setChemin] = useState([])
  const [vue, setVue] = useState('reglages')

  const index = useMemo(() => (arbre ? indexerParId(arbre) : null), [arbre])

  if (!arbre) return null

  const sections = arbre.sections
  const cheminEffectif = chemin.length > 0 ? chemin : [sections[0]]
  const sectionActiveId = cheminEffectif[0].id

  function choisirSection(section) {
    setChemin([section])
  }

  function entrer(entree) {
    setChemin((c) => [...(c.length > 0 ? c : [sections[0]]), entree])
  }

  function revenir(profondeur) {
    setChemin((c) => c.slice(0, profondeur + 1))
  }

  return (
    <div className="app">
      <Entete
        connexion={connexion}
        modeImage={modeImage}
        entreeModeImage={index?.get('image.mode-selection')}
        vue={vue}
        onChangerVue={setVue}
      />
      <div className="corps">
        {vue === 'service' ? (
          <PanneauService index={index} />
        ) : (
          <>
            <BarreLaterale sections={sections} sectionActiveId={sectionActiveId} onChoisir={choisirSection} />
            <PanneauMenu
              chemin={cheminEffectif}
              reglages={reglages}
              onEcrire={ecrire}
              onEntrer={entrer}
              onRevenir={revenir}
            />
          </>
        )}
      </div>
    </div>
  )
}
