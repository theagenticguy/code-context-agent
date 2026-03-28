interface StatCardProps {
  title: string
  value: string | number
  color?: string
}

export function StatCard({ title, value, color }: StatCardProps) {
  return (
    <div className="rounded-base border-2 border-border shadow-neo bg-bg2 p-3">
      <p className="text-[11px] font-heading uppercase tracking-wide text-fg/50">{title}</p>
      <p className="text-xl font-heading mt-1" style={color ? { color } : undefined}>
        {value}
      </p>
    </div>
  )
}
