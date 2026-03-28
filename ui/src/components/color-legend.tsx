import { useState } from 'react'
import { EDGE_COLORS, EDGE_TYPE_LABELS, NODE_COLORS, NODE_TYPE_LABELS } from '../constants/colors'

export function ColorLegend() {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-[10px] px-2 py-1 rounded-base border border-border/40 bg-bg2 text-fg/60 hover:text-fg cursor-pointer transition-colors"
        aria-expanded={open}
      >
        {open ? '✕ Legend' : '◑ Legend'}
      </button>
      {open && (
        <div className="absolute top-full mt-1 right-0 z-50 rounded-base border-2 border-border shadow-neo bg-bg2 p-3 min-w-[200px]">
          <p className="text-[10px] font-heading uppercase tracking-wide text-fg/40 mb-2">Node Types</p>
          <div className="space-y-1 mb-3">
            {Object.entries(NODE_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-2 text-xs">
                <span className="w-3 h-3 rounded-full border border-border/30 shrink-0" style={{ background: color }} />
                <span className="text-fg/70">{NODE_TYPE_LABELS[type] ?? type}</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] font-heading uppercase tracking-wide text-fg/40 mb-2">Edge Types</p>
          <div className="space-y-1">
            {Object.entries(EDGE_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-2 text-xs">
                <span className="w-3 h-0.5 shrink-0" style={{ background: color }} />
                <span className="text-fg/70">{EDGE_TYPE_LABELS[type] ?? type}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
