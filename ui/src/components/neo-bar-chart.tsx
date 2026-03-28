import { Link } from '@tanstack/react-router'
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useStore } from '../store/use-store'

interface BarChartItem {
  label: string
  value: number
  color?: string
}

interface NeoBarChartProps {
  data: BarChartItem[]
  maxBars?: number
  linkTo?: string
  height?: number
}

export function NeoBarChart({ data, maxBars = 10, linkTo, height = 300 }: NeoBarChartProps) {
  const setPendingSearch = useStore((s) => s.setPendingSearch)
  const sliced = data.slice(0, maxBars)

  if (sliced.length === 0) {
    return <p className="text-xs text-fg/40 py-4 text-center">No data</p>
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={sliced} layout="vertical" margin={{ left: 0, right: 16, top: 0, bottom: 0 }}>
          <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--foreground)' }} />
          <YAxis
            type="category"
            dataKey="label"
            width={140}
            tick={{ fontSize: 11, fill: 'var(--foreground)' }}
            tickFormatter={(v: string) => (v.length > 22 ? `${v.slice(0, 20)}…` : v)}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--secondary-background)',
              border: '2px solid var(--border)',
              borderRadius: '5px',
              boxShadow: '2px 2px 0 var(--border)',
              fontSize: '12px',
            }}
          />
          <Bar dataKey="value" radius={[0, 3, 3, 0]} stroke="var(--border)" strokeWidth={2}>
            {sliced.map((item, i) => (
              <Cell key={i} fill={item.color ?? 'var(--chart-1)'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {linkTo && (
        <div className="mt-2 flex flex-wrap gap-1">
          {sliced.map((item) => (
            <Link
              key={item.label}
              to={linkTo}
              search={{ q: item.label }}
              className="text-[10px] text-fg/50 hover:text-main hover:underline cursor-pointer"
              onClick={() => {
                // Set pending search for cross-view navigation
                setPendingSearch(item.label)
              }}
            >
              {item.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
