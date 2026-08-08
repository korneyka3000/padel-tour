import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // The API runs separately in development; in production both are one deployment.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: { outDir: 'dist', sourcemap: true },
})
