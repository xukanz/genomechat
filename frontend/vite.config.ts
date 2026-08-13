import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// The demo is published to GitHub Pages, which serves from a repo subpath.
// Both are opt-in via env vars so a normal `npm run build` is unaffected:
//   BUILD_TARGET=demo   → build only demo.html (no app bundle on Pages)
//   PUBLIC_BASE_PATH=…  → asset base, e.g. "/genomechat/"
const demoOnly = process.env.BUILD_TARGET === 'demo'
const base = process.env.PUBLIC_BASE_PATH || '/'

const appEntry = { main: path.resolve(__dirname, 'index.html') }
const demoEntry = { demo: path.resolve(__dirname, 'demo.html') }

// https://vitejs.dev/config/
export default defineConfig({
  base,
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      // The app itself, plus a standalone walkthrough (landing → login → chat)
      // served against a mocked backend — a separate entry so it never touches
      // the app's routing.
      input: demoOnly ? demoEntry : { ...appEntry, ...demoEntry },
    },
  },
  server: {
    port: 5173,
    host: true,
  },
})
