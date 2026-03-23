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
 *   GM:     Queue (#/gm), Event Feed (#/gm/feed), Game Objects (#/gm/world),
 *           Sessions (#/gm/sessions), More (dropdown)
 *
 * Active tab:
 *   Determined by matching window.location.hash at render time and on
 *   each hashchange event. Exact match wins; prefix match is fallback
 *   (so #/gm/feed highlights the GM Event Feed tab, #/ highlights Feed, etc.).
 *
 * GM-player dual identity:
 *   When the GM has a character_id the "More" dropdown includes a
 *   "My Character" link to #/gm/character.
 *
 * More dropdown:
 *   The GM "More" button opens a floating panel above the nav bar with links
 *   to Players, Invites, Trait Templates, Clocks, Profile. Clicking any link
 *   navigates and closes the dropdown. Clicking outside or pressing Escape
 *   also closes it.
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
    { label: "Queue",        hash: "#/gm",          matchPrefix: false },
    { label: "Event Feed",   hash: "#/gm/feed",     matchPrefix: true  },
    { label: "Game Objects", hash: "#/gm/world",    matchPrefix: true  },
    { label: "Sessions",     hash: "#/gm/sessions", matchPrefix: true  },
  ];

  // Items shown in the GM "More" dropdown panel.
  // matchPrefix controls whether any of these routes activates the More button.
  var GM_MORE_ITEMS = [
    { label: "Players",         hash: "#/gm/players"         },
    { label: "Invites",         hash: "#/gm/invites"         },
    { label: "Trait Templates", hash: "#/gm/trait-templates" },
    { label: "Clocks",          hash: "#/gm/clocks"          },
    { label: "Profile",         hash: "#/profile"            },
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
   * Return true if the current path matches any of the GM_MORE_ITEMS routes,
   * which means the More button should appear active.
   * @param {string} currentPath
   * @returns {boolean}
   */
  function _isMoreActive(currentPath) {
    for (var i = 0; i < GM_MORE_ITEMS.length; i++) {
      var itemPath = GM_MORE_ITEMS[i].hash.slice(1) || "/";
      if (currentPath === itemPath || currentPath.indexOf(itemPath + "/") === 0) {
        return true;
      }
    }
    // Also mark More active when on the old /gm/more route
    if (currentPath === "/gm/more") return true;
    // Also mark More active for GM character route (shown as My Character in dropdown)
    if (currentPath === "/gm/character") return true;
    return false;
  }

  /**
   * Close the More dropdown panel if it exists, and remove the outside-click
   * listener. Safe to call when panel is not open.
   */
  function _closeMorePanel() {
    var panel = document.getElementById("nav-more-panel");
    if (panel) {
      panel.parentNode.removeChild(panel);
    }
    document.removeEventListener("click", _outsideMoreClick, true);
    document.removeEventListener("keydown", _escMoreKey);
  }

  /**
   * Handle clicks outside the More panel. Closes the panel when the user
   * taps anywhere that is not the panel or the More button itself.
   */
  function _outsideMoreClick(evt) {
    var panel = document.getElementById("nav-more-panel");
    var btn = document.getElementById("nav-more-btn");
    if (!panel) return;
    if ((panel && panel.contains(evt.target)) || (btn && btn.contains(evt.target))) {
      return;
    }
    _closeMorePanel();
  }

  /**
   * Close More panel on Escape key.
   */
  function _escMoreKey(evt) {
    if (evt.key === "Escape") {
      _closeMorePanel();
    }
  }

  /**
   * Build and open the More dropdown panel, positioned above the nav-container.
   * @param {string} currentPath
   * @param {object} store  — Alpine app store
   */
  function _openMorePanel(currentPath, store) {
    // If already open, close it (toggle behaviour)
    if (document.getElementById("nav-more-panel")) {
      _closeMorePanel();
      return;
    }

    var panel = document.createElement("div");
    panel.id = "nav-more-panel";
    panel.className = "nav-more-panel";
    panel.setAttribute("role", "menu");
    panel.setAttribute("aria-label", "More options");

    // Build item list
    var items = GM_MORE_ITEMS.slice(); // copy
    // Prepend "My Character" if the GM has a character
    if (store && store.character_id) {
      items = [{ label: "My Character", hash: "#/gm/character" }].concat(items);
    }

    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var itemPath = item.hash.slice(1) || "/";
      var isActive = (currentPath === itemPath || currentPath.indexOf(itemPath + "/") === 0);

      var a = document.createElement("a");
      a.href = item.hash;
      a.className = "nav-more-panel__item" + (isActive ? " nav-more-panel__item--active" : "");
      a.textContent = item.label;
      a.setAttribute("role", "menuitem");
      if (isActive) {
        a.setAttribute("aria-current", "page");
      }

      // Clicking any item closes the panel
      a.addEventListener("click", _closeMorePanel);

      panel.appendChild(a);
    }

    // Attach panel to nav-container (renders above the nav bar)
    var container = document.getElementById("nav-container");
    if (container) {
      container.appendChild(panel);
    }

    // Close on outside click or Escape (use capture phase so panel link clicks
    // are processed before the outside-click handler fires)
    setTimeout(function () {
      document.addEventListener("click", _outsideMoreClick, true);
      document.addEventListener("keydown", _escMoreKey);
    }, 0);
  }

  /**
   * Build the GM "More" button that opens the dropdown panel.
   * @param {string} currentPath
   * @param {object} store
   * @returns {HTMLElement}
   */
  function _buildMoreButton(currentPath, store) {
    var btn = document.createElement("button");
    btn.id = "nav-more-btn";
    btn.className = "nav-tab nav-tab--more";
    btn.setAttribute("aria-label", "More navigation options");
    btn.setAttribute("aria-haspopup", "menu");
    btn.setAttribute("aria-expanded", "false");

    if (_isMoreActive(currentPath)) {
      btn.classList.add("nav-tab--active");
    }

    btn.textContent = "More";

    btn.addEventListener("click", function (evt) {
      evt.stopPropagation();
      var isOpen = !!document.getElementById("nav-more-panel");
      btn.setAttribute("aria-expanded", String(!isOpen));
      _openMorePanel(currentPath, store);
    });

    return btn;
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

    if (store.isGm()) {
      // GM gets a "More" button that opens a dropdown
      nav.appendChild(_buildMoreButton(currentPath, store));
    }

    // Both GMs and players get a visible Profile link
    var profileLink = document.createElement("a");
    profileLink.href = "#/profile";
    profileLink.className = "nav-tab nav-tab--secondary";
    profileLink.textContent = "Profile";
    profileLink.setAttribute("aria-label", "Profile");
    if (currentPath === "/profile") {
      profileLink.classList.add("nav-tab--active");
      profileLink.setAttribute("aria-current", "page");
    }
    nav.appendChild(profileLink);

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

    // Close any open More dropdown before rebuilding the nav
    _closeMorePanel();

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
