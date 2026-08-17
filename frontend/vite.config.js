import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // En dev, le backend FastAPI tourne à part : on lui relaie les appels API.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
