import { Link } from '@tanstack/react-router'

interface EmptyStateProps {
  icon?: string
  title: string
  description?: string
  actionLabel?: string
  actionTo?: string
}

export function EmptyState({ icon, title, description, actionLabel, actionTo }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-fg/50">
      {icon && <span className="text-4xl mb-3">{icon}</span>}
      <p className="text-xl font-heading">{title}</p>
      {description && <p className="text-sm mt-2 text-center max-w-md">{description}</p>}
      {actionLabel && actionTo && (
        <Link
          to={actionTo}
          className="mt-4 px-4 py-2 bg-main text-main-fg rounded-base border-2 border-border shadow-neo neo-pressable font-base text-sm"
        >
          {actionLabel}
        </Link>
      )}
    </div>
  )
}
