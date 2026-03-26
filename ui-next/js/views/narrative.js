// narrative.js — Renders CONTEXT.md with TOC sidebar and scroll-spy
// Two-column layout: sticky TOC on the left, rendered markdown content on the right.

import { store } from '../store.js';
import { renderMarkdownWithIds, extractTOC } from '../markdown.js';

/**
 * Render the narrative view into the given container.
 * Returns a cleanup function that disconnects the IntersectionObserver.
 *
 * @param {HTMLElement} container
 * @param {import('../store.js').Store} _store
 * @returns {() => void} cleanup
 */
export function render(container, _store) {
  const narrative = store.get('narrative');

  // ── Empty state ──────────────────────────────────────────────────────────
  if (!narrative) {
    container.innerHTML = `
      <div class="flex items-center justify-center h-full">
        <div class="text-center max-w-md p-8 rounded-base border-2 border-border shadow-neo bg-bg2">
          <span class="text-4xl block mb-4">\u2263</span>
          <h2 class="font-heading text-xl mb-2">No Narrative Document</h2>
          <p class="text-sm text-fg/60 font-base leading-relaxed">
            No narrative document loaded. Run the code-context-agent analyzer to generate CONTEXT.md
          </p>
        </div>
      </div>`;
    return () => {};
  }

  // ── Extract TOC and render markdown ──────────────────────────────────────
  const toc = extractTOC(narrative);
  const contentHtml = renderMarkdownWithIds(narrative);

  // ── Build TOC sidebar HTML ───────────────────────────────────────────────
  const minLevel = toc.length > 0 ? Math.min(...toc.map((h) => h.level)) : 1;

  const tocItemsHtml = toc
    .map((entry) => {
      const indent = entry.level - minLevel;
      const paddingLeft = 0.75 + indent * 0.75; // rem
      return `
        <a href="#${entry.id}" data-toc-id="${entry.id}"
           class="toc-link block py-1 px-3 text-sm font-base text-fg/70 rounded-base
                  border-l-2 border-transparent transition-all hover:text-fg hover:bg-main/10"
           style="padding-left: ${paddingLeft}rem;">
          ${escapeHtml(entry.text)}
        </a>`;
    })
    .join('');

  // ── Assemble full layout ─────────────────────────────────────────────────
  container.innerHTML = `
    <div class="flex h-full view-enter">
      <!-- TOC Sidebar -->
      <aside id="narrative-toc" class="w-56 shrink-0 border-r-2 border-border bg-bg2 overflow-y-auto sticky top-0 h-full">
        <div class="p-4 border-b-2 border-border">
          <h2 class="font-heading text-sm uppercase tracking-wide text-fg/60">Table of Contents</h2>
        </div>
        <nav class="p-2 space-y-0.5">
          ${tocItemsHtml || '<p class="text-xs text-fg/40 px-3 py-2">No headings found</p>'}
        </nav>
      </aside>

      <!-- Content -->
      <div id="narrative-content" class="flex-1 overflow-y-auto">
        <div class="max-w-3xl mx-auto p-8">
          <div id="narrative-prose" class="narrative-prose">
            ${contentHtml}
          </div>
        </div>
      </div>
    </div>

    <style>
      /* ── Narrative prose typography ────────────────────────────────── */
      .narrative-prose h1 {
        font-weight: var(--font-weight-heading, 700);
        font-size: 2rem;
        line-height: 1.2;
        margin-top: 2.5rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid var(--border);
      }
      .narrative-prose h2 {
        font-weight: var(--font-weight-heading, 700);
        font-size: 1.5rem;
        line-height: 1.3;
        margin-top: 2rem;
        margin-bottom: 0.75rem;
      }
      .narrative-prose h3 {
        font-weight: var(--font-weight-heading, 700);
        font-size: 1.25rem;
        line-height: 1.4;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
      }
      .narrative-prose h4,
      .narrative-prose h5,
      .narrative-prose h6 {
        font-weight: var(--font-weight-heading, 700);
        font-size: 1.1rem;
        line-height: 1.4;
        margin-top: 1.25rem;
        margin-bottom: 0.5rem;
      }
      .narrative-prose p {
        margin-bottom: 1rem;
        line-height: 1.7;
      }

      /* Code blocks */
      .narrative-prose pre {
        background-color: var(--background);
        border: 2px solid var(--border);
        border-radius: var(--radius-base, 5px);
        padding: 0.75rem;
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
        font-size: 0.875rem;
        overflow-x: auto;
        margin-bottom: 1rem;
      }
      .narrative-prose pre code {
        background: none;
        padding: 0;
        border: none;
        border-radius: 0;
        font-size: inherit;
      }

      /* Inline code */
      .narrative-prose code {
        background-color: var(--background);
        opacity: 0.85;
        padding: 0.125rem 0.25rem;
        border-radius: var(--radius-base, 5px);
        font-size: 0.875rem;
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
      }

      /* Links */
      .narrative-prose a {
        color: var(--main);
        text-decoration: underline;
        text-underline-offset: 2px;
      }
      .narrative-prose a:hover {
        opacity: 0.8;
      }

      /* Lists */
      .narrative-prose ul {
        list-style-type: disc;
        padding-left: 1.5rem;
        margin-bottom: 1rem;
      }
      .narrative-prose ol {
        list-style-type: decimal;
        padding-left: 1.5rem;
        margin-bottom: 1rem;
      }
      .narrative-prose li {
        margin-bottom: 0.375rem;
        line-height: 1.6;
      }
      .narrative-prose li > ul,
      .narrative-prose li > ol {
        margin-top: 0.375rem;
        margin-bottom: 0;
      }

      /* Blockquotes */
      .narrative-prose blockquote {
        border-left: 4px solid var(--main);
        padding-left: 1rem;
        margin-left: 0;
        margin-bottom: 1rem;
        color: var(--foreground);
        opacity: 0.85;
        font-style: italic;
      }

      /* Tables */
      .narrative-prose table {
        width: 100%;
        border-collapse: collapse;
        border: 2px solid var(--border);
        margin-bottom: 1rem;
        font-size: 0.875rem;
      }
      .narrative-prose th {
        background-color: var(--secondary-background);
        font-weight: var(--font-weight-heading, 700);
        text-align: left;
        padding: 0.5rem 0.75rem;
        border: 2px solid var(--border);
      }
      .narrative-prose td {
        padding: 0.5rem 0.75rem;
        border: 2px solid var(--border);
      }
      .narrative-prose tr:nth-child(even) td {
        background-color: var(--background);
      }

      /* Horizontal rule */
      .narrative-prose hr {
        border: none;
        border-top: 2px solid var(--border);
        margin: 2rem 0;
      }

      /* Images */
      .narrative-prose img {
        max-width: 100%;
        border: 2px solid var(--border);
        border-radius: var(--radius-base, 5px);
        margin-bottom: 1rem;
      }

      /* First heading — no top margin */
      .narrative-prose > h1:first-child,
      .narrative-prose > h2:first-child,
      .narrative-prose > h3:first-child {
        margin-top: 0;
      }

      /* ── Active TOC link ──────────────────────────────────────────── */
      .toc-link.toc-active {
        color: var(--foreground);
        background-color: color-mix(in oklch, var(--main) 20%, transparent);
        border-left-color: var(--main);
        font-weight: 600;
      }
    </style>`;

  // ── Scroll-spy via IntersectionObserver ─────────────────────────────────
  const contentEl = container.querySelector('#narrative-content');
  const tocLinks = container.querySelectorAll('.toc-link');
  const tocLinkMap = new Map();
  tocLinks.forEach((link) => {
    tocLinkMap.set(link.dataset.tocId, link);
  });

  /** @type {string|null} */
  let activeId = toc.length > 0 ? toc[0].id : null;

  function setActiveToc(id) {
    if (id === activeId) return;
    // Remove previous
    if (activeId && tocLinkMap.has(activeId)) {
      tocLinkMap.get(activeId).classList.remove('toc-active');
    }
    // Set new
    activeId = id;
    if (activeId && tocLinkMap.has(activeId)) {
      const link = tocLinkMap.get(activeId);
      link.classList.add('toc-active');
      // Scroll TOC sidebar to keep active item visible
      link.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  // Set initial active state
  if (activeId && tocLinkMap.has(activeId)) {
    tocLinkMap.get(activeId).classList.add('toc-active');
  }

  // Observe all heading elements for intersection
  const headingEls = toc
    .map((entry) => contentEl.querySelector(`#${CSS.escape(entry.id)}`))
    .filter(Boolean);

  /** @type {IntersectionObserver|null} */
  let observer = null;

  if (headingEls.length > 0) {
    observer = new IntersectionObserver(
      (entries) => {
        // Find the topmost visible heading
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);

        if (visible.length > 0) {
          setActiveToc(visible[0].target.id);
        }
      },
      {
        root: contentEl,
        rootMargin: '0px 0px -70% 0px',
        threshold: 0,
      },
    );

    headingEls.forEach((el) => observer.observe(el));
  }

  // ── Smooth scroll for TOC links ──────────────────────────────────────────
  const tocNav = container.querySelector('#narrative-toc nav');
  function handleTocClick(e) {
    const link = e.target.closest('.toc-link');
    if (!link) return;
    e.preventDefault();
    const targetId = link.dataset.tocId;
    const targetEl = contentEl.querySelector(`#${CSS.escape(targetId)}`);
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setActiveToc(targetId);
    }
  }
  tocNav?.addEventListener('click', handleTocClick);

  // ── Cleanup ──────────────────────────────────────────────────────────────
  return () => {
    if (observer) {
      observer.disconnect();
      observer = null;
    }
    tocNav?.removeEventListener('click', handleTocClick);
  };
}

/**
 * Escape HTML entities in a string.
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
