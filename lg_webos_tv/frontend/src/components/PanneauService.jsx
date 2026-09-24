import { useState } from 'react'
import VueHistorique from './VueHistorique.jsx'
import VuePresets from './VuePresets.jsx'

export default function PanneauService({ index, lectureSeule }) {
  const [onglet, setOnglet] = useState('presets')

  return (
    <section className="panneau-service">
      <div className="onglets-service">
        <button
          type="button"
          className={onglet === 'presets' ? 'onglet-actif' : ''}
          onClick={() => setOnglet('presets')}
        >
          Presets
        </button>
        <button
          type="button"
          className={onglet === 'historique' ? 'onglet-actif' : ''}
          onClick={() => setOnglet('historique')}
        >
          Historique
        </button>
      </div>
      {onglet === 'presets'
        ? <VuePresets lectureSeule={lectureSeule} />
        : <VueHistorique index={index} lectureSeule={lectureSeule} />}
    </section>
  )
}
