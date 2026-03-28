import { createFileRoute } from '@tanstack/react-router'
import { marked } from 'marked'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState } from '../components/empty-state'
import { SearchBar } from '../components/search-bar'
import { initMermaid, renderMermaidBlocks } from '../lib/mermaid-init'
import { useStore } from '../store/use-store'

export const Route = createFileRoute('/signatures')({
  component: SignaturesView,
})

function configureMarked() {
  const renderer = new marked.Renderer()
  renderer.code = ({ text, lang }) => {
    if (lang === 'mermaid') {
      return `<pre><code class="language-mermaid">${text}</code></pre>`
    }
    return `<pre><code class="language-${lang || ''}">${text}</code></pre>`
  }
  marked.setOptions({ renderer })
}

configureMarked()

/** Split markdown into sections by h2/h3 headings, filter by query, rejoin. */
function filterMarkdown(markdown: string, query: string): string {
  if (!query.trim()) return markdown

  const lowerQuery = query.toLowerCase()
  const lines = markdown.split('\n')
  const sections: { heading: string; lines: string[] }[] = []
  let current: { heading: string; lines: string[] } = { heading: '', lines: [] }

  for (const line of lines) {
    if (/^#{1,3}\s+/.test(line)) {
      if (current.heading || current.lines.length > 0) {
        sections.push(current)
      }
      current = { heading: line, lines: [] }
    } else {
      current.lines.push(line)
    }
  }
  if (current.heading || current.lines.length > 0) {
    sections.push(current)
  }

  const filtered = sections.filter((section) => {
    const text = `${section.heading}\n${section.lines.join('\n')}`.toLowerCase()
    return text.includes(lowerQuery)
  })

  return filtered.map((s) => [s.heading, ...s.lines].join('\n')).join('\n')
}

function SignaturesView() {
  const signatures = useStore((s) => s.signatures)
  const pendingSearch = useStore((s) => s.pendingSearch)
  const setPendingSearch = useStore((s) => s.setPendingSearch)
  const theme = useStore((s) => s.theme)
  const contentRef = useRef<HTMLDivElement>(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Consume pending search from store (e.g., navigated from another view with a search)
  useEffect(() => {
    if (pendingSearch) {
      setSearchQuery(pendingSearch)
      setPendingSearch(null)
    }
  }, [pendingSearch, setPendingSearch])

  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query)
  }, [])

  const filteredMd = useMemo(
    () => (signatures ? filterMarkdown(signatures, searchQuery) : ''),
    [signatures, searchQuery],
  )

  const html = useMemo(() => (filteredMd ? (marked.parse(filteredMd) as string) : ''), [filteredMd])

  useEffect(() => {
    if (contentRef.current && html) {
      initMermaid(theme)
      renderMermaidBlocks(contentRef.current)
    }
  }, [html, theme])

  if (!signatures) {
    return (
      <div className="flex items-center justify-center h-full view-enter">
        <EmptyState
          icon={'\u270E'}
          title="No signatures loaded"
          description="Load a CONTEXT.signatures.md file from the Dashboard to view API signatures."
          actionLabel="Go to Dashboard"
          actionTo="/"
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full view-enter">
      {/* Search bar */}
      <div className="shrink-0 border-b-2 border-border bg-bg2 p-4">
        <div className="max-w-2xl">
          <SearchBar placeholder="Filter signatures..." onSearch={handleSearch} initialValue={searchQuery} />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6 lg:p-10">
        {filteredMd.trim() ? (
          <div ref={contentRef} className="prose max-w-none font-base" dangerouslySetInnerHTML={{ __html: html }} />
        ) : (
          <div className="flex items-center justify-center h-full">
            <p className="text-fg/40 font-base text-sm">No signatures match "{searchQuery}"</p>
          </div>
        )}
      </div>
    </div>
  )
}
