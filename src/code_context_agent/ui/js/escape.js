// escape.js — Shared HTML escaping and safe DOM rendering utilities

const ESCAPE_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

/**
 * Escape a string for safe insertion into HTML.
 * @param {string} str
 * @returns {string}
 */
export function escapeHtml(str) {
  if (str == null) return '';
  return String(str).replace(/[&<>"']/g, (c) => ESCAPE_MAP[c]);
}

const domParser = new DOMParser();

/**
 * Safely set the HTML content of an element without using innerHTML.
 * Uses DOMParser to parse the HTML string, then replaces the element's
 * children with the parsed nodes. Unlike innerHTML, DOMParser does not
 * execute inline <script> tags, providing defense-in-depth.
 *
 * @param {HTMLElement} el - Target element
 * @param {string} html - HTML string (should be pre-sanitized via safeHtml/escapeHtml)
 */
export function setHTML(el, html) {
  const doc = domParser.parseFromString(html, 'text/html');
  el.replaceChildren(...doc.body.childNodes);
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
 *   setHTML(container, safeHtml`<div>${userName}</div>`);
 *
 * Values wrapped in rawHtml() bypass escaping:
 *   setHTML(container, safeHtml`<div>${rawHtml(componentOutput)}</div>`);
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
