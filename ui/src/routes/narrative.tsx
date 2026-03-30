import { createFileRoute } from '@tanstack/react-router'
import { marked } from 'marked'
import { useEffect, useMemo, useRef } from 'react'
import { EmptyState } from '../components/empty-state'
import { initMermaid, renderMermaidBlocks } from '../lib/mermaid-init'
import { useStore } from '../store/use-store'

export const Route = createFileRoute('/narrative')({
  component: NarrativeView,
})

interface TocEntry {
  id: string
  text: string
  level: number
}

function buildToc(markdown: string): TocEntry[] {
  const entries: TocEntry[] = []
  const headingRe = /^(#{2,3})\s+(.+)$/gm
  let match: RegExpExecArray | null
  while ((match = headingRe.exec(markdown)) !== null) {
    const level = match[1].length
    const text = match[2].trim()
    const id = text
      .toLowerCase()
      .replace(/[^\w\s-]/g, '')
      .replace(/\s+/g, '-')
    entries.push({ id, text, level })
  }
  return entries
}

function configureMarked() {
  const renderer = new marked.Renderer()
  renderer.heading = (args) => {
    const text = args.text
    const id = text
      .toLowerCase()
      .replace(/<[^>]*>/g, '')
      .replace(/[^\w\s-]/g, '')
      .replace(/\s+/g, '-')
    return `<h${args.depth} id="${id}">${text}</h${args.depth}>`
  }
  renderer.code = ({ text, lang }) => {
    if (lang === 'mermaid') {
      return `<pre><code class="language-mermaid">${text}</code></pre>`
    }
    return `<pre><code class="language-${lang || ''}">${text}</code></pre>`
  }
  marked.setOptions({ renderer })
}

configureMarked()

function NarrativeView() {
  const narrative = useStore((s) => s.narrative)
  const theme = useStore((s) => s.theme)
  const contentRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const toc = useMemo(() => (narrative ? buildToc(narrative) : []), [narrative])
  const html = useMemo(() => (narrative ? (marked.parse(narrative) as string) : ''), [narrative])

  useEffect(() => {
    if (contentRef.current && html) {
      initMermaid(theme)
      renderMermaidBlocks(contentRef.current)
    }
  }, [html, theme])

  if (!narrative) {
    return (
      <div className="flex items-center justify-center h-full view-enter">
        <EmptyState
          icon={'\u2263'}
          title="No narrative loaded"
          description="Load a CONTEXT.md file from the Dashboard to view the analysis narrative."
          actionLabel="Go to Dashboard"
          actionTo="/"
        />
      </div>
    )
  }

  return (
    <div className="flex h-full view-enter">
      {/* TOC sidebar */}
      <aside className="hidden lg:block w-64 shrink-0 border-r-2 border-border bg-bg2 overflow-auto p-4">
        <h2 className="font-heading text-sm uppercase tracking-wide text-fg/50 mb-3">Contents</h2>
        <nav className="space-y-1">
          {toc.map((entry) => (
            <button
              type="button"
              key={entry.id}
              onClick={() => {
                const el = document.getElementById(entry.id)
                const container = scrollContainerRef.current
                if (el && container) {
                  const offset =
                    container.scrollTop + el.getBoundingClientRect().top - container.getBoundingClientRect().top - 20
                  container.scrollTo({ top: offset, behavior: 'smooth' })
                }
              }}
              className={`block text-left text-sm font-base truncate-line hover:text-main transition-colors ${
                entry.level === 3 ? 'pl-4 text-fg/60' : 'text-fg/80'
              }`}
            >
              {entry.text}
            </button>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <div ref={scrollContainerRef} className="flex-1 overflow-auto p-6 lg:p-10">
        <div ref={contentRef} className="prose max-w-none font-base" dangerouslySetInnerHTML={{ __html: html }} />
      </div>
    </div>
  )
}
