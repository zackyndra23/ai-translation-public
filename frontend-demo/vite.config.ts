import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    open: false, // launcher controls Chrome
    proxy: {
      // Forward /api/* to backend FastAPI on :8000. Avoids CORS in dev and
      // matches the production-style relative-path routing the frontend uses.
      // Per ADR-063: Vite proxy is the dev path; reverse proxy handles prod.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
