import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'

// Extension-specific initialization
console.log('🚀 ORII React Extension: Initializing...')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

console.log('✅ ORII React Extension: Initialized successfully')
