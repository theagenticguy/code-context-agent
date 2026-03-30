import { createFileRoute } from '@tanstack/react-router'
import { marked } from 'marked'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState } from '../components/empty-state'
import { initMermaid, renderMermaidBlocks } from '../lib/mermaid-init'
import { useStore } from '../store/use-store'

export const Route = createFileRoute('/bundles')({
  component: BundlesView,
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

/** Format a bundle area key for display: "auth-flows" → "Auth Flows" */
function formatAreaLabel(area: string): string {
  return area
    .split(/[-_]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function BundlesView() {
  const bundles = useStore((s) => s.bundles)
  const theme = useStore((s) => s.theme)
  const contentRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const areaKeys = useMemo(() => Object.keys(bundles).sort(), [bundles])
  const [activeArea, setActiveArea] = useState<string>('')

  // Keep activeArea in sync when bundles change
  useEffect(() => {
    if (areaKeys.length > 0 && !areaKeys.includes(activeArea)) {
      setActiveArea(areaKeys[0])
    }
  }, [areaKeys, activeArea])

  const content = activeArea ? (bundles[activeArea] ?? '') : ''
  const toc = useMemo(() => (content ? buildToc(content) : []), [content])
  const html = useMemo(() => (content ? (marked.parse(content) as string) : ''), [content])

  useEffect(() => {
    if (contentRef.current && html) {
      initMermaid(theme)
      renderMermaidBlocks(contentRef.current)
    }
  }, [html, theme])

  const handleTocClick = useCallback((id: string) => {
    const el = document.getElementById(id)
    const container = scrollContainerRef.current
    if (el && container) {
      const offset = container.scrollTop + el.getBoundingClientRect().top - container.getBoundingClientRect().top - 20
      container.scrollTo({ top: offset, behavior: 'smooth' })
    }
  }, [])

  if (areaKeys.length === 0) {
    return (
      <div className="flex items-center justify-center h-full view-enter">
        <EmptyState
          icon={'\u2750'}
          title="No bundles loaded"
          description="Load bundle files from the Dashboard to view the bundle analysis."
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
        {/* Bundle selector tabs (when multiple bundles) */}
        {areaKeys.length > 1 && (
          <div className="mb-4 pb-3 border-b-2 border-border">
            <h2 className="font-heading text-sm uppercase tracking-wide text-fg/50 mb-2">Bundles</h2>
            <div className="space-y-1">
              {areaKeys.map((area) => (
                <button
                  type="button"
                  key={area}
                  onClick={() => setActiveArea(area)}
                  className={`block w-full text-left text-sm px-2 py-1 rounded-base truncate transition-colors ${
                    area === activeArea
                      ? 'bg-main text-main-fg font-bold border-2 border-border shadow-neo'
                      : 'border-2 border-transparent hover:bg-main/20 text-fg/70'
                  }`}
                >
                  {formatAreaLabel(area)}
                </button>
              ))}
            </div>
          </div>
        )}

        <h2 className="font-heading text-sm uppercase tracking-wide text-fg/50 mb-3">Contents</h2>
        <nav className="space-y-1">
          {toc.map((entry) => (
            <button
              type="button"
              key={entry.id}
              onClick={() => handleTocClick(entry.id)}
              className={`block w-full text-left text-sm font-base truncate-line hover:text-main transition-colors ${
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
        {/* Horizontal bundle tabs for small screens or when sidebar is hidden */}
        {areaKeys.length > 1 && (
          <div className="lg:hidden flex flex-wrap gap-2 mb-6">
            {areaKeys.map((area) => (
              <button
                type="button"
                key={area}
                onClick={() => setActiveArea(area)}
                className={`text-sm px-3 py-1 rounded-base border-2 transition-colors ${
                  area === activeArea
                    ? 'bg-main text-main-fg border-border shadow-neo font-bold'
                    : 'border-border/50 hover:bg-main/20 text-fg/70'
                }`}
              >
                {formatAreaLabel(area)}
              </button>
            ))}
          </div>
        )}
        <div ref={contentRef} className="prose max-w-none font-base" dangerouslySetInnerHTML={{ __html: html }} />
      </div>
    </div>
  )
}
