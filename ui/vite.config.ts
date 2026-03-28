import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'

export default defineConfig({
  plugins: [TanStackRouterVite(), react(), tailwindcss()],
  build: {
    outDir: '../src/code_context_agent/ui',
    emptyOutDir: true,
  },
  base: './',
  server: {
    proxy: {
      '/data': 'http://localhost:8765',
      '/api': 'http://localhost:8765',
    },
  },
})
