/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API (`uv run unapply api`) runs separately. Requests to /api go to it, so the
// browser sees one origin and the API needs no CORS. UNAPPLY_API_URL points
// elsewhere, as the end-to-end tests do.
const api = process.env.UNAPPLY_API_URL ?? 'http://127.0.0.1:8000'
const proxy = {
  '/api': {
    target: api,
    changeOrigin: true,
    rewrite: (p: string) => p.replace(/^\/api/, ''),
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: { proxy },
  preview: { proxy },
  // Component tests (`npm test`). The end-to-end tests in e2e/ run with Playwright.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
})
