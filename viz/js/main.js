/**
 * Main application controller — data loading, routing, and view management.
 */
import { state, parseGraphData, computeCaches } from './state.js';
import { renderDashboard } from './dashboard.js';
import { initGraph, destroyGraph } from './graph.js';
import { renderModules } from './modules.js';
import { renderHotspots } from './hotspots.js';
import { renderDependencies } from './dependencies.js';
import { renderNarrative } from './narrative.js';

// ── Routing ──────────────────────────────────────────────────────
const views = ['landing', 'dashboard', 'graph', 'modules', 'hotspots', 'dependencies', 'narrative'];

function switchView(name) {
  if (!views.includes(name)) return;

  // Don't switch to data views if no data loaded
  if (name !== 'landing' && !state.graph && !state.narrative && !state.analysisResult) {
    toast('Load data first', 'info');
    return;
  }

  state.activeView = name;

  // Hide all views, show target
  views.forEach(v => {
    const el = document.getElementById(`view-${v}`);
    if (el) el.classList.toggle('active', v === name);
  });

  // Update nav
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === name);
  });

  // Render view
  switch (name) {
    case 'dashboard': renderDashboard(); break;
    case 'graph':
      destroyGraph();
      requestAnimationFrame(() => initGraph());
      break;
    case 'modules': renderModules(); break;
    case 'hotspots': renderHotspots(); break;
    case 'dependencies': renderDependencies(); break;
    case 'narrative': renderNarrative(); break;
  }
}

// ── Data Loading ─────────────────────────────────────────────────
async function loadFiles(files) {
  let loaded = 0;

  for (const file of files) {
    const name = file.name.toLowerCase();
    const text = await file.text();

    if (name === 'code_graph.json') {
      try {
        const raw = JSON.parse(text);
        state.graph = parseGraphData(raw);
        computeCaches();
        loaded++;
        toast(`Loaded graph: ${state.graph.nodes.length} nodes, ${state.graph.links.length} edges`, 'success');
      } catch (e) {
        toast(`Failed to parse code_graph.json: ${e.message}`, 'error');
      }
    } else if (name === 'analysis_result.json') {
      try {
        state.analysisResult = JSON.parse(text);
        loaded++;
        toast('Loaded analysis result', 'success');
      } catch (e) {
        toast(`Failed to parse analysis_result.json: ${e.message}`, 'error');
      }
    } else if (name === 'context.md' || name.endsWith('context.md')) {
      state.narrative = text;
      loaded++;
      toast('Loaded CONTEXT.md', 'success');
    }
  }

  if (loaded > 0) {
    switchView('dashboard');
  }
}

// ── Demo Data ────────────────────────────────────────────────────
function loadDemoData() {
  const nodes = [];
  const links = [];

  // Generate a realistic-looking code graph
  const modules = [
    { prefix: 'src/auth', funcs: ['login', 'logout', 'verify_token', 'refresh_session', 'hash_password', 'check_permissions'], classes: ['AuthService', 'TokenManager'] },
    { prefix: 'src/api', funcs: ['get_users', 'create_user', 'update_user', 'delete_user', 'list_orders', 'create_order'], classes: ['UserRouter', 'OrderRouter', 'APIMiddleware'] },
    { prefix: 'src/db', funcs: ['connect', 'query', 'execute', 'begin_transaction', 'commit', 'rollback'], classes: ['DatabasePool', 'QueryBuilder', 'Migration'] },
    { prefix: 'src/models', funcs: [], classes: ['User', 'Order', 'Product', 'Session', 'AuditLog'] },
    { prefix: 'src/services', funcs: ['send_email', 'process_payment', 'generate_report', 'schedule_job', 'validate_input'], classes: ['EmailService', 'PaymentGateway', 'ReportEngine'] },
    { prefix: 'src/utils', funcs: ['format_date', 'parse_json', 'sanitize_html', 'generate_id', 'calculate_hash'], classes: ['Logger', 'Cache'] },
    { prefix: 'tests', funcs: ['test_login', 'test_create_user', 'test_payment', 'test_query', 'test_email'], classes: ['TestAuth', 'TestAPI'] },
  ];

  let line = 1;
  for (const mod of modules) {
    // File nodes
    nodes.push({
      id: `${mod.prefix}/__init__.py:L1`,
      name: mod.prefix.split('/').pop(),
      node_type: 'file',
      file_path: `${mod.prefix}/__init__.py`,
      line_start: 1,
      line_end: 50,
    });

    // Class nodes
    for (const cls of mod.classes) {
      const id = `${mod.prefix}/${cls.toLowerCase()}.py:${cls}:${line}`;
      nodes.push({
        id,
        name: cls,
        node_type: 'class',
        file_path: `${mod.prefix}/${cls.toLowerCase()}.py`,
        line_start: line,
        line_end: line + 40,
        category: mod.prefix.includes('auth') ? 'auth'
          : mod.prefix.includes('db') ? 'db'
          : mod.prefix.includes('api') ? 'http'
          : mod.prefix.includes('services') ? 'integrations'
          : null,
      });
      // Contains edge from file
      links.push({
        source: `${mod.prefix}/__init__.py:L1`,
        target: id,
        edge_type: 'contains',
        weight: 1,
      });
      line += 45;
    }

    // Function nodes
    for (const fn of mod.funcs) {
      const id = `${mod.prefix}/functions.py:${fn}:${line}`;
      nodes.push({
        id,
        name: fn,
        node_type: 'function',
        file_path: `${mod.prefix}/functions.py`,
        line_start: line,
        line_end: line + 15,
        category: mod.prefix.includes('auth') ? 'auth'
          : mod.prefix.includes('db') ? 'db'
          : mod.prefix.includes('api') ? 'http'
          : mod.prefix.includes('services') ? 'integrations'
          : mod.prefix.includes('utils') ? 'validation'
          : null,
      });
      links.push({
        source: `${mod.prefix}/__init__.py:L1`,
        target: id,
        edge_type: 'contains',
        weight: 1,
      });
      line += 18;
    }
  }

  // Cross-module relationships
  const addCall = (fromName, toName) => {
    const from = nodes.find(n => n.name === fromName);
    const to = nodes.find(n => n.name === toName);
    if (from && to) links.push({ source: from.id, target: to.id, edge_type: 'calls', weight: 1 });
  };

  const addImport = (fromName, toName) => {
    const from = nodes.find(n => n.name === fromName);
    const to = nodes.find(n => n.name === toName);
    if (from && to) links.push({ source: from.id, target: to.id, edge_type: 'imports', weight: 1 });
  };

  const addInherit = (fromName, toName) => {
    const from = nodes.find(n => n.name === fromName);
    const to = nodes.find(n => n.name === toName);
    if (from && to) links.push({ source: from.id, target: to.id, edge_type: 'inherits', weight: 1 });
  };

  const addTest = (fromName, toName) => {
    const from = nodes.find(n => n.name === fromName);
    const to = nodes.find(n => n.name === toName);
    if (from && to) links.push({ source: from.id, target: to.id, edge_type: 'tests', weight: 1 });
  };

  // API -> Auth
  addCall('get_users', 'verify_token');
  addCall('create_user', 'verify_token');
  addCall('create_user', 'hash_password');
  addCall('update_user', 'check_permissions');
  addCall('delete_user', 'check_permissions');
  addCall('create_order', 'verify_token');
  addImport('UserRouter', 'AuthService');
  addImport('OrderRouter', 'AuthService');
  addImport('APIMiddleware', 'TokenManager');

  // API -> DB
  addCall('get_users', 'query');
  addCall('create_user', 'execute');
  addCall('update_user', 'execute');
  addCall('delete_user', 'execute');
  addCall('list_orders', 'query');
  addCall('create_order', 'begin_transaction');
  addImport('UserRouter', 'DatabasePool');
  addImport('OrderRouter', 'QueryBuilder');

  // API -> Models
  addImport('UserRouter', 'User');
  addImport('OrderRouter', 'Order');
  addImport('OrderRouter', 'Product');

  // Auth -> DB
  addCall('login', 'query');
  addCall('verify_token', 'query');
  addCall('refresh_session', 'execute');
  addImport('AuthService', 'DatabasePool');

  // Services -> various
  addCall('process_payment', 'begin_transaction');
  addCall('process_payment', 'commit');
  addCall('generate_report', 'query');
  addCall('send_email', 'format_date');
  addCall('validate_input', 'sanitize_html');
  addImport('PaymentGateway', 'DatabasePool');
  addImport('ReportEngine', 'QueryBuilder');
  addImport('EmailService', 'Logger');

  // Utils used everywhere
  addCall('login', 'calculate_hash');
  addCall('hash_password', 'calculate_hash');
  addCall('create_user', 'generate_id');
  addCall('create_order', 'generate_id');
  addCall('verify_token', 'parse_json');

  // Inheritance
  addInherit('UserRouter', 'APIMiddleware');
  addInherit('OrderRouter', 'APIMiddleware');

  // Tests
  addTest('test_login', 'login');
  addTest('test_create_user', 'create_user');
  addTest('test_payment', 'process_payment');
  addTest('test_query', 'query');
  addTest('test_email', 'send_email');
  addTest('TestAuth', 'AuthService');
  addTest('TestAPI', 'UserRouter');

  // Co-changes
  const addCochange = (fromName, toName) => {
    const from = nodes.find(n => n.name === fromName);
    const to = nodes.find(n => n.name === toName);
    if (from && to) links.push({ source: from.id, target: to.id, edge_type: 'cochanges', weight: 3 });
  };
  addCochange('login', 'verify_token');
  addCochange('create_user', 'User');
  addCochange('create_order', 'Order');
  addCochange('DatabasePool', 'Migration');

  // References
  const addRef = (fromName, toName) => {
    const from = nodes.find(n => n.name === fromName);
    const to = nodes.find(n => n.name === toName);
    if (from && to) links.push({ source: from.id, target: to.id, edge_type: 'references', weight: 1 });
  };
  addRef('User', 'Session');
  addRef('Order', 'Product');
  addRef('Order', 'User');
  addRef('AuditLog', 'User');
  addRef('Session', 'TokenManager');
  addRef('Cache', 'Logger');

  const graphData = { nodes, links, directed: true, multigraph: true, graph: {} };

  // Analysis result
  state.analysisResult = {
    status: 'completed',
    summary: 'A Python web application with authentication, user management, order processing, and payment integration. Core architecture follows a layered pattern with API routes, services, models, and database access.',
    total_files_analyzed: 42,
    business_logic_items: [
      { rank: 1, name: 'login', role: 'User authentication entry point', location: 'src/auth/functions.py:1', score: 0.92, category: 'auth' },
      { rank: 2, name: 'create_order', role: 'Order creation with transaction', location: 'src/api/functions.py:91', score: 0.87, category: 'workflows' },
      { rank: 3, name: 'process_payment', role: 'Payment processing', location: 'src/services/functions.py:28', score: 0.83, category: 'integrations' },
      { rank: 4, name: 'verify_token', role: 'JWT token verification', location: 'src/auth/functions.py:46', score: 0.79, category: 'auth' },
      { rank: 5, name: 'create_user', role: 'User registration', location: 'src/api/functions.py:19', score: 0.75, category: 'workflows' },
      { rank: 6, name: 'query', role: 'Database query execution', location: 'src/db/functions.py:19', score: 0.71, category: 'db' },
      { rank: 7, name: 'generate_report', role: 'Report generation', location: 'src/services/functions.py:46', score: 0.65, category: 'integrations' },
      { rank: 8, name: 'validate_input', role: 'Input sanitization', location: 'src/services/functions.py:64', score: 0.60, category: 'validation' },
    ],
    risks: [
      { description: 'DatabasePool is a single point of failure with no connection pooling fallback', severity: 'high', location: 'src/db/DatabasePool', mitigation: 'Add connection pool redundancy and circuit breaker pattern' },
      { description: 'Token verification queries DB on every request — potential performance bottleneck', severity: 'medium', location: 'src/auth/verify_token', mitigation: 'Cache verified tokens with short TTL' },
      { description: 'No rate limiting on authentication endpoints', severity: 'medium', location: 'src/auth/login', mitigation: 'Add rate limiter middleware' },
      { description: 'payment processing lacks idempotency keys', severity: 'high', location: 'src/services/process_payment', mitigation: 'Add idempotency key parameter and dedup logic' },
      { description: 'Test coverage gap for order deletion flow', severity: 'low', location: 'tests/', mitigation: 'Add test_delete_order with cascade verification' },
    ],
    generated_files: [
      { path: 'CONTEXT.md', line_count: 280, description: 'Main narrated context' },
      { path: 'CONTEXT.bundle.md', line_count: 1200, description: 'Compressed source bundle' },
      { path: 'code_graph.json', line_count: 450, description: 'Code graph data' },
    ],
    graph_stats: {
      node_count: nodes.length,
      edge_count: links.length,
      module_count: 7,
      hotspot_count: 5,
    },
  };

  // Demo narrative
  state.narrative = `# E-Commerce Platform Context

## Summary

This is a Python web application implementing an e-commerce platform with user authentication,
order management, and payment processing. The codebase follows a layered architecture with clear
separation between API routes, business services, data models, and database access.

## Architecture

\`\`\`mermaid
graph TD
    A[API Layer] --> B[Auth Service]
    A --> C[Database Layer]
    A --> D[Models]
    E[Services] --> C
    E --> F[Utils]
    B --> C
    G[Tests] -.-> A
    G -.-> B
    G -.-> E
\`\`\`

## Key Components

### Authentication (\`src/auth/\`)

The auth module handles JWT-based authentication with password hashing via \`hash_password\`
and token verification through \`verify_token\`. The \`AuthService\` class coordinates login
flows and session management.

### API Routes (\`src/api/\`)

RESTful endpoints for user and order CRUD operations. Both \`UserRouter\` and \`OrderRouter\`
inherit from \`APIMiddleware\` for shared request validation.

### Database (\`src/db/\`)

Connection pooling via \`DatabasePool\` with \`QueryBuilder\` for safe SQL construction.
Transaction support through \`begin_transaction\`/\`commit\`/\`rollback\`.

### Services (\`src/services/\`)

Business logic for payments (\`PaymentGateway\`), email (\`EmailService\`), and
reporting (\`ReportEngine\`).

## Business Logic Rankings

| Rank | Name | Role | Score |
|------|------|------|-------|
| 1 | \`login\` | User authentication entry point | 0.92 |
| 2 | \`create_order\` | Order creation with transaction | 0.87 |
| 3 | \`process_payment\` | Payment processing | 0.83 |
| 4 | \`verify_token\` | JWT token verification | 0.79 |
| 5 | \`create_user\` | User registration | 0.75 |

## Risks

> **High**: DatabasePool is a single point of failure with no connection pooling fallback

> **High**: Payment processing lacks idempotency keys

> **Medium**: Token verification queries DB on every request

## Conventions

- All API routes require authentication via \`verify_token\`
- Database operations use \`QueryBuilder\` — no raw SQL
- Input validation happens in \`validate_input\` before any DB write
- Tests follow \`test_<function_name>\` naming convention
`;

  state.graph = parseGraphData(graphData);
  computeCaches();
  toast(`Demo loaded: ${state.graph.nodes.length} nodes, ${state.graph.links.length} edges`, 'success');
  switchView('dashboard');
}

// ── Event Bindings ───────────────────────────────────────────────
function init() {
  // Nav clicks
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => switchView(item.dataset.view));
  });

  // Load buttons
  document.getElementById('btn-load').addEventListener('click', () => {
    document.getElementById('file-input').click();
  });

  document.getElementById('btn-load-files').addEventListener('click', () => {
    document.getElementById('file-input').click();
  });

  document.getElementById('btn-load-dir').addEventListener('click', () => {
    document.getElementById('dir-input').click();
  });

  document.getElementById('btn-load-demo').addEventListener('click', loadDemoData);

  // File inputs
  document.getElementById('file-input').addEventListener('change', (e) => {
    if (e.target.files.length > 0) loadFiles(e.target.files);
  });

  document.getElementById('dir-input').addEventListener('change', (e) => {
    if (e.target.files.length > 0) loadFiles(e.target.files);
  });

  // Drag and drop
  const dropZone = document.getElementById('drop-zone');

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');

    const files = [];
    if (e.dataTransfer.items) {
      for (const item of e.dataTransfer.items) {
        if (item.kind === 'file') files.push(item.getAsFile());
      }
    } else {
      for (const file of e.dataTransfer.files) {
        files.push(file);
      }
    }

    if (files.length > 0) loadFiles(files);
  });

  // URL params: ?graph=path&narrative=path&result=path
  const params = new URLSearchParams(window.location.search);
  const graphUrl = params.get('graph');
  const narrativeUrl = params.get('narrative');
  const resultUrl = params.get('result');

  if (graphUrl || narrativeUrl || resultUrl) {
    loadFromUrls(graphUrl, narrativeUrl, resultUrl);
  }

  // Keyboard shortcut: 1-6 for views
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    const viewMap = { '1': 'dashboard', '2': 'graph', '3': 'modules', '4': 'hotspots', '5': 'dependencies', '6': 'narrative' };
    if (viewMap[e.key]) switchView(viewMap[e.key]);
  });
}

async function loadFromUrls(graphUrl, narrativeUrl, resultUrl) {
  const fetches = [];

  if (graphUrl) {
    fetches.push(
      fetch(graphUrl)
        .then(r => r.json())
        .then(raw => {
          state.graph = parseGraphData(raw);
          computeCaches();
          toast(`Loaded graph from URL`, 'success');
        })
        .catch(e => toast(`Failed to load graph: ${e.message}`, 'error'))
    );
  }

  if (narrativeUrl) {
    fetches.push(
      fetch(narrativeUrl)
        .then(r => r.text())
        .then(text => {
          state.narrative = text;
          toast('Loaded narrative from URL', 'success');
        })
        .catch(e => toast(`Failed to load narrative: ${e.message}`, 'error'))
    );
  }

  if (resultUrl) {
    fetches.push(
      fetch(resultUrl)
        .then(r => r.json())
        .then(data => {
          state.analysisResult = data;
          toast('Loaded analysis result from URL', 'success');
        })
        .catch(e => toast(`Failed to load result: ${e.message}`, 'error'))
    );
  }

  await Promise.all(fetches);

  if (state.graph || state.narrative || state.analysisResult) {
    switchView('dashboard');
  }
}

// ── Toast Notifications ──────────────────────────────────────────
function toast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// Boot
init();
