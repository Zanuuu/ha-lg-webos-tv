import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Construit le panneau Home Assistant dans le dossier de l'intégration :
// un module d'entrée au nom fixe (panneau.js, référencé par panneau.py) et
// ses ressources (polices) servies sous le chemin statique du panneau.
export default defineConfig({
  base: '/lg_webos_tv_panneau/',
  plugins: [react()],
  build: {
    outDir: '../custom_components/lg_webos_tv/frontend',
    emptyOutDir: true,
    rollupOptions: {
      input: 'src/panneau.jsx',
      output: {
        entryFileNames: 'panneau.js',
        chunkFileNames: '[name]-[hash].js',
        assetFileNames: '[name]-[hash][extname]',
      },
    },
  },
})
