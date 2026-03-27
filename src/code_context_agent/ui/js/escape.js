// escape.js — Shared HTML escaping utilities

/**
 * Escape a string for safe insertion into innerHTML.
 * @param {string} str
 * @returns {string}
 */
export function escapeHtml(str) {
  if (str == null) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

/**
 * Marker wrapper for pre-escaped HTML that should bypass safeHtml escaping.
 * Use when embedding output from component functions that already return
 * safe HTML (e.g. searchBar(), filterChips(), statCard()).
 * @param {string} htmlString — must already be escaped/trusted
 * @returns {{ __safeHtml: true, toString: () => string }}
 */
export function rawHtml(htmlString) {
  return { __safeHtml: true, toString: () => String(htmlString ?? '') };
}

/**
 * Tagged template literal that auto-escapes all interpolated values.
 *
 * Usage:
 *   container.innerHTML = safeHtml`<div>${userName}</div>`;
 *
 * Values wrapped in rawHtml() bypass escaping:
 *   container.innerHTML = safeHtml`<div>${rawHtml(componentOutput)}</div>`;
 *
 * @param {TemplateStringsArray} strings
 * @param {...*} values
 * @returns {string}
 */
export function safeHtml(strings, ...values) {
  return strings.reduce((result, str, i) => {
    if (i >= values.length) return result + str;
    const val = values[i];
    const escaped = val && val.__safeHtml ? val.toString() : escapeHtml(String(val ?? ''));
    return result + str + escaped;
  }, '');
}
