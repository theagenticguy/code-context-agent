// store.js — Global state with observer pattern
// Provides a simple reactive store: set values, subscribe to changes by key or wildcard '*'.

/**
 * @typedef {Record<string, any>} State
 * @typedef {(value: any, state: State) => void} Listener
 */

export class Store {
  /**
   * @param {State} initialState
   */
  constructor(initialState) {
    /** @type {State} */
    this.state = { ...initialState };
    /** @type {Map<string, Set<Listener>>} key -> Set of callbacks */
    this.listeners = new Map();
  }

  /**
   * Read a single key from state.
   * @param {string} key
   * @returns {any}
   */
  get(key) {
    return this.state[key];
  }

  /**
   * Update one or more keys. Only fires listeners for keys whose value actually changed
   * (strict inequality check). Wildcard ('*') listeners fire if anything changed.
   * @param {Record<string, any>} updates
   */
  set(updates) {
    const changed = [];
    for (const [key, value] of Object.entries(updates)) {
      if (this.state[key] !== value) {
        this.state[key] = value;
        changed.push(key);
      }
    }
    // Notify listeners for changed keys
    for (const key of changed) {
      if (this.listeners.has(key)) {
        for (const fn of this.listeners.get(key)) {
          fn(this.state[key], this.state);
        }
      }
    }
    // Notify wildcard listeners
    if (changed.length > 0 && this.listeners.has('*')) {
      for (const fn of this.listeners.get('*')) {
        fn(this.state);
      }
    }
  }

  /**
   * Subscribe to changes on a specific key (or '*' for any change).
   * Returns an unsubscribe function.
   * @param {string} key
   * @param {Listener} fn
   * @returns {() => void} unsubscribe
   */
  on(key, fn) {
    if (!this.listeners.has(key)) this.listeners.set(key, new Set());
    this.listeners.get(key).add(fn);
    return () => this.listeners.get(key)?.delete(fn);
  }

  /**
   * Shallow copy of current state.
   * @returns {State}
   */
  getState() {
    return { ...this.state };
  }
}

// ---------------------------------------------------------------------------
// Singleton store instance
// ---------------------------------------------------------------------------

export const store = new Store({
  // Data artifacts
  graph: null,           // CodeGraph object (from code_graph.json)
  analysisResult: null,  // AnalysisResult object (from analysis_result.json)
  narrative: null,       // string (from CONTEXT.md)
  bundle: null,          // string (from CONTEXT.bundle.md)
  signatures: null,      // string (from CONTEXT.signatures.md)
  filesList: null,       // string (from files.all.txt)

  // UI state
  activeView: 'landing',
  theme: localStorage.getItem('theme') || 'light',
  isLoading: false,
  error: null,

  // Computed (set by data-loader after loading)
  nodeTypes: {},   // Record<string, number>  — counts per node_type
  edgeTypes: {},   // Record<string, number>  — counts per edge_type
});
