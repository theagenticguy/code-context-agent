import { useCallback, useEffect, useRef, useState } from 'react'

interface SearchBarProps {
  placeholder?: string
  onSearch: (query: string) => void
  initialValue?: string
  debounceMs?: number
}

// Module-level ref to the currently active search input (for Cmd+K)
let activeSearchInput: HTMLInputElement | null = null

// Register global Cmd+K handler once
let cmdKRegistered = false
function ensureCmdK() {
  if (cmdKRegistered) return
  cmdKRegistered = true
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault()
      activeSearchInput?.focus()
      activeSearchInput?.select()
    }
  })
}

export function SearchBar({ placeholder = 'Search…', onSearch, initialValue = '', debounceMs = 250 }: SearchBarProps) {
  const [value, setValue] = useState(initialValue)
  const inputRef = useRef<HTMLInputElement>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Register this input as the active one for Cmd+K
  useEffect(() => {
    ensureCmdK()
    activeSearchInput = inputRef.current
    return () => {
      if (activeSearchInput === inputRef.current) {
        activeSearchInput = null
      }
    }
  }, [])

  // Update value when initialValue changes (e.g., from pendingSearch)
  useEffect(() => {
    if (initialValue) setValue(initialValue)
  }, [initialValue])

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const q = e.target.value
      setValue(q)
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => onSearch(q), debounceMs)
    },
    [onSearch, debounceMs],
  )

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        aria-label="Search"
        className="w-full px-3 py-1.5 text-sm rounded-base border-2 border-border bg-bg2 text-fg placeholder:text-fg/30 neo-focus font-base"
      />
      <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] px-1 py-0.5 rounded border border-border/40 bg-bg/50 font-mono leading-none text-fg/40">
        ⌘K
      </kbd>
    </div>
  )
}
