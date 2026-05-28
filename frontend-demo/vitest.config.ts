/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

// Separate Vitest config avoids the Vite 8 / vitest-bundled-Vite type conflict
// that occurs when a combined vite.config.ts uses defineConfig from 'vitest/config'.
// The build (npm run build) uses vite.config.ts; tests (npm run test:run) use this.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    css: false,
  },
})
