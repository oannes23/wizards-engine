/* Wizards Engine — FeedList component
 *
 * Reusable paginated feed list. Fetches items from any feed URL that returns
 * the standard FeedResponse envelope { items, next_cursor, has_more } and
 * renders them using FeedItem.
 *
 * Usage:
 *   var list = new window.components.FeedList(containerEl);
 *   list.load('/api/v1/me/feed');
 *
 * The constructor returns an instance with:
 *   load(url)       — fetch first page from a new URL (resets state)
 *   loadMore()      — fetch the next page (appends to existing items)
 *   destroy()       — unmount, cancel callbacks, remove any wired listeners
 *
 * Registers the constructor as window.components.FeedList.
 * The instance wires its own "Load more" button click handler inside the
 * container — callers do not need to manage that.
 *
 * Dependencies (must be loaded before this file):
 *   utils.js         — window.utils.esc
 *   api.js           — window.api.get
 *   feed-item.js     — window.components.feedItem.render
 */

window.components = window.components || {};

/**
 * FeedList constructor.
 *
 * @param {HTMLElement} containerEl — the element to render into
 */
window.components.FeedList = function FeedList(containerEl) {
  var _container = containerEl;
  var _alive     = true;   // becomes false after destroy()
  var _loading   = false;
  var _items     = [];
  var _nextCursor = null;
  var _hasMore   = false;
  var _currentUrl = null;  // base URL without pagination params

  var FEED_LIMIT = 20;

  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  var _esc = function (s) { return window.utils.esc(s); };

  /**
   * Determine the current user's character_id for is_own resolution.
   * Falls back to null if the store is not yet populated.
   * @returns {string|null}
   */
  function _myCharId() {
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      return Alpine.store("app").character_id || null;
    }
    return null;
  }

  // --------------------------------------------------------------------------
  // Rendering
  // --------------------------------------------------------------------------

  /**
   * Render the full feed list HTML into _container, including:
   *   - loading skeleton (when loading and no items yet)
   *   - empty state (when done and no items)
   *   - list of FeedItem cards
   *   - "Load more" button or loading indicator at the bottom
   */
  function _render() {
    if (!_container) return;

    // Loading state: no items yet
    if (_loading && _items.length === 0) {
      _container.innerHTML =
        '<p class="feed-list__loading" aria-busy="true">Loading feed...</p>';
      return;
    }

    // Empty state
    if (!_loading && _items.length === 0) {
      _container.innerHTML =
        '<p class="feed-list__empty">No events yet.</p>';
      return;
    }

    var myCharId = _myCharId();
    var html = '<div class="feed-list__items">';

    for (var i = 0; i < _items.length; i++) {
      var item = _items[i];
      // is_own comes from the API, but cross-check against our character_id
      // as a belt-and-braces measure for the character feed case.
      var isOwn = item.is_own ||
        (myCharId !== null && (item.actor_id === myCharId || item.author_id === myCharId));
      html += window.components.feedItem.render({
        item: item,
        type: item.type || "event",
        isOwn: !!isOwn,
      });
    }

    html += '</div>';

    // Pagination footer
    if (_hasMore || _loading) {
      html +=
        '<div class="feed-list__more">' +
          '<button id="feed-list-load-more"' +
          '        class="outline secondary"' +
          '        ' + (_loading ? 'aria-busy="true" disabled' : '') + '>' +
          (_loading ? 'Loading...' : 'Load more') +
          '</button>' +
        '</div>';
    }

    _container.innerHTML = html;

    // Wire the "Load more" button
    var btn = _container.querySelector("#feed-list-load-more");
    if (btn) {
      btn.addEventListener("click", function () {
        _self.loadMore();
      });
    }
  }

  // --------------------------------------------------------------------------
  // Data fetching
  // --------------------------------------------------------------------------

  /**
   * Build the request URL by appending limit and (when paginating) cursor.
   * @param {string|null} cursor — ULID cursor from last page, or null for first
   * @returns {string}
   */
  function _buildUrl(cursor) {
    var url = _currentUrl + "?limit=" + FEED_LIMIT;
    if (cursor) {
      url += "&after=" + encodeURIComponent(cursor);
    }
    return url;
  }

  /**
   * Fetch one page.
   * @param {boolean} reset — true = first page (replace items); false = append
   */
  function _fetch(reset) {
    if (!_alive || _loading) return;

    _loading = true;
    _render();

    var cursor = reset ? null : _nextCursor;

    api
      .get(_buildUrl(cursor))
      .then(function (data) {
        if (!_alive) return;
        var incoming = (data && data.items) ? data.items : [];
        _nextCursor = (data && data.next_cursor) ? data.next_cursor : null;
        _hasMore    = !!(data && data.has_more);

        if (reset) {
          _items = incoming;
        } else {
          _items = _items.concat(incoming);
        }
      })
      .catch(function () {
        // Errors are surfaced via the api:error event in api.js.
        // Leave existing items in place; just stop loading.
      })
      .finally(function () {
        _loading = false;
        if (_alive) {
          _render();
        }
      });
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  var _self = {
    /**
     * Load the first page from a new URL. Resets all state.
     * @param {string} url — feed endpoint, without query params
     */
    load: function (url) {
      _currentUrl = url;
      _items      = [];
      _nextCursor = null;
      _hasMore    = false;
      _loading    = false;
      _fetch(true);
    },

    /**
     * Fetch the next page and append its items.
     * No-op if there are no more pages or a fetch is already in flight.
     */
    loadMore: function () {
      if (!_hasMore || _loading) return;
      _fetch(false);
    },

    /**
     * Destroy this instance. Clears the container and prevents any
     * in-flight request callbacks from updating the DOM.
     */
    destroy: function () {
      _alive = false;
      if (_container) {
        _container.innerHTML = "";
      }
    },
  };

  return _self;
};
