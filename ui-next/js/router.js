// router.js — Hash-based SPA router
// Uses hash fragments for navigation so it works from file:// URLs (no server required).

/**
 * @typedef {{ viewId: string, handler: () => void|Promise<void> }} RouteEntry
 */

export class Router {
  constructor() {
    /** @type {Map<string, RouteEntry>} */
    this.routes = new Map();
    /** @type {string|null} */
    this.currentView = null;
    /** @type {((viewId: string|null) => void)|null} optional hook for cleanup before navigating away */
    this.beforeNavigate = null;
    window.addEventListener('hashchange', () => this.resolve());
  }

  /**
   * Register a route.
   * @param {string} hash   — e.g. '#/dashboard'
   * @param {string} viewId — e.g. 'dashboard'
   * @param {() => void|Promise<void>} handler — called when the route is activated
   * @returns {Router} for chaining
   */
  add(hash, viewId, handler) {
    this.routes.set(hash, { viewId, handler });
    return this;
  }

  /**
   * Programmatically navigate to a hash.
   * @param {string} hash
   */
  navigate(hash) {
    window.location.hash = hash;
  }

  /**
   * Resolve the current hash and invoke the matching route handler.
   * Falls back to the first registered route if no match is found.
   */
  resolve() {
    const hash = window.location.hash || '#/';
    const route = this.routes.get(hash);
    if (route) {
      if (this.beforeNavigate) this.beforeNavigate(this.currentView);
      this.currentView = route.viewId;
      route.handler();
    } else {
      // fallback to first route
      const first = this.routes.entries().next().value;
      if (first) {
        window.location.hash = first[0];
      }
    }
  }
}
