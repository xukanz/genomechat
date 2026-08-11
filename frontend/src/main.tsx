import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import logoMark from './assets/logo_circle.svg'

const favicon = document.getElementById('app-favicon') as HTMLLinkElement | null
if (favicon) {
  // SVG favicon: no `sizes`, since it is resolution-independent.
  favicon.type = 'image/svg+xml'
  favicon.href = logoMark
  favicon.removeAttribute('sizes')
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

