/* Wizards Engine — Navigation component
 *
 * Renders the tab navigation bar (mobile bottom bar / desktop top bar).
 * Registers itself at window.components.nav.
 *
 * Usage: call window.components.nav.mount() after Alpine has initialised.
 * The component mounts into the #nav-container element in index.html.
 *
 * Tab sets:
 *   Player: Feed (#/), Character (#/character), Proposals (#/proposals),
 *           World (#/world), Session (#/session)
 *   GM:     Queue (#/gm), Feed (#/gm/feed), World (#/gm/world),
 *           Sessions (#/gm/sessions), More (#/gm/more)
 *
 * Active tab:
 *   Determined by matching window.location.hash at render time and on
 *   each hashchange event. Exact match wins; prefix match is fallback
 *   (so #/gm/feed highlights the GM Feed tab, #/ highlights Feed, etc.).
 *
 * GM-player dual identity:
 *   When the GM has a character_id the "More" menu includes a
 *   "My Character" link to #/gm/character.
 *
 * Visibility:
 *   Nav is hidden when:
 *   - $store.app.user is null (not authenticated)
 *   - Current route is /login, /setup, or /join
 *
 * Notification badges:
 *   window.navBadges = { proposals: 0, queue: 0 }
 *   Views update these counts on each poll cycle, then dispatch a
 *   'nav:refresh' CustomEvent to trigger a re-render.
 *   - proposals: count of newly-approved/rejected proposals (player)
 *   - queue:     count of pending proposals awaiting GM review
 */

window.components = window.components || {};

// ---------------------------------------------------------------------------
// Notification badge registry
// ---------------------------------------------------------------------------

/**
 * Global badge counts. Views update these and dispatch 'nav:refresh' to
 * trigger a re-render of the nav.
 *
 *   proposals — count of newly-approved/rejected proposals since last viewed
 *   queue     — count of pending proposals awaiting GM review
 */
window.navBadges = window.navBadges || { proposals: 0, queue: 0 };

window.components.nav = (function () {
  // ---------------------------------------------------------------------------
  // Routes that should hide the nav entirely
  // ---------------------------------------------------------------------------
  var HIDDEN_ROUTES = ["/login", "/setup", "/join"];

  // ---------------------------------------------------------------------------
  // Tab definitions
  // ---------------------------------------------------------------------------
  var PLAYER_TABS = [
    { label: "Feed",      hash: "#/",          matchPrefix: false },
    { label: "Character", hash: "#/character", matchPrefix: true  },
    { label: "Proposals", hash: "#/proposals", matchPrefix: true  },
    { label: "World",     hash: "#/world",     matchPrefix: true  },
    { label: "Session",   hash: "#/session",   matchPrefix: true  },
  ];

  var GM_TABS = [
    { label: "Queue",    hash: "#/gm",           matchPrefix: false },
    { label: "Feed",     hash: "#/gm/feed",      matchPrefix: true  },
    { label: "World",    hash: "#/gm/world",     matchPrefix: true  },
    { label: "Sessions", hash: "#/gm/sessions",  matchPrefix: true  },
    { label: "More",     hash: "#/gm/more",      matchPrefix: true  },
  ];

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  /**
   * Parse window.location.hash to a normalised path.
   * '' or '#' → '/'
   * '#/character' → '/character'
   */
  function _currentPath() {
    var hash = window.location.hash;
    if (!hash || hash === "#") return "/";
    return hash.slice(1) || "/";
  }

  /**
   * Determine whether a tab is active given the current path.
   * Special case: '#/' only matches exactly '/' to avoid matching everything.
   */
  function _isActive(tab, currentPath) {
    var tabPath = tab.hash.slice(1) || "/";
    if (!tab.matchPrefix) {
      return currentPath === tabPath;
    }
    // Prefix match: '/gm/feed' is active for '/gm/feed' and '/gm/feed/silent'
    return currentPath === tabPath || currentPath.indexOf(tabPath + "/") === 0;
  }

  /**
   * Return true if the nav should be hidden on this route.
   */
  function _isHiddenRoute(path) {
    for (var i = 0; i < HIDDEN_ROUTES.length; i++) {
      if (path === HIDDEN_ROUTES[i] || path.indexOf(HIDDEN_ROUTES[i] + "/") === 0) {
        return true;
      }
    }
    return false;
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  /**
   * Derive a badge count for a tab from window.navBadges.
   * Maps tab labels to their corresponding navBadges key.
   * Returns 0 if the tab has no badge or the count is 0.
   * @param {object} tab
   * @returns {number}
   */
  function _badgeCount(tab) {
    var badges = window.navBadges;
    if (!badges) return 0;
    if (tab.label === "Proposals") return badges.proposals || 0;
    if (tab.label === "Queue") return badges.queue || 0;
    return 0;
  }

  /**
   * Build a single <a> tab element, with optional notification badge.
   */
  function _buildTab(tab, currentPath) {
    var a = document.createElement("a");
    a.href = tab.hash;
    a.className = "nav-tab";
    a.setAttribute("aria-label", tab.label);

    if (_isActive(tab, currentPath)) {
      a.classList.add("nav-tab--active");
      a.setAttribute("aria-current", "page");
    }

    // Build the tab content: label text + optional badge
    var count = _badgeCount(tab);
    if (count > 0) {
      // Use a wrapper span so badge is positioned relative to the label
      var labelSpan = document.createElement("span");
      labelSpan.className = "nav-tab__label";
      labelSpan.textContent = tab.label;

      var badgeEl = document.createElement("span");
      badgeEl.className = "nav-badge";
      badgeEl.textContent = String(count > 99 ? "99+" : count);
      badgeEl.setAttribute("aria-label", count + " notification" + (count === 1 ? "" : "s"));

      a.appendChild(labelSpan);
      a.appendChild(badgeEl);
    } else {
      a.textContent = tab.label;
    }

    return a;
  }

  /**
   * Build the complete <nav> element for the current auth state.
   * Returns null if the nav should not be shown.
   */
  function _buildNav() {
    var currentPath = _currentPath();

    // Hide on auth/setup routes regardless of login state
    if (_isHiddenRoute(currentPath)) {
      return null;
    }

    // Hide when not authenticated
    var store = null;
    if (typeof Alpine !== "undefined") {
      store = Alpine.store("app");
    }
    if (!store || !store.user) {
      return null;
    }

    var nav = document.createElement("nav");
    nav.id = "app-nav";
    nav.setAttribute("aria-label", "Main navigation");

    var tabs = store.isGm() ? GM_TABS : PLAYER_TABS;

    for (var i = 0; i < tabs.length; i++) {
      nav.appendChild(_buildTab(tabs[i], currentPath));
    }

    // GM dual-identity: append "My Character" link inside the More group
    // We add it as a visually distinct secondary link (not a main tab)
    if (store.isGm() && store.character_id) {
      var charLink = document.createElement("a");
      charLink.href = "#/gm/character";
      charLink.className = "nav-tab nav-tab--secondary";
      charLink.textContent = "My Character";
      charLink.setAttribute("aria-label", "My Character");
      if (currentPath === "/gm/character") {
        charLink.classList.add("nav-tab--active");
        charLink.setAttribute("aria-current", "page");
      }
      nav.appendChild(charLink);
    }

    return nav;
  }

  // ---------------------------------------------------------------------------
  // Mount / update
  // ---------------------------------------------------------------------------

  /**
   * Replace the contents of #nav-container with the current nav state.
   * Safe to call multiple times (re-renders in place).
   */
  function _render() {
    var container = document.getElementById("nav-container");
    if (!container) return;

    // Remove old nav if present
    var existing = document.getElementById("app-nav");
    if (existing) {
      existing.parentNode.removeChild(existing);
    }

    var nav = _buildNav();
    if (nav) {
      container.appendChild(nav);
      container.hidden = false;
    } else {
      container.hidden = true;
    }
  }

  /**
   * Mount the nav component: attach hashchange and store-change listeners,
   * then perform the initial render.
   *
   * Call this once after alpine:initialized fires.
   */
  function mount() {
    // Re-render on every hash change (active tab highlight, route-hide logic)
    window.addEventListener("hashchange", _render);

    // Re-render when Alpine store changes (login/logout)
    // Alpine does not have a built-in subscribe — use a MutationObserver on a
    // sentinel element, or simply re-render on a custom event fired by app.js.
    // We also expose a manual refresh that views can call after auth changes.
    document.addEventListener("nav:refresh", _render);

    _render();
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------
  return {
    /**
     * Mount the navigation component. Call once after alpine:initialized.
     */
    mount: mount,

    /**
     * Force a re-render (e.g., after login/logout changes store state).
     * app.js or auth views can dispatch the 'nav:refresh' CustomEvent or
     * call this directly.
     */
    refresh: _render,
  };
})();
