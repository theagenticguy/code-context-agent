interface GaugeZone {
  from: number
  to: number
  color: string
}

interface GaugeProps {
  value: number
  max?: number
  label?: string
  zones?: GaugeZone[]
}

export function Gauge({ value, max = 100, label, zones }: GaugeProps) {
  const size = 120
  const stroke = 12
  const radius = (size - stroke) / 2
  const cx = size / 2
  const cy = size / 2

  const startAngle = -225
  const endAngle = 45
  const range = endAngle - startAngle
  const pct = Math.max(0, Math.min(1, value / max))
  const valueAngle = startAngle + pct * range

  function polarToXY(angle: number, r: number) {
    const rad = (angle * Math.PI) / 180
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
  }

  function arcPath(from: number, to: number, r: number) {
    const s = polarToXY(from, r)
    const e = polarToXY(to, r)
    const large = to - from > 180 ? 1 : 0
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`
  }

  const defaultZones: GaugeZone[] = zones ?? [
    { from: 0, to: 40, color: '#f87171' },
    { from: 40, to: 70, color: '#fbbf24' },
    { from: 70, to: 100, color: '#4ade80' },
  ]

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-28 h-28" aria-hidden="true">
      {/* Background arc */}
      <path
        d={arcPath(startAngle, endAngle, radius)}
        fill="none"
        stroke="var(--border)"
        strokeWidth={stroke}
        strokeLinecap="round"
        opacity={0.2}
      />
      {/* Zone arcs */}
      {defaultZones.map((zone, i) => {
        const zoneStart = startAngle + (zone.from / max) * range
        const zoneEnd = startAngle + (zone.to / max) * range
        return (
          <path
            key={i}
            d={arcPath(zoneStart, zoneEnd, radius)}
            fill="none"
            stroke={zone.color}
            strokeWidth={stroke}
            strokeLinecap="round"
            opacity={0.3}
          />
        )
      })}
      {/* Value arc */}
      {pct > 0 && (
        <path
          d={arcPath(startAngle, valueAngle, radius)}
          fill="none"
          stroke={defaultZones.find((z) => value >= z.from && value <= z.to)?.color ?? '#60a5fa'}
          strokeWidth={stroke}
          strokeLinecap="round"
        />
      )}
      {/* Center text */}
      <text x={cx} y={cy - 4} textAnchor="middle" fill="var(--foreground)" fontSize="22" fontWeight="700">
        {Math.round(value)}
      </text>
      {label && (
        <text x={cx} y={cy + 14} textAnchor="middle" fill="var(--foreground)" fontSize="9" opacity={0.6}>
          {label}
        </text>
      )}
    </svg>
  )
}
