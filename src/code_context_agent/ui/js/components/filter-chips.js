// filter-chips.js — Toggleable filter chip set with All/None controls
// Returns an HTML string. Use attachFilterListeners() to wire up interactivity.

/**
 * Render a set of filter chips.
 *
 * @param {object} opts
 * @param {string[]} opts.items       - Array of filter labels (e.g. node types)
 * @param {Set<string>} opts.activeSet - Currently active items
 * @param {Record<string, string>} opts.colorMap - Maps item name to hex color
 * @param {(newSet: Set<string>) => void} opts.onChange - Callback with updated active set
 * @returns {string} HTML string
 */
export function filterChips({ items, activeSet, colorMap, onChange }) {
  const allActive = items.every((item) => activeSet.has(item));

  const toggleAllLabel = allActive ? 'None' : 'All';

  const chips = items
    .map((item) => {
      const active = activeSet.has(item);
      const color = colorMap[item] || '#6a6a86';
      return `
        <button data-filter-chip="${item}"
          class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-base border-2 border-border font-base transition-all ${
            active ? 'shadow-neo bg-bg2' : 'opacity-40'
          }">
          <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background: ${color}"></span>
          ${item}
        </button>`;
    })
    .join('');

  return `
    <div class="flex flex-wrap items-center gap-1.5">
      <button data-filter-toggle-all
        class="inline-flex items-center px-2.5 py-1 text-xs rounded-base border-2 border-border font-base transition-all neo-pressable bg-bg2">
        ${toggleAllLabel}
      </button>
      ${chips}
    </div>`;
}

/**
 * Attach click listeners to filter chips inside a container.
 * Call this after inserting the filterChips HTML into the DOM.
 *
 * @param {string} containerId - ID of the parent element containing the chips
 * @param {string[]} items     - Same items array passed to filterChips()
 * @param {Set<string>} activeSet - Current active set (will be cloned on change)
 * @param {Record<string, string>} colorMap - Same color map
 * @param {(newSet: Set<string>) => void} onChange - Callback with updated active set
 */
export function attachFilterListeners(containerId, items, activeSet, colorMap, onChange) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Toggle individual chips
  container.querySelectorAll('[data-filter-chip]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const item = btn.getAttribute('data-filter-chip');
      const next = new Set(activeSet);
      if (next.has(item)) {
        next.delete(item);
      } else {
        next.add(item);
      }
      onChange(next);
    });
  });

  // Toggle All / None
  const toggleAll = container.querySelector('[data-filter-toggle-all]');
  if (toggleAll) {
    toggleAll.addEventListener('click', () => {
      const allActive = items.every((item) => activeSet.has(item));
      const next = allActive ? new Set() : new Set(items);
      onChange(next);
    });
  }
}
