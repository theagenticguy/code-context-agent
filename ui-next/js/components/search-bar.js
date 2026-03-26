// search-bar.js — Debounced search input with keyboard hint
// Returns an HTML string. Use attachSearchListeners() to wire up interactivity.

/**
 * Render a search bar input.
 *
 * @param {object} opts
 * @param {string} [opts.placeholder='Search...'] - Placeholder text
 * @param {(query: string) => void} opts.onSearch  - Callback fired on debounced input
 * @returns {string} HTML string
 */
export function searchBar({ placeholder = 'Search...', onSearch }) {
  return `
    <div class="relative" data-search-bar>
      <input type="text" placeholder="${placeholder}"
        data-search-input
        class="w-full h-9 px-3 pr-8 text-sm rounded-base border-2 border-border bg-bg2 text-fg font-base neo-focus"
      />
      <span class="absolute right-2.5 top-1/2 -translate-y-1/2 text-fg/30 text-xs pointer-events-none">\u2318K</span>
    </div>`;
}

/**
 * Attach input listeners to the search bar inside a container.
 * Call this after inserting the searchBar HTML into the DOM.
 *
 * Debounces input by 200ms before calling onSearch.
 *
 * @param {string} containerId - ID of the parent element containing the search bar
 * @param {(query: string) => void} onSearch - Callback with the current query string
 */
export function attachSearchListeners(containerId, onSearch) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const input = container.querySelector('[data-search-input]');
  if (!input) return;

  let timer = null;

  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      onSearch(input.value.trim());
    }, 200);
  });

  // Clear on Escape
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      input.value = '';
      clearTimeout(timer);
      onSearch('');
      input.blur();
    }
  });

  // Global Cmd+K / Ctrl+K focuses the search bar
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      input.focus();
      input.select();
    }
  });
}
