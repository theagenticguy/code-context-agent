import { createRootRoute, Outlet } from '@tanstack/react-router'
import { useEffect } from 'react'
import { Sidebar } from '../components/sidebar'
import { TooltipProvider } from '../components/tooltip'
import { useStore } from '../store/use-store'

function RootLayout() {
  const toggleTheme = useStore((s) => s.toggleTheme)

  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      // 'd' toggles dark mode
      if (e.key === 'd' && !e.ctrlKey && !e.metaKey) {
        document.documentElement.classList.add('transitioning-theme')
        toggleTheme()
        setTimeout(() => document.documentElement.classList.remove('transitioning-theme'), 350)
      }
    }

    document.addEventListener('keydown', handleKeydown)
    return () => document.removeEventListener('keydown', handleKeydown)
  }, [toggleTheme])

  return (
    <TooltipProvider>
      <div className="flex h-screen bg-bg text-fg font-base">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </TooltipProvider>
  )
}

export const Route = createRootRoute({
  component: RootLayout,
})
