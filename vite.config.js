import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const MOTEUR = process.env.SHYCLONE_ENGINE ?? 'http://127.0.0.1:5000'

// Le client appelle /api et /preview en relatif : c'est ce proxy qui pointe
// vers Flask, plutôt qu'une URL localhost codée en dur dans le bundle.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': { target: MOTEUR, changeOrigin: true },
      '/preview': { target: MOTEUR, changeOrigin: true },
    },
  },
})
