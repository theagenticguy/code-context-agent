import { severityColor } from '../constants/colors'

interface SeverityBadgeProps {
  severity: string
}

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  const color = severityColor(severity)
  return (
    <span
      className="inline-flex items-center text-xs font-heading px-2 py-0.5 rounded-base border-2 border-border"
      style={{
        background: `color-mix(in srgb, ${color} 20%, transparent)`,
        color,
      }}
    >
      {severity}
    </span>
  )
}
