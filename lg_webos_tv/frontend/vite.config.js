import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // Chemins relatifs : sous Ingress Home Assistant, l'app est servie derrière
  // un préfixe d'URL dynamique inconnu au moment du build.
  base: './',
  plugins: [react()],
  server: {
    // En dev, le backend FastAPI tourne à part : on lui relaie les appels API.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
})
