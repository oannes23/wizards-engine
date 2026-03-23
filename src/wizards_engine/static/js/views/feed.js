/* Wizards Engine — Feed views
 *
 * Handles four routes via a shared rendering core:
 *
 *   Route                Hash                Tabs shown           Active tab
 *   ------------------- ------------------- -------------------- ----------
 *   Player dashboard     #/                  All | Starred        All
 *   Player starred       #/feed/starred      All | Starred        Starred
 *   GM full feed         #/gm/feed           Full | Silent        Full
 *   GM silent feed       #/gm/feed/silent    Full | Silent        Silent
 *
 * Tab switching updates the URL hash (so the browser back button works) and
 * swaps the FeedList's data URL without re-mounting the shell.
 *
 * API endpoints consumed:
 *   GET /api/v1/me/feed           — personal (All) feed
 *   GET /api/v1/me/feed/starred   — starred feed
 *   GET /api/v1/me/feed/silent    — GM silent feed (bookkeeping events)
 *
 * Registers:
 *   window.views.feed          — player dashboard (#/)
 *   window.views.feedStarred   — player starred feed (#/feed/starred)
 *   window.views.gmFeed        — GM full feed (#/gm/feed)
 *   window.views.gmFeedSilent  — GM silent feed (#/gm/feed/silent)
 *
 * Dependencies (must already be loaded):
 *   utils.js, api.js, store.js, feed-list.js, feed-item.js
 */

window.views = window.views || {};

(function () {
  // --------------------------------------------------------------------------
  // Constants
  // --------------------------------------------------------------------------

  var FEED_URLS = {
    all:     "/api/v1/me/feed",
    starred: "/api/v1/me/feed/starred",
    full:    "/api/v1/me/feed",        // same endpoint as "all" for GMs
    silent:  "/api/v1/me/feed/silent",
  };

  // Tab configuration per view context.
  // Each tab: { key, label, url, hash }
  var PLAYER_TABS = [
    { key: "all",     label: "All",     url: FEED_URLS.all,     hash: "#/" },
    { key: "starred", label: "Starred", url: FEED_URLS.starred, hash: "#/feed/starred" },
  ];

  var GM_TABS = [
    { key: "full",   label: "Full",   url: FEED_URLS.full,   hash: "#/gm/feed" },
    { key: "silent", label: "Silent", url: FEED_URLS.silent, hash: "#/gm/feed/silent" },
  ];

  // --------------------------------------------------------------------------
  // Module-level state
  // --------------------------------------------------------------------------

  /** Currently mounted FeedList instance, or null. */
  var _feedList = null;

  /** Whether the view is currently mounted. */
  var _mounted = false;

  /** The own-routes set for this mount — used to detect navigation away. */
  var _ownHashes = null;

  // --------------------------------------------------------------------------
  // Helpers
  // --------------------------------------------------------------------------


  // --------------------------------------------------------------------------
  // Shell rendering
  // --------------------------------------------------------------------------

  /**
   * Build the tab bar HTML.
   *
   * @param {Array} tabs       — array of { key, label, hash }
   * @param {string} activeKey — key of the currently active tab
   * @returns {string} HTML
   */
  function _buildTabBar(tabs, activeKey) {
    var html =
      '<nav class="feed-tabs" role="tablist" aria-label="Feed filters">';

    for (var i = 0; i < tabs.length; i++) {
      var tab = tabs[i];
      var isActive = tab.key === activeKey;
      html +=
        '<a href="' + window.utils.esc(tab.hash) + '"' +
        '   class="feed-tab' + (isActive ? ' feed-tab--active' : '') + '"' +
        '   role="tab"' +
        '   aria-selected="' + (isActive ? 'true' : 'false') + '">' +
        window.utils.esc(tab.label) +
        '</a>';
    }

    html += '</nav>';
    return html;
  }

  /**
   * Render the full view shell (heading, tabs, feed container) into #view.
   * Creates a new FeedList and loads the active tab's URL.
   *
   * @param {object} opts
   * @param {string}   opts.heading   — page heading text
   * @param {Array}    opts.tabs      — PLAYER_TABS or GM_TABS
   * @param {string}   opts.activeKey — currently active tab key
   * @param {string[]} opts.ownHashes — hash strings that belong to this view
   */
  function _mount(opts) {
    // Destroy any previous FeedList before re-mounting.
    if (_feedList) {
      _feedList.destroy();
      _feedList = null;
    }

    var viewEl = document.getElementById("view");
    if (!viewEl) return;

    _mounted = true;
    _ownHashes = opts.ownHashes;

    // Find the active tab object.
    var activeTab = null;
    for (var i = 0; i < opts.tabs.length; i++) {
      if (opts.tabs[i].key === opts.activeKey) {
        activeTab = opts.tabs[i];
        break;
      }
    }
    if (!activeTab) return; // Shouldn't happen.

    // Render the shell.
    viewEl.innerHTML =
      '<div class="feed-view">' +
        '<h2 class="feed-view__heading">' + window.utils.esc(opts.heading) + '</h2>' +
        _buildTabBar(opts.tabs, opts.activeKey) +
        '<div id="feed-view-container" class="feed-view__container"></div>' +
      '</div>';

    // Mount FeedList into the container div.
    var container = document.getElementById("feed-view-container");
    if (!container) return;

    _feedList = new window.components.FeedList(container);
    _feedList.load(activeTab.url);

    // Register hashchange listener for teardown.
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  }

  // --------------------------------------------------------------------------
  // Teardown
  // --------------------------------------------------------------------------

  /**
   * Tear down when navigating away from all owned routes.
   */
  function _teardown() {
    _mounted = false;
    if (_feedList) {
      _feedList.destroy();
      _feedList = null;
    }
    _ownHashes = null;
  }

  /**
   * hashchange handler: tears down when leaving this view's routes entirely.
   */
  function _onHashChange() {
    if (!_ownHashes) return;
    var hash = window.location.hash || "#/";
    var stillHere = false;
    for (var i = 0; i < _ownHashes.length; i++) {
      if (_ownHashes[i] === hash) {
        stillHere = true;
        break;
      }
    }
    if (!stillHere) {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // --------------------------------------------------------------------------
  // Tab switching
  // --------------------------------------------------------------------------

  /**
   * Handle a tab change within the same view family (player or GM).
   * Re-mounts with the new active tab without navigating away.
   * Called by the router when the new hash is still one of the owned routes.
   *
   * @param {object} opts — same shape as _mount opts
   */
  function _switchTab(opts) {
    // Destroy the current FeedList; re-render the shell with the new active tab.
    _mount(opts);
  }

  // --------------------------------------------------------------------------
  // Public view entry points
  // --------------------------------------------------------------------------

  /**
   * Player dashboard — #/ (All tab).
   */
  window.views.feed = function () {
    _mount({
      heading:   "Feed",
      tabs:      PLAYER_TABS,
      activeKey: "all",
      ownHashes: ["#/", "#/feed/starred"],
    });
  };

  /**
   * Player starred feed — #/feed/starred.
   */
  window.views.feedStarred = function () {
    _mount({
      heading:   "Feed",
      tabs:      PLAYER_TABS,
      activeKey: "starred",
      ownHashes: ["#/", "#/feed/starred"],
    });
  };

  /**
   * GM full feed — #/gm/feed.
   */
  window.views.gmFeed = function () {
    _mount({
      heading:   "GM Feed",
      tabs:      GM_TABS,
      activeKey: "full",
      ownHashes: ["#/gm/feed", "#/gm/feed/silent"],
    });
  };

  /**
   * GM silent feed — #/gm/feed/silent.
   */
  window.views.gmFeedSilent = function () {
    _mount({
      heading:   "GM Feed",
      tabs:      GM_TABS,
      activeKey: "silent",
      ownHashes: ["#/gm/feed", "#/gm/feed/silent"],
    });
  };

})();
