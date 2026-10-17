/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    // jsdom gives tests a browser-like DOM without starting a real browser.
    environment: 'jsdom',
    // Vitest blanks CSS imports by default; the contrast test needs the real tokens.
    css: { include: [/src\/index\.css/] },
  },
})
