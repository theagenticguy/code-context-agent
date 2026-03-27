// sidebar.js — Navigation sidebar component
// Renders the main navigation, theme toggle, and keyboard shortcut hints.

import { safeHtml, rawHtml } from '../escape.js';

/**
 * View definitions for the sidebar navigation.
 * Each entry maps a view ID to its display label, hash route, and keyboard shortcut.
 * @type {Array<{ id: string, label: string, hash: string, key: string, icon: string }>}
 */
const NAV_ITEMS = [
  { id: 'landing',      label: 'Home',         hash: '#/',              key: '1', icon: '\u2302' },
  { id: 'dashboard',    label: 'Dashboard',     hash: '#/dashboard',     key: '2', icon: '\u25A6' },
  { id: 'graph',        label: 'Graph',         hash: '#/graph',         key: '3', icon: '\u2B21' },
  { id: 'modules',      label: 'Modules',       hash: '#/modules',       key: '4', icon: '\u29C9' },
  { id: 'hotspots',     label: 'Hotspots',      hash: '#/hotspots',      key: '5', icon: '\u2622' },
  { id: 'dependencies', label: 'Dependencies',  hash: '#/dependencies',  key: '6', icon: '\u21C4' },
  { id: 'narrative',    label: 'Narrative',      hash: '#/narrative',     key: '7', icon: '\u2263' },
  { id: 'bundles',      label: 'Bundles',        hash: '#/bundles',       key: '8', icon: '\u2750' },
  { id: 'insights',     label: 'Insights',       hash: '#/insights',      key: '9', icon: '\u2605' },
  { id: 'signatures',   label: 'Signatures',     hash: '#/signatures',    key: '0', icon: '\u270E' },
];

/**
 * Render a single navigation item.
 * @param {{ id: string, label: string, hash: string, key: string, icon: string }} item
 * @param {boolean} isActive
 * @returns {string}
 */
function navItem(item, isActive) {
  const activeClasses = isActive
    ? 'bg-main text-main-fg border-2 border-border shadow-neo'
    : 'border-2 border-transparent hover:bg-main/20';
  return `
    <a href="${item.hash}" data-view="${item.id}"
       class="flex items-center gap-2.5 px-2.5 py-1.5 rounded-base text-sm font-base transition-all ${activeClasses}">
      <span class="w-5 text-center text-base leading-none">${item.icon}</span>
      <span class="flex-1 truncate-line">${item.label}</span>
      <kbd class="text-[10px] min-w-[18px] h-[18px] inline-flex items-center justify-center px-1 rounded border border-border/40 bg-bg/50 font-mono leading-none ${isActive ? 'border-main-fg/40 bg-main-fg/10' : ''}">${item.key}</kbd>
    </a>`;
}

/**
 * Render the sidebar into the given container element.
 * Subscribes to store.activeView to highlight the current nav item.
 *
 * @param {HTMLElement} container - The <aside id="sidebar"> element
 * @param {import('../store.js').Store} store
 * @param {import('../router.js').Router} router
 */
export function renderSidebar(container, store, router) {
  function render() {
    const activeView = store.get('activeView');
    const template = safeHtml`
      <aside class="w-56 border-r-2 border-border bg-bg2 flex flex-col h-full">
        <div class="p-4 border-b-2 border-border">
          <h1 class="font-heading text-lg tracking-tight">Code Context</h1>
          <p class="text-xs text-fg/50 mt-1">Agent Visualizer</p>
        </div>
        <nav class="flex-1 p-2 space-y-1 overflow-auto">
          ${rawHtml(NAV_ITEMS.map((item) => navItem(item, item.id === activeView)).join(''))}
        </nav>
        <div class="p-3 border-t-2 border-border">
          <button id="theme-toggle"
            class="w-full flex items-center justify-center gap-2 px-3 py-1.5 text-xs rounded-base border-2 border-border font-base neo-pressable bg-bg2 hover:bg-main/20 transition-colors">
            <span id="theme-icon">${store.get('theme') === 'dark' ? '\u263E' : '\u2600'}</span>
            <span id="theme-label">${store.get('theme') === 'dark' ? 'Light mode' : 'Dark mode'}</span>
            <kbd class="ml-auto text-[10px] px-1 py-0.5 rounded border border-border/40 bg-bg/50 font-mono leading-none">D</kbd>
          </button>
        </div>
      </aside>`;
    // All interpolated values auto-escaped via safeHtml; navItem() wrapped in rawHtml() is a static internal component
    container.innerHTML = template; // nosemgrep: javascript.browser.security.insecure-document-method.insecure-document-method

    // Wire up theme toggle click
    const btn = container.querySelector('#theme-toggle');
    btn?.addEventListener('click', () => {
      const current = store.get('theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.classList.add('transitioning-theme');
      document.documentElement.classList.toggle('dark');
      localStorage.setItem('theme', next);
      store.set({ theme: next });
      setTimeout(() => document.documentElement.classList.remove('transitioning-theme'), 350);
    });
  }

  // Initial render
  render();

  // Re-render when active view changes
  store.on('activeView', render);

  // Re-render when theme changes (to update icon/label)
  store.on('theme', render);
}
