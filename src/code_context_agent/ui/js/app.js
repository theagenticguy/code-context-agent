// app.js — Entry point
// Wires together the router, store, data-loader, and lazy-loaded views.

import { Router } from './router.js';
import { store } from './store.js';
import { setupDragDrop } from './data-loader.js';
import { renderSidebar } from './components/sidebar.js';

// ---------------------------------------------------------------------------
// View imports (lazy-loaded on first navigation)
// ---------------------------------------------------------------------------

const views = {
  landing:      () => import('./views/landing.js'),
  dashboard:    () => import('./views/dashboard.js'),
  graph:        () => import('./views/graph.js'),
  modules:      () => import('./views/modules.js'),
  hotspots:     () => import('./views/hotspots.js'),
  dependencies: () => import('./views/dependencies.js'),
  narrative:    () => import('./views/narrative.js'),
  bundles:      () => import('./views/bundles.js'),
  insights:     () => import('./views/insights.js'),
  signatures:   () => import('./views/signatures.js'),
};

// ---------------------------------------------------------------------------
// Router setup
// ---------------------------------------------------------------------------

const content = document.getElementById('content');
const router = new Router();

/** @type {(() => void)|null} */
let currentCleanup = null;

router.beforeNavigate = () => {
  if (currentCleanup) {
    currentCleanup();
    currentCleanup = null;
  }
};

/**
 * Load and render a view into the content area.
 * If the view's render() returns a function, it is stored as a cleanup hook.
 * @param {string} viewId
 */
async function renderView(viewId) {
  store.set({ activeView: viewId });
  content.textContent = '';
  const loader = document.createElement('div');
  loader.className = 'flex items-center justify-center h-full';
  const span = document.createElement('span');
  span.className = 'text-fg/50';
  span.textContent = 'Loading...';
  loader.appendChild(span);
  content.appendChild(loader);
  try {
    const mod = await views[viewId]();
    const result = mod.render(content, store);
    if (result && typeof result === 'function') {
      currentCleanup = result; // view returns cleanup function
    }
  } catch (e) {
    content.textContent = '';
    const errDiv = document.createElement('div');
    errDiv.className = 'p-8 text-red-500';
    errDiv.textContent = 'Error loading view: ' + e.message;
    content.appendChild(errDiv);
    console.error('[app] Error loading view:', viewId, e);
  }
}

// Register routes
router
  .add('#/',              'landing',      () => renderView('landing'))
  .add('#/dashboard',     'dashboard',    () => renderView('dashboard'))
  .add('#/graph',         'graph',        () => renderView('graph'))
  .add('#/modules',       'modules',      () => renderView('modules'))
  .add('#/hotspots',      'hotspots',     () => renderView('hotspots'))
  .add('#/dependencies',  'dependencies', () => renderView('dependencies'))
  .add('#/narrative',     'narrative',    () => renderView('narrative'))
  .add('#/bundles',       'bundles',      () => renderView('bundles'))
  .add('#/insights',      'insights',     () => renderView('insights'))
  .add('#/signatures',    'signatures',   () => renderView('signatures'));

// ---------------------------------------------------------------------------
// Keyboard shortcuts
// ---------------------------------------------------------------------------

const viewKeys = [
  'landing', 'dashboard', 'graph', 'modules', 'hotspots',
  'dependencies', 'narrative', 'bundles', 'insights', 'signatures',
];

document.addEventListener('keydown', (e) => {
  // Ignore when typing in form fields
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

  // Number keys 1-9,0 map to views
  const num = parseInt(e.key);
  if (num >= 0 && num <= 9) {
    const idx = num === 0 ? 9 : num - 1;
    const viewId = viewKeys[idx];
    if (viewId) {
      router.navigate(`#/${viewId === 'landing' ? '' : viewId}`);
    }
  }

  // 'd' toggles dark mode
  if (e.key === 'd' && !e.ctrlKey && !e.metaKey) {
    const current = store.get('theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', next);
    store.set({ theme: next });
  }
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

renderSidebar(document.getElementById('sidebar'), store, router);
setupDragDrop(store, router);

// Apply saved theme
if (store.get('theme') === 'dark') {
  document.documentElement.classList.add('dark');
}

// Resolve initial route
router.resolve();

// Auto-load from server if served by the viz command (detected by port presence)
if (window.location.port) {
  import('./data-loader.js').then((m) => m.loadFromServer(window.location.origin));
}
