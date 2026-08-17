import { libelleChoix } from '../arbre.js'

const LIBELLES_CONNEXION = {
  connecte: 'Connecté',
  deconnecte: 'Déconnecté',
  connexion: 'Connexion…',
}

export default function Entete({ connexion, modeImage, entreeModeImage }) {
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
      </div>
    </header>
  )
}
