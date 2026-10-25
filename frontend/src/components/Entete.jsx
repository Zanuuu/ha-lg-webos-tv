import { libelleChoix } from '../arbre.js'

const LIBELLES_CONNEXION = {
  connecte: 'Connecté',
  deconnecte: 'Déconnecté',
  connexion: 'Connexion…',
  appairage_requis: 'Appairage requis',
}

export default function Entete({ connexion, modeImage, entreeModeImage, etroit }) {
  const libelleMode = entreeModeImage && modeImage
    ? libelleChoix(entreeModeImage, modeImage) || modeImage
    : null

  // HA replie sa barre latérale sur mobile et laisse au panneau le bouton qui
  // la rouvre ; dans l'iframe, l'événement est relayé à HA par son point
  // d'entrée des panneaux personnalisés.
  function basculerMenuHa(e) {
    e.currentTarget.dispatchEvent(
      new CustomEvent('hass-toggle-menu', { bubbles: true, composed: true }),
    )
  }

  return (
    <header className="entete">
      <div className="entete-titre">
        {etroit && (
          <button
            type="button"
            className="bouton-menu-ha"
            aria-label="Menu de Home Assistant"
            onClick={basculerMenuHa}
          >
            <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
              <path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z" fill="currentColor" />
            </svg>
          </button>
        )}
        <h1>Réglages</h1>
      </div>
      <div className="indicateurs">
        {libelleMode && <span className="mode-image">Mode d'image : {libelleMode}</span>}
        {connexion && (
          <span className={`indicateur-connexion indicateur-${connexion}`}>
            <span className="puce" />
            {LIBELLES_CONNEXION[connexion] || connexion}
          </span>
        )}
      </div>
    </header>
  )
}
