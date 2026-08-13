/**
 * Entry point for the demo build (`demo.html`).
 *
 * Mirrors the real `src/main.tsx`, but installs the fake backend before
 * rendering and starts every visitor logged out at the landing page, so a
 * previous session (real or demo) can't leak into the walkthrough.
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import { DemoApp } from './DemoApp'
import { installDemoBackend } from './mockBackend'
import { useAuthStore } from '../store/authStore'
import '../index.css'
import logoMark from '../assets/logo_circle.svg'

const favicon = document.getElementById('app-favicon') as HTMLLinkElement | null
if (favicon) {
  // SVG favicon: no `sizes`, since it is resolution-independent.
  favicon.type = 'image/svg+xml'
  favicon.href = logoMark
  favicon.removeAttribute('sizes')
}

installDemoBackend()

// authStore persists to localStorage, which this bundle shares with the real
// app's origin. Clear it so the demo always opens on the landing page.
useAuthStore.setState({
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,
  error: null,
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <DemoApp />
  </React.StrictMode>,
)
