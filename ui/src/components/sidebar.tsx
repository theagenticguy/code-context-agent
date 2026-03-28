import { Link, useRouterState } from '@tanstack/react-router'
import { useStore } from '../store/use-store'

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', to: '/' as const, key: '1', icon: '\u25A6' },
  { id: 'graph', label: 'Graph', to: '/graph' as const, key: '2', icon: '\u2B21' },
  { id: 'modules', label: 'Modules', to: '/modules' as const, key: '3', icon: '\u29C9' },
  { id: 'hotspots', label: 'Hotspots', to: '/hotspots' as const, key: '4', icon: '\u25C9' },
  { id: 'dependencies', label: 'Dependencies', to: '/dependencies' as const, key: '5', icon: '\u21C4' },
  { id: 'narrative', label: 'Narrative', to: '/narrative' as const, key: '6', icon: '\u2263' },
  { id: 'bundles', label: 'Bundles', to: '/bundles' as const, key: '7', icon: '\u2750' },
  { id: 'insights', label: 'Insights', to: '/insights' as const, key: '8', icon: '\u2605' },
  { id: 'signatures', label: 'Signatures', to: '/signatures' as const, key: '9', icon: '\u270E' },
] as const

/** Check if a view has data available in the store. */
function useViewHasData(id: string): boolean {
  const graph = useStore((s) => s.graph)
  const narrative = useStore((s) => s.narrative)
  const bundle = useStore((s) => s.bundle)
  const signatures = useStore((s) => s.signatures)
  const analysisResult = useStore((s) => s.analysisResult)

  switch (id) {
    case 'dashboard':
      return true
    case 'graph':
    case 'modules':
    case 'hotspots':
    case 'dependencies':
      return !!graph
    case 'narrative':
      return !!narrative
    case 'bundles':
      return !!bundle
    case 'insights':
      return !!analysisResult
    case 'signatures':
      return !!signatures
    default:
      return false
  }
}

function NavItem({ item }: { item: (typeof NAV_ITEMS)[number] }) {
  const hasData = useViewHasData(item.id)
  const location = useRouterState({ select: (s) => s.location })
  const isActive = location.pathname === item.to || (item.to === '/' && location.pathname === '')

  return (
    <Link
      to={item.to}
      className={`flex items-center gap-2.5 px-2.5 py-1.5 rounded-base text-sm font-base transition-all ${
        isActive
          ? 'bg-main text-main-fg border-2 border-border shadow-neo'
          : 'border-2 border-transparent hover:bg-main/20'
      } ${!hasData && item.id !== 'dashboard' ? 'opacity-40' : ''}`}
    >
      <span className="w-5 text-center text-base leading-none">{item.icon}</span>
      <span className="flex-1 truncate-line">{item.label}</span>
      <kbd
        className={`text-[10px] min-w-[18px] h-[18px] inline-flex items-center justify-center px-1 rounded border font-mono leading-none ${
          isActive ? 'border-main-fg/40 bg-main-fg/10' : 'border-border/40 bg-bg/50'
        }`}
      >
        {item.key}
      </kbd>
    </Link>
  )
}

export function Sidebar() {
  const theme = useStore((s) => s.theme)
  const toggleTheme = useStore((s) => s.toggleTheme)

  return (
    <aside className="w-56 border-r-2 border-border bg-bg2 flex flex-col h-full">
      <div className="p-4 border-b-2 border-border">
        <h1 className="font-heading text-lg tracking-tight">Code Context Visualizer</h1>
      </div>
      <nav className="flex-1 p-2 space-y-1 overflow-auto" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => (
          <NavItem key={item.id} item={item} />
        ))}
      </nav>
      <div className="p-3 border-t-2 border-border">
        <button
          type="button"
          onClick={() => {
            document.documentElement.classList.add('transitioning-theme')
            toggleTheme()
            setTimeout(() => document.documentElement.classList.remove('transitioning-theme'), 350)
          }}
          className="w-full flex items-center justify-center gap-2 px-3 py-1.5 text-xs rounded-base border-2 border-border font-base neo-pressable bg-bg2 hover:bg-main/20 transition-colors"
        >
          <span>{theme === 'dark' ? '\u263E' : '\u2600'}</span>
          <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          <kbd className="ml-auto text-[10px] px-1 py-0.5 rounded border border-border/40 bg-bg/50 font-mono leading-none">
            D
          </kbd>
        </button>
      </div>
    </aside>
  )
}
