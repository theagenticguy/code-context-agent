// tooltip.js — Global tooltip show/hide using the #tooltip element
// Positioned with boundary detection to stay within the viewport.

import { setHTML } from '../escape.js';

/**
 * Show the global tooltip at the given position.
 *
 * @param {string} html - Inner HTML content for the tooltip
 * @param {number} x    - Mouse/pointer X coordinate (clientX)
 * @param {number} y    - Mouse/pointer Y coordinate (clientY)
 */
export function showTooltip(html, x, y) {
  const el = document.getElementById('tooltip');
  if (!el) return;

  // All callers pre-escape content via escapeHtml() or safeHtml before passing to showTooltip()
  setHTML(el, html);
  el.classList.remove('hidden');

  // Force layout so we can measure the rendered size
  el.style.left = '0px';
  el.style.top = '0px';
  el.style.visibility = 'hidden';
  el.classList.add('visible');

  const rect = el.getBoundingClientRect();
  const left = Math.min(x + 12, window.innerWidth - rect.width - 8);
  const top = Math.min(y - 8, window.innerHeight - rect.height - 8);

  el.style.left = Math.max(8, left) + 'px';
  el.style.top = Math.max(8, top) + 'px';
  el.style.visibility = '';
}

/**
 * Hide the global tooltip.
 */
export function hideTooltip() {
  const el = document.getElementById('tooltip');
  if (!el) return;

  el.classList.remove('visible');
  el.classList.add('hidden');
  el.replaceChildren();
}
