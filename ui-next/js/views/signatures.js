// signatures.js — Signatures view
// Renders CONTEXT.signatures.md with search/filter and code-friendly styling.

import { store } from '../store.js';
import { renderMarkdownWithIds } from '../markdown.js';
import { searchBar, attachSearchListeners } from '../components/search-bar.js';

const VIEW_ID = 'signatures-view';

/**
 * Escape special regex characters in a string.
 * @param {string} str
 * @returns {string}
 */
function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Walk all text nodes inside a container and wrap matches in <mark>.
 * Returns the number of matches found.
 * @param {HTMLElement} container
 * @param {string} query — the search string (case-insensitive)
 * @returns {number} match count
 */
function highlightMatches(container, query) {
  if (!query) return 0;

  const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
  let matchCount = 0;

  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
  const textNodes = [];
  while (walker.nextNode()) {
    textNodes.push(walker.currentNode);
  }

  for (const node of textNodes) {
    if (!regex.test(node.textContent)) continue;
    regex.lastIndex = 0; // reset after test()

    const fragment = document.createDocumentFragment();
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(node.textContent)) !== null) {
      // Text before the match
      if (match.index > lastIndex) {
        fragment.appendChild(document.createTextNode(node.textContent.slice(lastIndex, match.index)));
      }
      // The highlighted match
      const mark = document.createElement('mark');
      mark.className = 'bg-main/30 rounded-sm px-0.5';
      mark.textContent = match[1];
      fragment.appendChild(mark);
      matchCount++;
      lastIndex = regex.lastIndex;
    }

    // Remaining text after last match
    if (lastIndex < node.textContent.length) {
      fragment.appendChild(document.createTextNode(node.textContent.slice(lastIndex)));
    }

    node.parentNode.replaceChild(fragment, node);
  }

  return matchCount;
}

/**
 * Filter sections by search query: hide sections (h2/h3 blocks) that don't
 * contain the query, then highlight matches in remaining visible sections.
 * @param {HTMLElement} contentEl — the .sig-content element
 * @param {string} rawMd — original markdown source
 * @param {string} query — search string
 */
function applySearch(contentEl, rawMd, query) {
  // Re-render from clean markdown each time to clear previous highlights
  contentEl.innerHTML = renderMarkdownWithIds(rawMd);
  applyCodeStyling(contentEl);

  if (!query) {
    // Show everything, remove any "no results" notice
    contentEl.querySelectorAll('[data-sig-section]').forEach((s) => s.classList.remove('hidden'));
    const notice = contentEl.parentElement.querySelector('.sig-no-results');
    if (notice) notice.remove();
    return;
  }

  // Group DOM nodes into sections delineated by headings
  const sections = [];
  let currentSection = null;

  for (const child of contentEl.children) {
    const tag = child.tagName;
    if (tag === 'H1' || tag === 'H2' || tag === 'H3') {
      currentSection = { heading: child, nodes: [child] };
      sections.push(currentSection);
    } else if (currentSection) {
      currentSection.nodes.push(child);
    } else {
      // Content before the first heading — always visible
      sections.push({ heading: null, nodes: [child] });
    }
  }

  const lowerQuery = query.toLowerCase();
  let visibleSections = 0;

  for (const section of sections) {
    const sectionText = section.nodes.map((n) => n.textContent).join(' ');
    const matches = sectionText.toLowerCase().includes(lowerQuery);

    for (const node of section.nodes) {
      if (matches) {
        node.classList.remove('hidden');
      } else {
        node.classList.add('hidden');
      }
    }

    if (matches) visibleSections++;
  }

  // Highlight matches in visible content
  highlightMatches(contentEl, query);

  // Show/hide "no results" notice
  let notice = contentEl.parentElement.querySelector('.sig-no-results');
  if (visibleSections === 0) {
    if (!notice) {
      notice = document.createElement('div');
      notice.className = 'sig-no-results p-8 text-center text-fg/50 text-sm';
      contentEl.parentElement.appendChild(notice);
    }
    notice.textContent = `No sections matching "${query}"`;
  } else if (notice) {
    notice.remove();
  }
}

/**
 * Apply neobrutalism code styling to rendered markdown content.
 * Targets code blocks and inline code for signature-friendly presentation.
 * @param {HTMLElement} container
 */
function applyCodeStyling(container) {
  // Style fenced code blocks
  container.querySelectorAll('pre').forEach((pre) => {
    pre.className =
      'bg-bg2 border-2 border-border rounded-base p-4 my-3 overflow-x-auto shadow-neo text-sm leading-relaxed';
  });

  container.querySelectorAll('pre code').forEach((code) => {
    code.className = 'font-mono text-fg';
  });

  // Style inline code
  container.querySelectorAll(':not(pre) > code').forEach((code) => {
    code.className = 'font-mono text-sm bg-bg2 border border-border/60 rounded px-1.5 py-0.5';
  });

  // Style headings — function/class names should stand out
  container.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach((h) => {
    h.classList.add('font-heading', 'tracking-tight');
    if (h.tagName === 'H1') {
      h.classList.add('text-2xl', 'mt-8', 'mb-4', 'pb-2', 'border-b-2', 'border-border');
    } else if (h.tagName === 'H2') {
      h.classList.add('text-xl', 'mt-6', 'mb-3');
    } else if (h.tagName === 'H3') {
      h.classList.add('text-lg', 'mt-4', 'mb-2');
    } else {
      h.classList.add('text-base', 'mt-3', 'mb-1');
    }
  });

  // Style paragraphs
  container.querySelectorAll('p').forEach((p) => {
    p.classList.add('my-2', 'leading-relaxed');
  });

  // Style lists
  container.querySelectorAll('ul, ol').forEach((list) => {
    list.classList.add('my-2', 'pl-6');
    if (list.tagName === 'UL') list.classList.add('list-disc');
    if (list.tagName === 'OL') list.classList.add('list-decimal');
  });

  container.querySelectorAll('li').forEach((li) => {
    li.classList.add('my-1');
  });

  // Style tables
  container.querySelectorAll('table').forEach((table) => {
    table.className = 'w-full border-collapse border-2 border-border rounded-base my-4 text-sm';
  });
  container.querySelectorAll('th').forEach((th) => {
    th.className = 'bg-bg2 border-2 border-border px-3 py-2 text-left font-heading';
  });
  container.querySelectorAll('td').forEach((td) => {
    td.className = 'border-2 border-border px-3 py-2';
  });

  // Style blockquotes
  container.querySelectorAll('blockquote').forEach((bq) => {
    bq.className = 'border-l-4 border-main pl-4 my-3 text-fg/70 italic';
  });

  // Style horizontal rules
  container.querySelectorAll('hr').forEach((hr) => {
    hr.className = 'my-6 border-t-2 border-border';
  });
}

/**
 * Render the Signatures view into the given container.
 * Displays CONTEXT.signatures.md with search filtering and code styling.
 *
 * @param {HTMLElement} container — the <main id="content"> element
 * @param {import('../store.js').Store} _store — the global store
 * @returns {() => void} cleanup function
 */
export function render(container, _store) {
  const signatures = store.get('signatures');

  // -- Empty state --
  if (!signatures) {
    container.innerHTML = `
      <div class="flex flex-col items-center justify-center h-full gap-4 p-8 view-enter">
        <div class="w-16 h-16 flex items-center justify-center rounded-base border-2 border-border bg-bg2 shadow-neo text-3xl">
          \u270E
        </div>
        <p class="text-fg/60 text-center max-w-md leading-relaxed">
          No signatures file loaded. Run <code class="font-mono text-sm bg-bg2 border border-border/60 rounded px-1.5 py-0.5">code-context-agent analyze</code> to extract function signatures.
        </p>
      </div>`;
    return () => {};
  }

  // -- Main layout --
  container.innerHTML = `
    <div id="${VIEW_ID}" class="flex flex-col h-full view-enter">
      <!-- Header + Search -->
      <div class="flex items-center gap-4 px-6 py-4 border-b-2 border-border bg-bg2 shrink-0">
        <h2 class="font-heading text-xl tracking-tight whitespace-nowrap">Signatures</h2>
        <div class="flex-1 max-w-md">
          ${searchBar({ placeholder: 'Filter signatures...' })}
        </div>
        <span class="text-xs text-fg/40 whitespace-nowrap sig-match-count"></span>
      </div>

      <!-- Scrollable content -->
      <div class="flex-1 overflow-auto">
        <div class="sig-content max-w-4xl mx-auto px-6 py-6"></div>
      </div>
    </div>`;

  const viewEl = document.getElementById(VIEW_ID);
  const contentEl = viewEl.querySelector('.sig-content');
  const matchCountEl = viewEl.querySelector('.sig-match-count');

  // Render the markdown content
  contentEl.innerHTML = renderMarkdownWithIds(signatures);
  applyCodeStyling(contentEl);

  // -- Search wiring --
  /** @type {string} current search query */
  let currentQuery = '';

  /**
   * Handle search input.
   * @param {string} query
   */
  function onSearch(query) {
    currentQuery = query;
    applySearch(contentEl, signatures, query);

    // Update match count display
    if (query) {
      const marks = contentEl.querySelectorAll('mark');
      matchCountEl.textContent = `${marks.length} match${marks.length === 1 ? '' : 'es'}`;
    } else {
      matchCountEl.textContent = '';
    }
  }

  attachSearchListeners(VIEW_ID, onSearch);

  // -- Store subscription: re-render if signatures data changes --
  const unsubSignatures = store.on('signatures', (newSigs) => {
    if (newSigs) {
      contentEl.innerHTML = renderMarkdownWithIds(newSigs);
      applyCodeStyling(contentEl);
      if (currentQuery) onSearch(currentQuery);
    }
  });

  // -- Cleanup --
  return () => {
    unsubSignatures();
  };
}
