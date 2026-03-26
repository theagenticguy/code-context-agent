// bundles.js — Focused analysis bundle viewer
// Renders CONTEXT.bundle.md with TOC sidebar, scroll-spy, and contextual callout.
// Uses the same markdown styling approach as the narrative view.

import { store } from '../store.js';
import { renderMarkdownWithIds, extractTOC } from '../markdown.js';

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

/**
 * Render the bundles view into the given container.
 * Returns a cleanup function that disconnects observers and listeners.
 *
 * @param {HTMLElement} container
 * @param {import('../store.js').Store} _store
 * @returns {() => void} cleanup
 */
export function render(container, _store) {
  const unsubs = [];

  function draw() {
    const bundle = store.get('bundle');

    // ── Empty state ────────────────────────────────────────────────────────
    if (!bundle) {
      container.innerHTML = `
        <div class="flex flex-col h-full view-enter">
          <header class="p-6 border-b-2 border-border">
            <h1 class="font-heading text-2xl">Bundles \u2014 Focused Analysis</h1>
            <p class="text-fg/60 mt-1 text-sm font-base">Deep-dive into specific capabilities</p>
          </header>
          <div class="flex-1 flex items-center justify-center">
            <div class="max-w-2xl mx-auto p-8">
              <h2 class="font-heading text-xl">No Bundle Loaded</h2>
              <p class="mt-2 text-fg/70">Bundles are focused analysis results generated when you run:</p>
              <code class="block mt-3 p-3 bg-bg2 border-2 border-border rounded-base text-sm">
                code-context-agent analyze --focus "auth module"
              </code>
              <p class="mt-3 text-fg/70">This produces a CONTEXT.bundle.md with deep analysis scoped to that specific area of your codebase.</p>
            </div>
          </div>
        </div>`;
      return;
    }

    // ── Extract TOC and render markdown ────────────────────────────────────
    const toc = extractTOC(bundle);
    const contentHtml = renderMarkdownWithIds(bundle);

    // ── Build TOC sidebar HTML ─────────────────────────────────────────────
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

    // ── Assemble full layout ───────────────────────────────────────────────
    container.innerHTML = `
      <div class="flex h-full view-enter">
        <!-- TOC Sidebar -->
        <aside id="bundle-toc" class="w-56 shrink-0 border-r-2 border-border bg-bg2 overflow-y-auto sticky top-0 h-full">
          <div class="p-4 border-b-2 border-border">
            <h2 class="font-heading text-sm uppercase tracking-wide text-fg/60">Contents</h2>
          </div>
          <nav class="p-2 space-y-0.5">
            ${tocItemsHtml || '<p class="text-xs text-fg/40 px-3 py-2">No headings found</p>'}
          </nav>
        </aside>

        <!-- Content -->
        <div id="bundle-scroll" class="flex-1 overflow-y-auto">
          <div class="max-w-3xl mx-auto p-8">
            <!-- Header -->
            <header class="mb-6">
              <h1 class="font-heading text-2xl">Bundles \u2014 Focused Analysis</h1>
              <p class="text-fg/60 mt-1 text-sm font-base">Deep-dive into specific capabilities</p>
            </header>

            <!-- Callout card -->
            <div class="mb-6 p-4 bg-main/10 border-2 border-border rounded-base shadow-neo">
              <p class="text-sm font-base text-fg/80">
                <span class="font-heading text-main mr-1">\u25A0</span>
                This bundle was generated with
                <code class="bundle-prose-inline-code">\u2011\u2011focus</code>
                mode, analyzing a specific area of the codebase.
              </p>
            </div>

            <!-- Rendered bundle markdown -->
            <div id="bundle-prose" class="bundle-prose">
              ${contentHtml}
            </div>
          </div>
        </div>
      </div>

      <style>
        /* ── Bundle prose typography (matches narrative-prose) ──────────── */
        .bundle-prose h1 {
          font-weight: var(--font-weight-heading, 700);
          font-size: 2rem;
          line-height: 1.2;
          margin-top: 2.5rem;
          margin-bottom: 1rem;
          padding-bottom: 0.5rem;
          border-bottom: 2px solid var(--border);
        }
        .bundle-prose h2 {
          font-weight: var(--font-weight-heading, 700);
          font-size: 1.5rem;
          line-height: 1.3;
          margin-top: 2rem;
          margin-bottom: 0.75rem;
        }
        .bundle-prose h3 {
          font-weight: var(--font-weight-heading, 700);
          font-size: 1.25rem;
          line-height: 1.4;
          margin-top: 1.5rem;
          margin-bottom: 0.5rem;
        }
        .bundle-prose h4,
        .bundle-prose h5,
        .bundle-prose h6 {
          font-weight: var(--font-weight-heading, 700);
          font-size: 1.1rem;
          line-height: 1.4;
          margin-top: 1.25rem;
          margin-bottom: 0.5rem;
        }
        .bundle-prose p {
          margin-bottom: 1rem;
          line-height: 1.7;
        }

        /* Code blocks */
        .bundle-prose pre {
          background-color: var(--background);
          border: 2px solid var(--border);
          border-radius: var(--radius-base, 5px);
          padding: 0.75rem;
          font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
          font-size: 0.875rem;
          overflow-x: auto;
          margin-bottom: 1rem;
        }
        .bundle-prose pre code {
          background: none;
          padding: 0;
          border: none;
          border-radius: 0;
          font-size: inherit;
        }

        /* Inline code */
        .bundle-prose code {
          background-color: var(--background);
          opacity: 0.85;
          padding: 0.125rem 0.25rem;
          border-radius: var(--radius-base, 5px);
          font-size: 0.875rem;
          font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
        }

        /* Callout inline code (outside .bundle-prose) */
        .bundle-prose-inline-code {
          background-color: var(--background);
          padding: 0.125rem 0.375rem;
          border-radius: var(--radius-base, 5px);
          font-size: 0.8125rem;
          font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
        }

        /* Links */
        .bundle-prose a {
          color: var(--main);
          text-decoration: underline;
          text-underline-offset: 2px;
        }
        .bundle-prose a:hover {
          opacity: 0.8;
        }

        /* Lists */
        .bundle-prose ul {
          list-style-type: disc;
          padding-left: 1.5rem;
          margin-bottom: 1rem;
        }
        .bundle-prose ol {
          list-style-type: decimal;
          padding-left: 1.5rem;
          margin-bottom: 1rem;
        }
        .bundle-prose li {
          margin-bottom: 0.375rem;
          line-height: 1.6;
        }
        .bundle-prose li > ul,
        .bundle-prose li > ol {
          margin-top: 0.375rem;
          margin-bottom: 0;
        }

        /* Blockquotes */
        .bundle-prose blockquote {
          border-left: 4px solid var(--main);
          padding-left: 1rem;
          margin-left: 0;
          margin-bottom: 1rem;
          color: var(--foreground);
          opacity: 0.85;
          font-style: italic;
        }

        /* Tables */
        .bundle-prose table {
          width: 100%;
          border-collapse: collapse;
          border: 2px solid var(--border);
          margin-bottom: 1rem;
          font-size: 0.875rem;
        }
        .bundle-prose th {
          background-color: var(--secondary-background);
          font-weight: var(--font-weight-heading, 700);
          text-align: left;
          padding: 0.5rem 0.75rem;
          border: 2px solid var(--border);
        }
        .bundle-prose td {
          padding: 0.5rem 0.75rem;
          border: 2px solid var(--border);
        }
        .bundle-prose tr:nth-child(even) td {
          background-color: var(--background);
        }

        /* Horizontal rule */
        .bundle-prose hr {
          border: none;
          border-top: 2px solid var(--border);
          margin: 2rem 0;
        }

        /* Images */
        .bundle-prose img {
          max-width: 100%;
          border: 2px solid var(--border);
          border-radius: var(--radius-base, 5px);
          margin-bottom: 1rem;
        }

        /* First heading — no top margin */
        .bundle-prose > h1:first-child,
        .bundle-prose > h2:first-child,
        .bundle-prose > h3:first-child {
          margin-top: 0;
        }

        /* ── Active TOC link ──────────────────────────────────────────── */
        #bundle-toc .toc-link.toc-active {
          color: var(--foreground);
          background-color: color-mix(in oklch, var(--main) 20%, transparent);
          border-left-color: var(--main);
          font-weight: 600;
        }
      </style>`;

    // ── Scroll-spy via IntersectionObserver ───────────────────────────────
    const scrollEl = container.querySelector('#bundle-scroll');
    const tocLinks = container.querySelectorAll('#bundle-toc .toc-link');
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
        link.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }

    // Set initial active state
    if (activeId && tocLinkMap.has(activeId)) {
      tocLinkMap.get(activeId).classList.add('toc-active');
    }

    // Observe all heading elements for intersection
    const headingEls = toc
      .map((entry) => scrollEl.querySelector(`#${CSS.escape(entry.id)}`))
      .filter(Boolean);

    /** @type {IntersectionObserver|null} */
    let observer = null;

    if (headingEls.length > 0) {
      observer = new IntersectionObserver(
        (entries) => {
          const visible = entries
            .filter((e) => e.isIntersecting)
            .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);

          if (visible.length > 0) {
            setActiveToc(visible[0].target.id);
          }
        },
        {
          root: scrollEl,
          rootMargin: '0px 0px -70% 0px',
          threshold: 0,
        },
      );

      headingEls.forEach((el) => observer.observe(el));
    }

    // ── Smooth scroll for TOC links ──────────────────────────────────────
    const tocNav = container.querySelector('#bundle-toc nav');
    function handleTocClick(e) {
      const link = e.target.closest('.toc-link');
      if (!link) return;
      e.preventDefault();
      const targetId = link.dataset.tocId;
      const targetEl = scrollEl.querySelector(`#${CSS.escape(targetId)}`);
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        setActiveToc(targetId);
      }
    }
    tocNav?.addEventListener('click', handleTocClick);

    // Store cleanup for this draw cycle
    unsubs.push(() => {
      if (observer) {
        observer.disconnect();
        observer = null;
      }
      tocNav?.removeEventListener('click', handleTocClick);
    });
  }

  // Initial draw
  draw();

  // Re-render when bundle data changes
  unsubs.push(store.on('bundle', draw));

  // Return cleanup function
  return () => {
    for (const unsub of unsubs) unsub();
  };
}
