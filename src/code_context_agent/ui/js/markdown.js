// markdown.js — Markdown rendering with TOC extraction

/**
 * Render markdown string to HTML.
 * Uses window.marked (loaded via CDN).
 * @param {string} md - Markdown source
 * @returns {string} HTML string
 */
export function renderMarkdown(md) {
  if (!md) return '';
  return window.marked.parse(md);
}

/**
 * Extract table of contents from markdown.
 * @param {string} md - Markdown source
 * @returns {Array<{level: number, text: string, id: string}>}
 */
export function extractTOC(md) {
  if (!md) return [];
  const headingRegex = /^(#{1,6})\s+(.+)$/gm;
  const toc = [];
  let match;
  while ((match = headingRegex.exec(md)) !== null) {
    const level = match[1].length;
    const text = match[2].trim();
    const id = text.toLowerCase().replace(/[^\w]+/g, '-').replace(/^-|-$/g, '');
    toc.push({ level, text, id });
  }
  return toc;
}

/**
 * Render markdown with heading IDs for scroll-spy.
 * Each heading gets an id derived from its text content.
 * @param {string} md - Markdown source
 * @returns {string} HTML string with id attributes on headings
 */
export function renderMarkdownWithIds(md) {
  if (!md) return '';
  // Configure marked to add IDs to headings
  const renderer = new window.marked.Renderer();
  renderer.heading = function ({ tokens, depth }) {
    const text = this.parser.parseInline(tokens);
    const id = text.toLowerCase().replace(/<[^>]*>/g, '').replace(/[^\w]+/g, '-').replace(/^-|-$/g, '');
    return `<h${depth} id="${id}" class="scroll-mt-4">${text}</h${depth}>`;
  };
  return window.marked.parse(md, { renderer });
}
