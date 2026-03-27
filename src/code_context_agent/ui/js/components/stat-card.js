// stat-card.js — Statistic card with optional trend badge and sparkline
// Returns an HTML string. Caller inserts via setHTML().

import { escapeHtml } from '../escape.js';

/**
 * Build an inline SVG sparkline from an array of numbers.
 * @param {number[]} data
 * @param {string} color - Stroke color (hex)
 * @returns {string} SVG markup
 */
function sparkline(data, color) {
  if (!data || data.length < 2) return '';

  const width = 100;
  const height = 24;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 2) - 1; // 1px padding top/bottom
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return `
    <svg viewBox="0 0 ${width} ${height}" class="w-full mt-2" style="height: ${height}px;" preserveAspectRatio="none">
      <polyline
        points="${points}"
        fill="none"
        stroke="${color}"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>`;
}

/**
 * Render a stat card.
 *
 * @param {object} opts
 * @param {string} opts.title      - Label above the value (e.g. "Total Nodes")
 * @param {string|number} opts.value - The main metric value
 * @param {string} [opts.subtitle] - Optional subtitle below the value
 * @param {string} [opts.color]    - Hex color for the value text
 * @param {'up'|'down'|null} [opts.trend] - Optional trend direction
 * @param {number[]} [opts.sparkData] - Optional array of numbers for a sparkline
 * @returns {string} HTML string
 */
export function statCard({ title, value, subtitle, color, trend, sparkData }) {
  const trendBadge = trend
    ? `<span class="inline-flex items-center text-xs font-heading px-1.5 py-0.5 rounded-base border border-border/30 ${
        trend === 'up'
          ? 'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/30'
          : 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900/30'
      }">${trend === 'up' ? '\u25B2' : '\u25BC'}</span>`
    : '';

  const subtitleHtml = subtitle
    ? `<p class="text-xs text-fg/50 mt-1">${escapeHtml(subtitle)}</p>`
    : '';

  const sparkHtml = sparkData ? sparkline(sparkData, color || '#60a5fa') : '';

  return `
    <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-4 font-base">
      <div class="flex items-center justify-between">
        <span class="text-xs text-fg/60 uppercase tracking-wide">${escapeHtml(title)}</span>
        ${trendBadge}
      </div>
      <div class="text-2xl font-heading mt-1"${color ? ` style="color: ${color}"` : ''}>${escapeHtml(String(value))}</div>
      ${subtitleHtml}
      ${sparkHtml}
    </div>`;
}
