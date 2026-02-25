/**
 * Narrative view — renders CONTEXT.md with rich formatting.
 */
import { state } from './state.js';

export function renderNarrative() {
  if (!state.narrative) {
    document.getElementById('narrative-content').innerHTML = `
      <div class="empty-state">
        <p>No CONTEXT.md loaded. Load analysis results to view the narrative.</p>
      </div>
    `;
    document.getElementById('narrative-toc').innerHTML = '';
    return;
  }

  // Render markdown
  const html = marked.parse(state.narrative, {
    gfm: true,
    breaks: false,
    highlight: (code, lang) => {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value;
      }
      return hljs.highlightAuto(code).value;
    },
  });

  const content = document.getElementById('narrative-content');
  content.innerHTML = html;

  // Syntax-highlight all code blocks
  content.querySelectorAll('pre code').forEach(block => {
    hljs.highlightElement(block);
  });

  // Handle mermaid diagrams
  content.querySelectorAll('pre code.language-mermaid').forEach(block => {
    const pre = block.closest('pre');
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = block.textContent;
    pre.replaceWith(div);
  });

  // Also handle ```mermaid fenced blocks that marked wraps differently
  content.querySelectorAll('code.language-mermaid').forEach(block => {
    const pre = block.closest('pre');
    if (pre) {
      const div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = block.textContent;
      pre.replaceWith(div);
    }
  });

  // Build table of contents
  buildTOC(content);

  // Add heading IDs for TOC linking
  content.querySelectorAll('h1, h2, h3, h4, h5').forEach((heading, i) => {
    heading.id = `heading-${i}`;
  });
}

function buildTOC(content) {
  const toc = document.getElementById('narrative-toc');
  const headings = content.querySelectorAll('h1, h2, h3');

  if (headings.length === 0) {
    toc.innerHTML = '';
    return;
  }

  let html = '<h4>Contents</h4><ul class="toc-list">';

  headings.forEach((heading, i) => {
    heading.id = `heading-${i}`;
    const depth = parseInt(heading.tagName[1]);
    const depthClass = depth <= 1 ? '' : `depth-${depth}`;

    html += `<li class="toc-item ${depthClass}" data-target="heading-${i}">
      ${esc(heading.textContent)}
    </li>`;
  });

  html += '</ul>';
  toc.innerHTML = html;

  // Click handler
  toc.querySelectorAll('.toc-item').forEach(item => {
    item.addEventListener('click', () => {
      const target = document.getElementById(item.dataset.target);
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        // Update active TOC item
        toc.querySelectorAll('.toc-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
      }
    });
  });

  // Scroll spy
  const narrativeContent = document.getElementById('narrative-content');
  narrativeContent.addEventListener('scroll', () => {
    let current = '';
    headings.forEach(heading => {
      if (heading.getBoundingClientRect().top < 120) {
        current = heading.id;
      }
    });
    if (current) {
      toc.querySelectorAll('.toc-item').forEach(item => {
        item.classList.toggle('active', item.dataset.target === current);
      });
    }
  });
}

function esc(s) {
  if (!s) return '';
  const el = document.createElement('span');
  el.textContent = String(s);
  return el.innerHTML;
}
