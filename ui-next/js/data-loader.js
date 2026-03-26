// data-loader.js — Loads code-context-agent artifacts from files or server
// Handles drag-drop, FileList input, fetch-from-server, and demo data generation.

import { store } from './store.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Count occurrences of each distinct value of `field` across `items`.
 * @param {any[]} items
 * @param {string} field
 * @returns {Record<string, number>}
 */
export function countByField(items, field) {
  const counts = {};
  for (const item of items) {
    const val = item[field] ?? 'unknown';
    counts[val] = (counts[val] || 0) + 1;
  }
  return counts;
}

/**
 * Normalize a raw NetworkX node_link_data JSON blob into a consistent shape.
 *
 * @typedef {{ id: string, name: string, node_type: string, file_path: string, line_start: number, line_end: number, lsp_kind?: number }} GraphNode
 * @typedef {{ source: string, target: string, edge_type: string, weight: number, confidence?: number }} GraphEdge
 * @typedef {{ directed: boolean, multigraph: boolean, graph: object, nodes: GraphNode[], links: GraphEdge[] }} CodeGraph
 *
 * @param {object} raw — the parsed JSON from code_graph.json
 * @returns {CodeGraph}
 */
export function parseGraph(raw) {
  const nodes = (raw.nodes || []).map((n) => ({
    id: String(n.id),
    name: n.name || n.id,
    node_type: n.node_type || 'unknown',
    file_path: n.file_path || '',
    line_start: n.line_start ?? 0,
    line_end: n.line_end ?? 0,
    ...(n.lsp_kind !== undefined ? { lsp_kind: n.lsp_kind } : {}),
  }));

  const links = (raw.links || raw.edges || []).map((e) => ({
    source: String(e.source),
    target: String(e.target),
    edge_type: e.edge_type || e.key || 'unknown',
    weight: e.weight ?? 1,
    ...(e.confidence !== undefined ? { confidence: e.confidence } : {}),
  }));

  return {
    directed: raw.directed ?? true,
    multigraph: raw.multigraph ?? false,
    graph: raw.graph || {},
    nodes,
    links,
  };
}

/**
 * After loading a graph, compute summary counts and push them into the store.
 * @param {CodeGraph} graph
 */
function computeGraphStats(graph) {
  store.set({
    nodeTypes: countByField(graph.nodes, 'node_type'),
    edgeTypes: countByField(graph.links, 'edge_type'),
  });
}

// ---------------------------------------------------------------------------
// File-name -> store-key mapping
// ---------------------------------------------------------------------------

/** @type {Record<string, { key: string, parse: (text: string) => any }>} */
const FILE_MAP = {
  'code_graph.json': {
    key: 'graph',
    parse: (text) => parseGraph(JSON.parse(text)),
  },
  'analysis_result.json': {
    key: 'analysisResult',
    parse: (text) => JSON.parse(text),
  },
  'CONTEXT.md': {
    key: 'narrative',
    parse: (text) => text,
  },
  'CONTEXT.bundle.md': {
    key: 'bundle',
    parse: (text) => text,
  },
  'CONTEXT.signatures.md': {
    key: 'signatures',
    parse: (text) => text,
  },
  'files.all.txt': {
    key: 'filesList',
    parse: (text) => text,
  },
};

// ---------------------------------------------------------------------------
// loadFromFiles — accepts a FileList (from <input> or drop event)
// ---------------------------------------------------------------------------

/**
 * Read recognized files from a FileList and update the store.
 * @param {FileList} fileList
 */
export async function loadFromFiles(fileList) {
  store.set({ isLoading: true, error: null });
  try {
    const promises = [];

    for (const file of fileList) {
      const mapping = FILE_MAP[file.name];
      if (!mapping) continue; // skip unrecognized files

      promises.push(
        file.text().then((text) => {
          const value = mapping.parse(text);
          store.set({ [mapping.key]: value });
          if (mapping.key === 'graph') computeGraphStats(value);
        })
      );
    }

    await Promise.all(promises);
    store.set({ isLoading: false });
  } catch (err) {
    store.set({ isLoading: false, error: `File load error: ${err.message}` });
    console.error('[data-loader] loadFromFiles error:', err);
  }
}

// ---------------------------------------------------------------------------
// loadFromServer — fetch artifacts from the viz-server base URL
// ---------------------------------------------------------------------------

/**
 * Fetch artifacts from the viz server. Silently skips 404s.
 * @param {string} baseUrl — e.g. 'http://localhost:8080'
 */
export async function loadFromServer(baseUrl) {
  store.set({ isLoading: true, error: null });

  const urls = {
    'code_graph.json': `${baseUrl}/data/code_graph.json`,
    'analysis_result.json': `${baseUrl}/data/analysis_result.json`,
    'CONTEXT.md': `${baseUrl}/data/CONTEXT.md`,
    'CONTEXT.bundle.md': `${baseUrl}/data/CONTEXT.bundle.md`,
    'CONTEXT.signatures.md': `${baseUrl}/data/CONTEXT.signatures.md`,
  };

  try {
    const promises = Object.entries(urls).map(async ([fileName, url]) => {
      try {
        const resp = await fetch(url);
        if (!resp.ok) return; // silently skip 404s and other errors
        const text = await resp.text();
        const mapping = FILE_MAP[fileName];
        if (mapping) {
          const value = mapping.parse(text);
          store.set({ [mapping.key]: value });
          if (mapping.key === 'graph') computeGraphStats(value);
        }
      } catch {
        // network errors are silently ignored per-artifact
      }
    });

    await Promise.all(promises);
    store.set({ isLoading: false });
  } catch (err) {
    store.set({ isLoading: false, error: `Server load error: ${err.message}` });
    console.error('[data-loader] loadFromServer error:', err);
  }
}

// ---------------------------------------------------------------------------
// loadDemoData — generates a small sample graph for demo/testing
// ---------------------------------------------------------------------------

/**
 * Populate the store with synthetic demo data (~20 nodes, ~30 edges, minimal analysis).
 */
export function loadDemoData() {
  store.set({ isLoading: true, error: null });

  // --- Nodes ---
  const nodes = [
    // modules
    { id: 'mod:app', name: 'app', node_type: 'module', file_path: 'app/__init__.py', line_start: 1, line_end: 5 },
    { id: 'mod:auth', name: 'auth', node_type: 'module', file_path: 'app/auth/__init__.py', line_start: 1, line_end: 3 },
    { id: 'mod:db', name: 'db', node_type: 'module', file_path: 'app/db/__init__.py', line_start: 1, line_end: 3 },
    // files
    { id: 'file:main.py', name: 'main.py', node_type: 'file', file_path: 'app/main.py', line_start: 1, line_end: 120 },
    { id: 'file:models.py', name: 'models.py', node_type: 'file', file_path: 'app/models.py', line_start: 1, line_end: 95 },
    { id: 'file:auth.py', name: 'auth.py', node_type: 'file', file_path: 'app/auth/auth.py', line_start: 1, line_end: 80 },
    { id: 'file:db.py', name: 'db.py', node_type: 'file', file_path: 'app/db/db.py', line_start: 1, line_end: 60 },
    // classes
    { id: 'cls:User', name: 'User', node_type: 'class', file_path: 'app/models.py', line_start: 10, line_end: 45 },
    { id: 'cls:Session', name: 'Session', node_type: 'class', file_path: 'app/models.py', line_start: 48, line_end: 75 },
    { id: 'cls:AuthProvider', name: 'AuthProvider', node_type: 'class', file_path: 'app/auth/auth.py', line_start: 5, line_end: 60 },
    // functions
    { id: 'fn:main', name: 'main', node_type: 'function', file_path: 'app/main.py', line_start: 10, line_end: 35 },
    { id: 'fn:create_app', name: 'create_app', node_type: 'function', file_path: 'app/main.py', line_start: 38, line_end: 65 },
    { id: 'fn:get_db', name: 'get_db', node_type: 'function', file_path: 'app/db/db.py', line_start: 8, line_end: 20 },
    { id: 'fn:migrate', name: 'migrate', node_type: 'function', file_path: 'app/db/db.py', line_start: 22, line_end: 50 },
    // methods
    { id: 'meth:User.save', name: 'User.save', node_type: 'method', file_path: 'app/models.py', line_start: 30, line_end: 40 },
    { id: 'meth:User.validate', name: 'User.validate', node_type: 'method', file_path: 'app/models.py', line_start: 20, line_end: 28 },
    { id: 'meth:AuthProvider.login', name: 'AuthProvider.login', node_type: 'method', file_path: 'app/auth/auth.py', line_start: 15, line_end: 40 },
    { id: 'meth:Session.refresh', name: 'Session.refresh', node_type: 'method', file_path: 'app/models.py', line_start: 55, line_end: 70 },
    // variables
    { id: 'var:DB_URL', name: 'DB_URL', node_type: 'variable', file_path: 'app/db/db.py', line_start: 3, line_end: 3 },
    { id: 'var:SECRET_KEY', name: 'SECRET_KEY', node_type: 'variable', file_path: 'app/auth/auth.py', line_start: 3, line_end: 3 },
    // pattern_match
    { id: 'pat:singleton_db', name: 'Singleton (DB)', node_type: 'pattern_match', file_path: 'app/db/db.py', line_start: 8, line_end: 20 },
  ];

  // --- Edges ---
  const links = [
    // imports
    { source: 'file:main.py', target: 'mod:auth', edge_type: 'imports', weight: 1 },
    { source: 'file:main.py', target: 'mod:db', edge_type: 'imports', weight: 1 },
    { source: 'file:auth.py', target: 'file:models.py', edge_type: 'imports', weight: 1 },
    { source: 'file:db.py', target: 'file:models.py', edge_type: 'imports', weight: 1 },
    // contains
    { source: 'mod:app', target: 'file:main.py', edge_type: 'contains', weight: 1 },
    { source: 'mod:app', target: 'file:models.py', edge_type: 'contains', weight: 1 },
    { source: 'mod:auth', target: 'file:auth.py', edge_type: 'contains', weight: 1 },
    { source: 'mod:db', target: 'file:db.py', edge_type: 'contains', weight: 1 },
    { source: 'file:models.py', target: 'cls:User', edge_type: 'contains', weight: 1 },
    { source: 'file:models.py', target: 'cls:Session', edge_type: 'contains', weight: 1 },
    { source: 'file:auth.py', target: 'cls:AuthProvider', edge_type: 'contains', weight: 1 },
    { source: 'file:main.py', target: 'fn:main', edge_type: 'contains', weight: 1 },
    { source: 'file:main.py', target: 'fn:create_app', edge_type: 'contains', weight: 1 },
    { source: 'file:db.py', target: 'fn:get_db', edge_type: 'contains', weight: 1 },
    { source: 'file:db.py', target: 'fn:migrate', edge_type: 'contains', weight: 1 },
    { source: 'cls:User', target: 'meth:User.save', edge_type: 'contains', weight: 1 },
    { source: 'cls:User', target: 'meth:User.validate', edge_type: 'contains', weight: 1 },
    { source: 'cls:AuthProvider', target: 'meth:AuthProvider.login', edge_type: 'contains', weight: 1 },
    { source: 'cls:Session', target: 'meth:Session.refresh', edge_type: 'contains', weight: 1 },
    // calls
    { source: 'fn:main', target: 'fn:create_app', edge_type: 'calls', weight: 1 },
    { source: 'fn:create_app', target: 'fn:get_db', edge_type: 'calls', weight: 1 },
    { source: 'meth:AuthProvider.login', target: 'meth:User.validate', edge_type: 'calls', weight: 1 },
    { source: 'meth:User.save', target: 'fn:get_db', edge_type: 'calls', weight: 2 },
    { source: 'fn:migrate', target: 'fn:get_db', edge_type: 'calls', weight: 1 },
    { source: 'meth:AuthProvider.login', target: 'meth:Session.refresh', edge_type: 'calls', weight: 1 },
    // references
    { source: 'fn:get_db', target: 'var:DB_URL', edge_type: 'references', weight: 1 },
    { source: 'meth:AuthProvider.login', target: 'var:SECRET_KEY', edge_type: 'references', weight: 1 },
    { source: 'fn:create_app', target: 'cls:AuthProvider', edge_type: 'references', weight: 1 },
    // inherits
    { source: 'cls:Session', target: 'cls:User', edge_type: 'inherits', weight: 1 },
    // pattern
    { source: 'pat:singleton_db', target: 'fn:get_db', edge_type: 'references', weight: 1, confidence: 0.85 },
  ];

  const graph = {
    directed: true,
    multigraph: false,
    graph: {},
    nodes,
    links,
  };

  // --- Minimal AnalysisResult ---
  const analysisResult = {
    status: 'completed',
    summary: 'Demo analysis of a small web application with authentication and database layers.',
    total_files_analyzed: 4,
    business_logic_items: [
      { name: 'User Authentication', description: 'Login flow validates credentials and creates sessions.', file_path: 'app/auth/auth.py', confidence: 0.92 },
      { name: 'Data Persistence', description: 'User model manages saving and validation against the database.', file_path: 'app/models.py', confidence: 0.88 },
      { name: 'Session Management', description: 'Sessions are refreshed on activity and tied to user accounts.', file_path: 'app/models.py', confidence: 0.80 },
    ],
    risks: [
      { title: 'Singleton DB Connection', description: 'get_db uses a module-level singleton that may cause connection pool exhaustion under concurrency.', severity: 'high', file_path: 'app/db/db.py', line: 8 },
      { title: 'Hardcoded Secret Key', description: 'SECRET_KEY is defined as a variable instead of being loaded from environment.', severity: 'critical', file_path: 'app/auth/auth.py', line: 3 },
    ],
    generated_files: [
      { name: 'CONTEXT.md', description: 'Narrative context document' },
      { name: 'CONTEXT.bundle.md', description: 'Bundled context for LLMs' },
    ],
    graph_stats: {
      total_nodes: nodes.length,
      total_edges: links.length,
      connected_components: 1,
    },
    refactoring_candidates: [
      { name: 'Extract DB configuration', description: 'Move DB_URL and connection setup to a dedicated config module.', file_path: 'app/db/db.py', priority: 'medium' },
      { name: 'AuthProvider method size', description: 'AuthProvider.login is 25 lines and handles validation, session creation, and logging. Split into smaller methods.', file_path: 'app/auth/auth.py', priority: 'low' },
    ],
    code_health: {
      overall_score: 72,
      maintainability: 68,
      complexity: 45,
      test_coverage: null,
    },
    analysis_mode: 'demo',
    phase_timings: [
      { phase: 'graph_construction', duration_ms: 0 },
      { phase: 'analysis', duration_ms: 0 },
    ],
  };

  const narrative = `# Demo Application Context

This is a small web application with three main modules:

- **app** — the main application entry point
- **auth** — authentication and session management
- **db** — database access layer

## Key Flows

1. \`main()\` calls \`create_app()\` which initializes the DB and auth providers.
2. \`AuthProvider.login()\` validates user credentials and refreshes sessions.
3. \`User.save()\` persists user data through \`get_db()\`.

## Concerns

The singleton database pattern in \`get_db\` and the hardcoded \`SECRET_KEY\` are the two highest-priority issues.
`;

  store.set({
    graph,
    analysisResult,
    narrative,
    bundle: '# Demo Bundle\n\nThis is a demo bundle combining all context.',
    signatures: '# Demo Signatures\n\n```python\ndef main() -> None: ...\ndef create_app() -> App: ...\nclass User:\n    def save(self) -> bool: ...\n    def validate(self) -> bool: ...\n```',
    isLoading: false,
  });

  computeGraphStats(graph);
}

// ---------------------------------------------------------------------------
// Drag-and-drop setup
// ---------------------------------------------------------------------------

/**
 * Wire up document-level drag-and-drop. Shows a visual overlay on dragover,
 * loads recognized files on drop.
 *
 * @param {import('./store.js').Store} _store — the store instance (for potential future use)
 * @param {import('./router.js').Router} router — router to navigate after loading
 */
export function setupDragDrop(_store, router) {
  let dragCounter = 0;

  // Create overlay element (hidden by default)
  const overlay = document.createElement('div');
  overlay.id = 'drop-overlay';
  overlay.innerHTML = '<div class="drop-overlay-content">Drop files to load</div>';
  overlay.style.cssText = `
    position: fixed; inset: 0; z-index: 9999;
    display: none; place-items: center;
    background: rgba(0,0,0,0.45);
    backdrop-filter: blur(4px);
  `;
  overlay.querySelector('.drop-overlay-content').style.cssText = `
    padding: 2rem 3rem; border-radius: 1rem;
    border: 3px dashed rgba(255,255,255,0.6);
    color: white; font-size: 1.5rem; font-weight: 600;
    pointer-events: none;
  `;
  document.body.appendChild(overlay);

  const show = () => { overlay.style.display = 'grid'; };
  const hide = () => { overlay.style.display = 'none'; dragCounter = 0; };

  document.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragCounter++;
    if (dragCounter === 1) show();
  });

  document.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter <= 0) hide();
  });

  document.addEventListener('dragover', (e) => {
    e.preventDefault(); // required to allow drop
  });

  document.addEventListener('drop', async (e) => {
    e.preventDefault();
    hide();
    if (e.dataTransfer?.files?.length) {
      await loadFromFiles(e.dataTransfer.files);
      // Navigate to dashboard if we loaded a graph
      if (store.get('graph')) {
        router.navigate('#/dashboard');
      }
    }
  });
}
