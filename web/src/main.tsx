import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Fonts come from npm, not a CDN, so the demo works offline.
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import './index.css'
import App from './App.tsx'

const root = createRoot(document.getElementById('root')!)

// /styleguide exists only in development; the production build drops this branch.
if (import.meta.env.DEV && window.location.pathname === '/styleguide') {
  import('./styleguide/StyleGuide.tsx').then(({ StyleGuide }) => {
    root.render(
      <StrictMode>
        <StyleGuide />
      </StrictMode>,
    )
  })
} else {
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}
