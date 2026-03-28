import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

interface TooltipState {
  html: string
  x: number
  y: number
  visible: boolean
}

interface TooltipContextValue {
  show: (html: string, x: number, y: number) => void
  hide: () => void
  move: (x: number, y: number) => void
}

const TooltipContext = createContext<TooltipContextValue>({
  show: () => {},
  hide: () => {},
  move: () => {},
})

export function useTooltip() {
  return useContext(TooltipContext)
}

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<TooltipState>({ html: '', x: 0, y: 0, visible: false })
  const ref = useRef<HTMLDivElement>(null)

  const position = useCallback((x: number, y: number) => {
    if (!ref.current) return { left: x + 12, top: y - 8 }
    const rect = ref.current.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight
    const pad = 8
    let left = x + 12
    let top = y - rect.height - pad
    if (left + rect.width > vw - pad) left = x - rect.width - 12
    if (top < pad) top = y + 12
    left = Math.max(pad, Math.min(left, vw - rect.width - pad))
    top = Math.max(pad, Math.min(top, vh - rect.height - pad))
    return { left, top }
  }, [])

  const show = useCallback((html: string, x: number, y: number) => {
    setState({ html, x, y, visible: true })
  }, [])

  const hide = useCallback(() => {
    setState((s) => ({ ...s, visible: false }))
  }, [])

  const move = useCallback((x: number, y: number) => {
    setState((s) => ({ ...s, x, y }))
  }, [])

  const pos = position(state.x, state.y)

  return (
    <TooltipContext.Provider value={{ show, hide, move }}>
      {children}
      {createPortal(
        <div
          ref={ref}
          className={`tooltip ${state.visible ? 'visible' : ''}`}
          style={{ left: pos.left, top: pos.top }}
          dangerouslySetInnerHTML={{ __html: state.html }}
        />,
        document.body,
      )}
    </TooltipContext.Provider>
  )
}
