import { StrictMode, type ComponentType, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './app/App'

async function start() {
  let devTools: ReactNode = null
  // Dev-only break-ui fixtures, dropped from production builds. src/dev/ is
  // gitignored, so it's globbed rather than imported: builds without it work.
  if (import.meta.env.DEV) {
    const dev = import.meta.glob<{
      installWorstCase?: () => void
      DataToggle?: ComponentType
    }>('./dev/*.{ts,tsx}')
    const loadFixtures = dev['./dev/worst-case.ts']
    const loadToggle = dev['./dev/DataToggle.tsx']
    if (loadFixtures && loadToggle) {
      const [{ installWorstCase }, { DataToggle }] = await Promise.all([
        loadFixtures(),
        loadToggle(),
      ])
      installWorstCase?.()
      if (DataToggle) devTools = <DataToggle />
    }
  }

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
      {devTools}
    </StrictMode>,
  )
}

void start()
