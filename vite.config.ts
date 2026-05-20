/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/build/**',
      '**/downloads/**',
      '**/release/**',
      '**/state/**',
      '**/switchboard/static/**',
      '**/switchboard/manager/**',
    ],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8009',
        changeOrigin: true,
      },
    },
  },
})
