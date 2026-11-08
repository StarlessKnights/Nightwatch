import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backendPort = process.env.BACKEND_PORT || '8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': `http://localhost:${backendPort}`,
      '/ws': { target: `ws://localhost:${backendPort}`, ws: true },
    },
  },
})
