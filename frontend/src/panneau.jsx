// Point d'entrée du panneau Home Assistant. Le panneau est enregistré avec
// embed_iframe : HA charge ce module dans une iframe, y crée l'élément
// <lg-webos-tv-panel> et lui transmet `hass` (puis à chaque changement d'état
// dans HA), `narrow` et `panel`. L'app est rendue une seule fois : seules les
// propriétés utiles (connexion websocket, thème, `narrow`) sont relayées
// ensuite.
import React from 'react'
import { createRoot } from 'react-dom/client'
import cssPolices from '@fontsource-variable/atkinson-hyperlegible-next/index.css?inline'
import cssApp from './App.css?inline'
import App from './App.jsx'
import { definirEtroit, definirHass } from './hass.js'

function injecterStyles() {
  // Dans l'iframe, le document est le nôtre : feuilles globales, @font-face
  // compris (impossible dans un shadow root).
  for (const css of [cssPolices, cssApp]) {
    const style = document.createElement('style')
    style.textContent = css
    document.head.appendChild(style)
  }
}

class PanneauLgWebosTv extends HTMLElement {
  set hass(hass) {
    definirHass(hass)
    // Le thème suit le choix fait dans le profil HA, pas seulement le système.
    const theme = hass.themes?.darkMode ? 'sombre' : 'clair'
    if (document.documentElement.dataset.theme !== theme) {
      document.documentElement.dataset.theme = theme
    }
  }

  set narrow(narrow) {
    definirEtroit(Boolean(narrow))
  }

  connectedCallback() {
    if (this.racine) return
    injecterStyles()
    this.racine = createRoot(this)
    this.racine.render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    )
  }

  disconnectedCallback() {
    this.racine?.unmount()
    this.racine = null
  }
}

if (!customElements.get('lg-webos-tv-panel')) {
  customElements.define('lg-webos-tv-panel', PanneauLgWebosTv)
}
