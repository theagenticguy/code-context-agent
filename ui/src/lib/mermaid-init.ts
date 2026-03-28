import mermaid from 'mermaid'

let initialized: 'light' | 'dark' | null = null

export function initMermaid(theme: 'light' | 'dark') {
  if (initialized === theme) return
  mermaid.initialize({
    startOnLoad: false,
    theme: theme === 'dark' ? 'dark' : 'default',
    fontFamily: "'DM Sans', sans-serif",
    flowchart: { curve: 'basis' },
    securityLevel: 'loose',
  })
  initialized = theme
}

export async function renderMermaidBlocks(container: HTMLElement) {
  const blocks = container.querySelectorAll('pre > code.language-mermaid, code.language-mermaid')
  for (const block of blocks) {
    const pre = block.parentElement?.tagName === 'PRE' ? block.parentElement : block
    const code = block.textContent || ''
    try {
      const id = `mermaid-${Math.random().toString(36).slice(2, 9)}`
      const { svg } = await mermaid.render(id, code)
      const wrapper = document.createElement('div')
      wrapper.className = 'mermaid-diagram rounded-base border-2 border-border bg-bg2 p-4 my-4 overflow-auto'
      wrapper.innerHTML = svg
      pre.replaceWith(wrapper)
    } catch (e) {
      // Leave as code block if mermaid parse fails
      console.warn('Mermaid render failed:', e)
    }
  }
}
