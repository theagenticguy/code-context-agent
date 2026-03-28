import { createHashHistory, createRouter, RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { loadFromServer } from './lib/data-loader'
import { routeTree } from './routeTree.gen'
import { useStore } from './store/use-store'
import './tailwind.css'
import './theme.css'

const hashHistory = createHashHistory()
const router = createRouter({ routeTree, history: hashHistory })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

// Apply saved theme on load
const savedTheme = useStore.getState().theme
if (savedTheme === 'dark') {
  document.documentElement.classList.add('dark')
}

// Auto-load from server if served by the viz command
if (window.location.port) {
  loadFromServer(window.location.origin)
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
