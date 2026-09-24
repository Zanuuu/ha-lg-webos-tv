import { libelleChoix } from '../arbre.js'

const LIBELLES_CONNEXION = {
  connecte: 'Connecté',
  deconnecte: 'Déconnecté',
  connexion: 'Connexion…',
  appairage: 'Appairage : acceptez la demande sur la TV',
}

export default function Entete({ connexion, modeImage, entreeModeImage, vue, onChangerVue }) {
  const libelleMode = entreeModeImage && modeImage
    ? libelleChoix(entreeModeImage, modeImage) || modeImage
    : null

  return (
    <header className="entete">
      <h1>Réglages</h1>
      <div className="indicateurs">
        {libelleMode && <span className="mode-image">Mode d'image : {libelleMode}</span>}
        <span className={`indicateur-connexion indicateur-${connexion}`}>
          <span className="puce" />
          {LIBELLES_CONNEXION[connexion] || connexion}
        </span>
        <button
          type="button"
          className="bouton-vue-service"
          onClick={() => onChangerVue(vue === 'service' ? 'reglages' : 'service')}
        >
          {vue === 'service' ? '← Réglages' : 'Presets & historique'}
        </button>
      </div>
    </header>
  )
}
