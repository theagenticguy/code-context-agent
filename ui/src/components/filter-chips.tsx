interface FilterChip {
  type: string
  label: string
  color: string
  active: boolean
}

interface FilterChipsProps {
  chips: FilterChip[]
  onToggle: (type: string) => void
  title?: string
}

export function FilterChips({ chips, onToggle, title }: FilterChipsProps) {
  return (
    <div>
      {title && <span className="text-[10px] font-heading uppercase tracking-wide text-fg/40 mr-2">{title}</span>}
      <div className="flex flex-wrap gap-1.5 mt-1">
        {chips.map((chip) => (
          <button
            type="button"
            key={chip.type}
            onClick={() => onToggle(chip.type)}
            className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-base border transition-all cursor-pointer ${
              chip.active
                ? 'border-border bg-bg2 text-fg shadow-[2px_2px_0_var(--border)]'
                : 'border-border/30 bg-bg/50 text-fg/40 line-through'
            }`}
            aria-pressed={chip.active}
          >
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: chip.color }} />
            {chip.label}
          </button>
        ))}
      </div>
    </div>
  )
}
