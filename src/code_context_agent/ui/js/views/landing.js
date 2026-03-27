// landing.js — Landing/home view
// Welcoming page with file loading, server connection, and demo data options.

import { loadFromFiles, loadDemoData, loadFromServer } from '../data-loader.js';
import { store } from '../store.js';

// ---------------------------------------------------------------------------
// Accepted file names
// ---------------------------------------------------------------------------

const ACCEPTED_FILES = [
  'code_graph.json',
  'analysis_result.json',
  'CONTEXT.md',
  'CONTEXT.bundle.md',
  'CONTEXT.signatures.md',
];

// ---------------------------------------------------------------------------
// Keyboard shortcuts reference data
// ---------------------------------------------------------------------------

const SHORTCUTS = [
  { keys: ['1'], desc: 'Home' },
  { keys: ['2'], desc: 'Dashboard' },
  { keys: ['3'], desc: 'Graph' },
  { keys: ['4'], desc: 'Modules' },
  { keys: ['5'], desc: 'Hotspots' },
  { keys: ['6'], desc: 'Dependencies' },
  { keys: ['7'], desc: 'Narrative' },
  { keys: ['8'], desc: 'Bundles' },
  { keys: ['9'], desc: 'Insights' },
  { keys: ['0'], desc: 'Signatures' },
  { keys: ['D'], desc: 'Toggle dark mode' },
];

// ---------------------------------------------------------------------------
// render
// ---------------------------------------------------------------------------

/**
 * Render the landing view into the given container.
 * @param {HTMLElement} container
 * @param {import('../store.js').Store} _store
 * @returns {() => void} cleanup function
 */
export function render(container, _store) {
  // -- Build HTML ----------------------------------------------------------

  // nosemgrep: javascript.browser.security.insecure-document-method.insecure-document-method — all interpolated values are hardcoded constants (ACCEPTED_FILES, SHORTCUTS) defined in this module
  container.innerHTML = `
    <div class="view-enter h-full overflow-auto bg-bg">
      <div class="max-w-3xl mx-auto px-6 py-16 font-base text-fg">

        <!-- Hero -->
        <header class="text-center mb-14">
          <h1 class="font-heading text-5xl tracking-tight leading-tight">
            Code Context Agent
          </h1>
          <p class="text-lg text-fg/60 mt-3 font-base">
            Visualize your codebase knowledge graph
          </p>
        </header>

        <!-- Action cards -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-10">

          <!-- Load Files -->
          <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-6 flex flex-col items-center text-center gap-4">
            <span class="text-3xl leading-none">\u{1F4C2}</span>
            <h2 class="font-heading text-lg">Load Files</h2>
            <p class="text-sm text-fg/60">
              Pick <code class="text-xs bg-bg px-1 py-0.5 rounded border border-border/40">.json</code> or
              <code class="text-xs bg-bg px-1 py-0.5 rounded border border-border/40">.md</code> artifacts from disk.
            </p>
            <label class="neo-pressable cursor-pointer inline-flex items-center gap-2 px-4 py-2 rounded-base border-2 border-border bg-main text-main-fg font-heading text-sm select-none">
              Choose files
              <input id="landing-file-input" type="file" multiple
                     accept=".json,.md,.txt"
                     class="hidden" />
            </label>
          </div>

          <!-- Connect to Server -->
          <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-6 flex flex-col items-center text-center gap-4">
            <span class="text-3xl leading-none">\u{1F310}</span>
            <h2 class="font-heading text-lg">Connect to Server</h2>
            <p class="text-sm text-fg/60">
              Fetch artifacts from a running viz&nbsp;server.
            </p>
            <div class="flex flex-col gap-2 w-full">
              <input id="landing-server-url" type="text"
                     placeholder="http://localhost:8080"
                     class="w-full px-3 py-1.5 text-sm rounded-base border-2 border-border bg-bg text-fg font-base placeholder:text-fg/30 neo-focus" />
              <button id="landing-connect-btn"
                      class="neo-pressable w-full px-4 py-2 rounded-base border-2 border-border bg-main text-main-fg font-heading text-sm">
                Connect
              </button>
            </div>
          </div>

          <!-- Try Demo -->
          <div class="rounded-base border-2 border-border shadow-neo bg-bg2 p-6 flex flex-col items-center text-center gap-4">
            <span class="text-3xl leading-none">\u{1F9EA}</span>
            <h2 class="font-heading text-lg">Try Demo</h2>
            <p class="text-sm text-fg/60">
              Load a synthetic sample graph to explore the UI.
            </p>
            <button id="landing-demo-btn"
                    class="neo-pressable px-4 py-2 rounded-base border-2 border-border bg-main text-main-fg font-heading text-sm">
              Load Demo Data
            </button>
          </div>

        </div>

        <!-- Drag-drop hint -->
        <p class="text-center text-sm text-fg/40 mb-8">
          or drag and drop <code class="text-xs bg-bg2 px-1 py-0.5 rounded border border-border/30">.code-context</code> files anywhere
        </p>

        <!-- Accepted files list -->
        <div class="rounded-base border-2 border-border bg-bg2 px-5 py-4 mb-12">
          <h3 class="font-heading text-sm mb-2 text-fg/70">Accepted files</h3>
          <ul class="flex flex-wrap gap-2">
            ${ACCEPTED_FILES.map(
              (f) =>
                `<li class="text-xs font-mono px-2 py-1 rounded-base border border-border/40 bg-bg text-fg/70">${f}</li>`
            ).join('')}
          </ul>
        </div>

        <!-- Keyboard shortcuts -->
        <div class="rounded-base border-2 border-border bg-bg2 px-5 py-4">
          <h3 class="font-heading text-sm mb-3 text-fg/70">Keyboard shortcuts</h3>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1.5">
            ${SHORTCUTS.map(
              (s) => `
              <div class="flex items-center gap-2 text-xs text-fg/60">
                <span class="flex gap-0.5">
                  ${s.keys
                    .map(
                      (k) =>
                        `<kbd class="inline-block min-w-[20px] text-center px-1 py-0.5 rounded border border-border/40 bg-bg font-mono text-[10px] leading-none">${k}</kbd>`
                    )
                    .join('')}
                </span>
                <span>${s.desc}</span>
              </div>`
            ).join('')}
          </div>
        </div>

      </div>
    </div>`;

  // -- Wire up event listeners ---------------------------------------------

  const fileInput = container.querySelector('#landing-file-input');
  const connectBtn = container.querySelector('#landing-connect-btn');
  const serverUrlInput = container.querySelector('#landing-server-url');
  const demoBtn = container.querySelector('#landing-demo-btn');

  /** @type {AbortController} */
  const ac = new AbortController();
  const signal = ac.signal;

  // File input change
  fileInput.addEventListener(
    'change',
    async (e) => {
      if (e.target.files?.length) {
        await loadFromFiles(e.target.files);
        if (store.get('graph')) {
          window.location.hash = '#/dashboard';
        }
      }
    },
    { signal }
  );

  // Connect to server
  connectBtn.addEventListener(
    'click',
    async () => {
      const url = serverUrlInput.value.trim();
      if (!url) {
        serverUrlInput.focus();
        return;
      }
      await loadFromServer(url);
      if (store.get('graph')) {
        window.location.hash = '#/dashboard';
      }
    },
    { signal }
  );

  // Allow pressing Enter in the URL input to trigger connect
  serverUrlInput.addEventListener(
    'keydown',
    (e) => {
      if (e.key === 'Enter') {
        connectBtn.click();
      }
    },
    { signal }
  );

  // Demo button
  demoBtn.addEventListener(
    'click',
    () => {
      loadDemoData();
      window.location.hash = '#/dashboard';
    },
    { signal }
  );

  // -- Cleanup -------------------------------------------------------------

  return () => {
    ac.abort();
  };
}
