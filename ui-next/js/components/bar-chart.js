// bar-chart.js — Horizontal bar chart using pure HTML/CSS
// Returns an HTML string. No D3 or SVG required.

/**
 * Render a horizontal bar chart.
 *
 * @param {object} opts
 * @param {Array<Record<string, any>>} opts.data - Array of data items
 * @param {string} opts.labelKey  - Key in each item for the bar label
 * @param {string} opts.valueKey  - Key in each item for the numeric value
 * @param {(item: Record<string, any>) => string} [opts.colorFn] - Returns hex color per item
 * @param {number} [opts.maxBars=10] - Maximum number of bars to display
 * @param {number} [opts.height]     - Not used (kept for API compat); bars are fixed height
 * @returns {string} HTML string
 */
export function barChart({ data, labelKey, valueKey, colorFn, maxBars = 10, height }) {
  if (!data || data.length === 0) {
    return `<div class="text-xs text-fg/40 py-4 text-center font-base">No data</div>`;
  }

  // Sort descending by value, take top N
  const sorted = [...data]
    .sort((a, b) => (b[valueKey] || 0) - (a[valueKey] || 0))
    .slice(0, maxBars);

  const maxValue = sorted.reduce((m, item) => Math.max(m, item[valueKey] || 0), 0) || 1;

  const bars = sorted
    .map((item) => {
      const label = item[labelKey] || '';
      const value = item[valueKey] || 0;
      const pct = (value / maxValue) * 100;
      const color = colorFn ? colorFn(item) : '#60a5fa';

      return `
        <div class="flex items-center gap-2 text-xs">
          <span class="w-28 truncate-line text-fg/70 font-base" title="${label}">${label}</span>
          <div class="flex-1 h-5 rounded-base border border-border/30 bg-bg overflow-hidden">
            <div class="h-full rounded-base transition-all duration-300" style="width: ${pct.toFixed(1)}%; background: ${color}"></div>
          </div>
          <span class="w-10 text-right font-heading text-fg/70">${value}</span>
        </div>`;
    })
    .join('');

  return `<div class="space-y-1.5">${bars}</div>`;
}
