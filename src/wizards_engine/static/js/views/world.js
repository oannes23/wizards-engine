/* Wizards Engine — World Browser view
 *
 * Routes:  #/world   and   #/gm/world
 * Access:  All authenticated users (GM sees same content as players)
 *
 * Displays a tabbed world browser with four categories:
 *   Characters — GET /api/v1/characters  → GameObjectCard list
 *   Groups     — GET /api/v1/groups      → GameObjectCard list
 *   Locations  — GET /api/v1/locations   → GameObjectCard list
 *   Stories    — GET /api/v1/stories     → custom story cards
 *
 * Each tab is lazy-loaded on first selection.  Data is cached in the
 * Alpine x-data state for the lifetime of the view.
 *
 * A text search input above the card list filters by name (client-side,
 * case-insensitive substring match on already-fetched data).
 *
 * Cards are tappable and navigate to the object's detail route:
 *   #/world/characters/{id}
 *   #/world/groups/{id}
 *   #/world/locations/{id}
 *   #/world/stories/{id}
 *
 * Registers as:  window.views.world
 * Called by:     router.js route table entries for "/world" and "/gm/world"
 */

window.views = window.views || {};

window.views.world = (function () {
  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /**
   * Escape a string for safe use in HTML attribute values and text content.
   * Delegates to window.utils.esc; also escapes single quotes for use inside
   * Alpine attribute strings.
   * @param {*} str
   * @returns {string}
   */
  function _esc(str) {
    return window.utils.esc(str).replace(/'/g, "&#39;");
  }

  /**
   * Truncate a string to at most maxLen characters, appending an ellipsis.
   * @param {string} text
   * @param {number} maxLen
   * @returns {string}
   */
  function _snippet(text, maxLen) {
    if (!text) return "";
    var s = String(text);
    if (s.length <= maxLen) return s;
    return s.slice(0, maxLen).trimEnd() + "\u2026";
  }

  // ---------------------------------------------------------------------------
  // Alpine data factory
  // ---------------------------------------------------------------------------

  /**
   * Build the initial Alpine x-data object for the world browser.
   * Defined as a factory so each render() call starts from a clean state.
   *
   * @returns {object} Alpine x-data object
   */
  function _makeData() {
    return {
      // ---- Tab state --------------------------------------------------------
      activeTab: "characters",

      // ---- Per-tab data caches ---------------------------------------------
      characters: [],
      groups:     [],
      locations:  [],
      stories:    [],

      // ---- Per-tab load status: false = not fetched, 'loading', 'done', 'error'
      loaded: {
        characters: false,
        groups:     false,
        locations:  false,
        stories:    false,
      },

      // ---- UI state --------------------------------------------------------
      search:  "",
      loading: false,  // true while the active tab's fetch is in flight
      error:   null,   // error message for the active tab, or null

      // ---- Starred state ---------------------------------------------------
      // Set of "type/id" keys for objects the current user has starred.
      _starredSet: {},

      // ---- Computed helpers ------------------------------------------------

      /**
       * Return the items for the active tab filtered by the search query.
       * For stories, the name field is simply 'name'.
       * @returns {Array}
       */
      filteredItems: function () {
        var tab  = this.activeTab;
        var all  = this[tab] || [];
        var q    = (this.search || "").trim().toLowerCase();
        if (!q) return all;
        return all.filter(function (item) {
          var name = (item.name || "").toLowerCase();
          return name.indexOf(q) !== -1;
        });
      },

      // ---- Tab switching ---------------------------------------------------

      /**
       * Switch to a tab by name, fetching its data if not yet loaded.
       * @param {string} tab — "characters" | "groups" | "locations" | "stories"
       */
      switchTab: function (tab) {
        this.error = null;
        this.activeTab = tab;
        this.search = "";
        this._fetchIfNeeded(tab);
      },

      // ---- Data fetching ---------------------------------------------------

      /**
       * Fetch the data for a tab if it hasn't been loaded yet.
       * @param {string} tab
       */
      _fetchIfNeeded: function (tab) {
        if (this.loaded[tab]) return;
        this._fetchData(tab);
      },

      /**
       * Fetch and store the items for a given tab from the API.
       * Stores all pages (up to the first page for now — backend default is 50
       * items which is sufficient for an MVP world browser).
       *
       * @param {string} tab
       */
      _fetchData: function (tab) {
        var self    = this;
        var urlMap  = {
          characters: "/api/v1/characters",
          groups:     "/api/v1/groups",
          locations:  "/api/v1/locations",
          stories:    "/api/v1/stories",
        };
        var url = urlMap[tab];
        if (!url) return;

        self.loaded[tab]  = "loading";
        self.loading      = (self.activeTab === tab);
        self.error        = null;

        api
          .get(url)
          .then(function (data) {
            var items = (data && data.items) ? data.items : [];
            self[tab]        = items;
            self.loaded[tab] = "done";
          })
          .catch(function (err) {
            self.loaded[tab] = "error";
            self.error = (err && err.message) || "Failed to load " + tab + ".";
          })
          .finally(function () {
            if (self.activeTab === tab) {
              self.loading = false;
            }
            // Re-render the card list after data lands
            self._renderCards();
          });
      },

      /**
       * Trigger a re-render of the card list for the current tab.
       * Called after a fetch completes or when the tab changes.
       * Uses a microtask (Promise.resolve) so Alpine has finished updating
       * reactive state before we read filteredItems().
       */
      _renderCards: function () {
        var self = this;
        Promise.resolve().then(function () {
          _renderCardList(self);
        });
      },

      // ---- Lifecycle -------------------------------------------------------

      /**
       * Called by Alpine when this x-data component initialises.
       * Fetches the user's starred objects, then starts the initial Characters
       * tab fetch.
       */
      init: function () {
        var self = this;
        api
          .get("/api/v1/me/starred")
          .then(function (data) {
            var items = Array.isArray(data) ? data : [];
            var set = {};
            for (var i = 0; i < items.length; i++) {
              var item = items[i];
              if (item.type && item.id) {
                set[item.type + "/" + item.id] = true;
              }
            }
            self._starredSet = set;
          })
          .catch(function () {
            // Starred list is non-critical — proceed without it.
            self._starredSet = {};
          })
          .finally(function () {
            self._fetchIfNeeded("characters");
          });
      },
    };
  }

  // ---------------------------------------------------------------------------
  // Imperative card-list renderer
  // ---------------------------------------------------------------------------

  /**
   * Build and inject the card list HTML into #world-card-list.
   * For character/group/location tabs, delegates to gameObjectCard.render().
   * For the stories tab, renders custom story cards inline.
   *
   * @param {object} data — the Alpine data object
   */
  function _renderCardList(data) {
    var container = document.getElementById("world-card-list");
    if (!container) return;

    var tab   = data.activeTab;
    var items = data.filteredItems();

    // Show loading / error states imperatively (Alpine also drives the
    // overlay, but this keeps the card area clean while waiting).
    if (data.loaded[tab] === "loading" || data.loaded[tab] === false) {
      container.innerHTML = "";
      return;
    }

    if (data.loaded[tab] === "error") {
      container.innerHTML = "";
      return;
    }

    if (items.length === 0) {
      container.innerHTML = '<p class="world-empty">No ' + _esc(tab) + ' found.</p>';
      return;
    }

    var html = [];

    if (tab === "stories") {
      // Custom story card rendering
      for (var i = 0; i < items.length; i++) {
        html.push(_renderStoryCard(items[i]));
      }
      container.innerHTML = html.join("");
      _bindStoryClicks(container);
    } else {
      // GameObjectCard component handles character / group / location
      var type = tab.slice(0, -1); // "characters" → "character", etc.
      var starredSet = data._starredSet || {};
      for (var j = 0; j < items.length; j++) {
        var item = items[j];
        var itemData = {};
        // Copy item fields into a new object so we can inject the starred flag
        for (var k in item) {
          if (Object.prototype.hasOwnProperty.call(item, k)) {
            itemData[k] = item[k];
          }
        }
        itemData.starred = !!starredSet[type + "/" + item.id];
        html.push(
          window.components.gameObjectCard.render({ type: type, data: itemData })
        );
      }
      container.innerHTML = html.join("");
      window.components.gameObjectCard.bindClicks(container);
      window.components.gameObjectCard.bindStarClicks(container, function (cardType, cardId, currentlyStarred) {
        _handleStar(data, container, cardType, cardId, currentlyStarred);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Star / unstar handler
  // ---------------------------------------------------------------------------

  /**
   * Handle a star button click on a game object card.
   * Applies optimistic UI immediately, then calls the API. Reverts on failure.
   *
   * @param {object} data      — Alpine data object (for _starredSet)
   * @param {HTMLElement} container — card-list container
   * @param {string} cardType  — "character" | "group" | "location"
   * @param {string} cardId    — object ULID
   * @param {boolean} currentlyStarred — true if the button was showing ★
   */
  function _handleStar(data, container, cardType, cardId, currentlyStarred) {
    var key = cardType + "/" + cardId;

    // Optimistic UI: toggle the button immediately.
    var btn = container.querySelector(
      '[data-card-star][data-card-type="' + cardType + '"][data-card-id="' + cardId + '"]'
    );

    if (currentlyStarred) {
      // Unstar
      if (btn) {
        btn.textContent = "\u2606"; // ☆
        btn.setAttribute("data-card-starred", "false");
        btn.setAttribute("aria-pressed", "false");
      }
      delete data._starredSet[key];

      api
        .del("/api/v1/me/starred/" + encodeURIComponent(cardType) + "/" + encodeURIComponent(cardId))
        .catch(function () {
          // Revert on failure
          data._starredSet[key] = true;
          if (btn) {
            btn.textContent = "\u2605"; // ★
            btn.setAttribute("data-card-starred", "true");
            btn.setAttribute("aria-pressed", "true");
          }
        });
    } else {
      // Star
      if (btn) {
        btn.textContent = "\u2605"; // ★
        btn.setAttribute("data-card-starred", "true");
        btn.setAttribute("aria-pressed", "true");
      }
      data._starredSet[key] = true;

      api
        .post("/api/v1/me/starred", { type: cardType, id: cardId })
        .catch(function () {
          // Revert on failure
          delete data._starredSet[key];
          if (btn) {
            btn.textContent = "\u2606"; // ☆
            btn.setAttribute("data-card-starred", "false");
            btn.setAttribute("aria-pressed", "false");
          }
        });
    }
  }

  // ---------------------------------------------------------------------------
  // Story card builder
  // ---------------------------------------------------------------------------

  /**
   * Render a single story card as an HTML string.
   * Stories have a different shape from game objects so we render them here
   * instead of through gameObjectCard.
   *
   * @param {object} story — StoryResponse from the API
   * @returns {string} HTML
   */
  function _renderStoryCard(story) {
    var id      = story.id || "";
    var name    = story.name || "Untitled";
    var status  = story.status || "active";
    var tags    = story.tags || [];
    var summary = _snippet(story.summary || story.description || "", 120);
    var hash    = "#/world/stories/" + encodeURIComponent(id);

    var statusMod = {
      active:    "active",
      completed: "completed",
      abandoned: "abandoned",
    }[status] || "active";

    var tagHtml = "";
    if (tags.length > 0) {
      var tagParts = [];
      for (var i = 0; i < tags.length; i++) {
        tagParts.push('<span class="world-story-card__tag">' + _esc(tags[i]) + '</span>');
      }
      tagHtml = '<div class="world-story-card__tags">' + tagParts.join("") + "</div>";
    }

    return (
      '<article class="world-story-card world-story-card--' + _esc(statusMod) + '"' +
               ' data-story-id="' + _esc(id) + '"' +
               ' data-story-hash="' + _esc(hash) + '"' +
               ' role="button"' +
               ' tabindex="0"' +
               ' aria-label="' + _esc(name) + '">' +
        '<header class="world-story-card__header">' +
          '<strong class="world-story-card__name">' + _esc(name) + '</strong>' +
          '<mark class="world-story-card__status world-story-card__status--' + _esc(statusMod) + '">' +
            _esc(status) +
          '</mark>' +
        '</header>' +
        (tagHtml) +
        (summary
          ? '<p class="world-story-card__summary">' + _esc(summary) + '</p>'
          : '') +
      '</article>'
    );
  }

  /**
   * Wire click and keyboard navigation handlers for story cards in a container.
   * @param {HTMLElement} container
   */
  function _bindStoryClicks(container) {
    if (!container) return;
    var cards = container.querySelectorAll(".world-story-card");
    for (var i = 0; i < cards.length; i++) {
      (function (card) {
        function _activate() {
          var hash = card.getAttribute("data-story-hash");
          if (hash) {
            if (typeof router !== "undefined") {
              router.navigate(hash);
            } else {
              window.location.hash = hash;
            }
          }
        }
        card.addEventListener("click", _activate);
        card.addEventListener("keydown", function (evt) {
          if (evt.key === "Enter" || evt.key === " ") {
            evt.preventDefault();
            _activate();
          }
        });
      })(cards[i]);
    }
  }

  // ---------------------------------------------------------------------------
  // HTML template builder
  // ---------------------------------------------------------------------------

  /**
   * Build the static HTML scaffold for the world browser.
   * Alpine directives handle tab switching, loading/error states, and search.
   * The card list is rendered imperatively via _renderCardList().
   *
   * @returns {string} HTML
   */
  function _buildHtml() {
    var tabs = [
      { key: "characters", label: "Characters" },
      { key: "groups",     label: "Groups"     },
      { key: "locations",  label: "Locations"  },
      { key: "stories",    label: "Stories"    },
    ];

    var tabHtml = tabs.map(function (t) {
      return (
        '<button class="world-tab"' +
                ' :class="{ \'world-tab--active\': activeTab === \'' + t.key + '\' }"' +
                ' @click="switchTab(\'' + t.key + '\'); _renderCards()"' +
                ' :aria-current="activeTab === \'' + t.key + '\' ? \'page\' : undefined"' +
                ' aria-label="' + _esc(t.label) + ' tab">' +
          _esc(t.label) +
        '</button>'
      );
    }).join("\n");

    return [
      '<div id="world-root" x-data="worldData">',

      '  <h2 class="world-heading">World</h2>',

      // Tab bar
      '  <nav class="world-tabs" role="tablist" aria-label="World browser categories">',
      tabHtml,
      '  </nav>',

      // Search input
      '  <div class="world-search">',
      '    <input type="search"',
      '           id="world-search-input"',
      '           class="world-search__input"',
      '           placeholder="Search by name..."',
      '           aria-label="Filter by name"',
      '           autocomplete="off"',
      '           x-model="search"',
      '           @input="_renderCards()"',
      '    />',
      '  </div>',

      // Loading indicator
      '  <div class="world-loading"',
      '       x-show="loading"',
      '       aria-live="polite"',
      '       aria-busy="true">',
      '    Loading...',
      '  </div>',

      // Error message
      '  <div class="world-error"',
      '       role="alert"',
      '       x-show="error && !loading"',
      '       x-text="error">',
      '  </div>',

      // Card list — populated imperatively by _renderCardList()
      '  <div id="world-card-list"',
      '       class="world-card-list"',
      '       role="list"',
      '       aria-label="World objects">',
      '  </div>',

      '</div>', // end #world-root
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // Render (public entry point)
  // ---------------------------------------------------------------------------

  /**
   * Mount the world browser into #view.
   * Registers the Alpine data component, initialises the Alpine subtree,
   * and wires a hashchange cleanup handler.
   */
  return function render() {
    var el = document.getElementById("view");
    if (!el) return;

    el.innerHTML = _buildHtml();

    if (typeof Alpine !== "undefined") {
      // Register the Alpine data component factory (idempotent by name).
      Alpine.data("worldData", _makeData);

      var root = document.getElementById("world-root");
      if (root) {
        Alpine.initTree(root);
      }

      // After Alpine initialises, trigger the initial render of the card list.
      // Use a short timeout so Alpine's init() has time to fire the first fetch.
      var renderTimer = setTimeout(function () {
        var alpineData = root && root._x_dataStack && root._x_dataStack[0];
        if (alpineData) {
          _renderCardList(alpineData);
        }
        clearTimeout(renderTimer);
      }, 0);

    }
  };
})();
