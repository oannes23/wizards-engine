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
   * Return true if the current user is the GM.
   * @returns {boolean}
   */
  function _isGm() {
    try {
      return !!(typeof Alpine !== "undefined" && Alpine.store("app") && Alpine.store("app").isGm());
    } catch (_) {
      return false;
    }
  }

  /**
   * Dispatch a success toast via the api:success custom event.
   * @param {string} message
   */
  function _showSuccess(message) {
    document.dispatchEvent(new CustomEvent("api:success", {
      detail: { message: message },
      bubbles: true,
    }));
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

      // ---- Render debounce timer --------------------------------------------
      _renderTimer: null,

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
       * Debounced via setTimeout so rapid successive calls coalesce into
       * a single render after Alpine has finished updating reactive state.
       */
      _renderCards: function () {
        var self = this;
        clearTimeout(self._renderTimer);
        self._renderTimer = setTimeout(function () {
          _renderCardList(self);
        }, 0);
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
  // GM toolbar renderer
  // ---------------------------------------------------------------------------

  /**
   * Render the GM-only "Create New" button into #world-gm-toolbar.
   * Shows only for Characters, Groups, and Locations tabs (not Stories).
   * Hidden entirely for player users.
   *
   * @param {string} tab — current active tab key
   */
  function _renderGmToolbar(tab) {
    var toolbar = document.getElementById("world-gm-toolbar");
    if (!toolbar) return;

    var createableTabs = { characters: true, groups: true, locations: true };

    if (!_isGm() || !createableTabs[tab]) {
      toolbar.innerHTML = "";
      return;
    }

    var routes = {
      characters: "#/gm/world/characters/new",
      groups:     "#/gm/world/groups/new",
      locations:  "#/gm/world/locations/new",
    };

    var labels = {
      characters: "Create New Character",
      groups:     "Create New Group",
      locations:  "Create New Location",
    };

    toolbar.innerHTML =
      '<div class="world-gm-toolbar__row">' +
        '<a href="' + _esc(routes[tab]) + '"' +
           ' class="world-gm-toolbar__create-btn"' +
           ' aria-label="' + _esc(labels[tab]) + '">' +
          '+ Create New' +
        '</a>' +
      '</div>';
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

    // Update GM toolbar (Create New button) for applicable tabs.
    _renderGmToolbar(tab);

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

    var isGm = _isGm();

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
        var cardHtml = window.components.gameObjectCard.render({ type: type, data: itemData });
        if (isGm) {
          var itemId   = item.id || "";
          var itemName = item.name || item.display_name || "Untitled";
          cardHtml =
            '<div class="world-card-wrap">' +
              cardHtml +
              '<div class="world-card-actions">' +
                '<a class="world-card-actions__edit"' +
                   ' href="#/gm/world/' + _esc(tab) + '/' + _esc(encodeURIComponent(itemId)) + '/edit"' +
                   ' aria-label="Edit ' + _esc(itemName) + '">' +
                  'Edit' +
                '</a>' +
                '<button class="world-card-actions__archive"' +
                        ' data-world-archive-type="' + _esc(type) + '"' +
                        ' data-world-archive-tab="' + _esc(tab) + '"' +
                        ' data-world-archive-id="' + _esc(itemId) + '"' +
                        ' data-world-archive-name="' + _esc(itemName) + '"' +
                        ' aria-label="Archive ' + _esc(itemName) + '">' +
                  'Archive' +
                '</button>' +
              '</div>' +
            '</div>';
        }
        html.push(cardHtml);
      }
      container.innerHTML = html.join("");
      window.components.gameObjectCard.bindClicks(container);
      window.components.gameObjectCard.bindStarClicks(container, function (cardType, cardId, currentlyStarred) {
        _handleStar(data, container, cardType, cardId, currentlyStarred);
      });
      if (isGm) {
        _bindArchiveClicks(container, data);
      }
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
  // Archive handler
  // ---------------------------------------------------------------------------

  /**
   * Show an inline confirmation dialog for archiving a game object.
   * On confirm: calls DELETE /api/v1/{tab}/{id}, removes the card wrapper
   * from the DOM, and shows a success toast.
   * On cancel: dismisses the dialog without action.
   *
   * @param {HTMLElement} container — the card-list container
   * @param {string} type           — "character" | "group" | "location"
   * @param {string} tab            — "characters" | "groups" | "locations"
   * @param {string} id             — ULID
   * @param {string} name           — display name for the confirmation message
   * @param {object} data           — Alpine data (used to splice item from cache)
   */
  function _showArchiveConfirm(container, type, tab, id, name, data) {
    // Remove any existing confirmation dialog first
    var existing = document.getElementById("world-archive-confirm");
    if (existing) existing.remove();

    var dialog = document.createElement("div");
    dialog.id = "world-archive-confirm";
    dialog.className = "world-archive-confirm";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Confirm archive");
    dialog.innerHTML =
      '<div class="world-archive-confirm__box">' +
        '<p class="world-archive-confirm__message">' +
          'Are you sure you want to archive ' + window.utils.esc(name) + '? This can be undone.' +
        '</p>' +
        '<div class="world-archive-confirm__actions">' +
          '<button class="world-archive-confirm__cancel">Cancel</button>' +
          '<button class="world-archive-confirm__confirm">Archive</button>' +
        '</div>' +
      '</div>';

    document.body.appendChild(dialog);

    dialog.querySelector(".world-archive-confirm__cancel").addEventListener("click", function () {
      dialog.remove();
    });

    dialog.querySelector(".world-archive-confirm__confirm").addEventListener("click", function () {
      dialog.remove();

      // Find the card wrapper and remove it (optimistic UI)
      var wrap = container.querySelector(
        '.world-card-wrap [data-world-archive-id="' + id + '"]'
      );
      var wrapEl = wrap ? wrap.closest(".world-card-wrap") : null;
      if (wrapEl) wrapEl.remove();

      // Also remove from data cache so re-renders stay clean
      if (data[tab] && Array.isArray(data[tab])) {
        data[tab] = data[tab].filter(function (item) { return item.id !== id; });
      }

      api
        .del("/api/v1/" + tab + "/" + encodeURIComponent(id))
        .then(function () {
          _showSuccess(name + " archived.");
        })
        .catch(function () {
          // Re-fetch to restore if the API call failed
          _showSuccess("Archive failed. Please reload.");
          data.loaded[tab] = false;
          data._fetchData(tab);
        });
    });

    // Close on backdrop click
    dialog.addEventListener("click", function (evt) {
      if (evt.target === dialog) {
        dialog.remove();
      }
    });

    // Focus the cancel button for accessibility
    dialog.querySelector(".world-archive-confirm__cancel").focus();
  }

  /**
   * Wire Archive button click handlers in the card list.
   * Archive buttons carry data-world-archive-* attributes for identification.
   *
   * @param {HTMLElement} container — the card-list container
   * @param {object} data           — Alpine data object
   */
  function _bindArchiveClicks(container, data) {
    var btns = container.querySelectorAll("[data-world-archive-id]");
    for (var i = 0; i < btns.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function (evt) {
          evt.stopPropagation();
          var type = btn.getAttribute("data-world-archive-type");
          var tab  = btn.getAttribute("data-world-archive-tab");
          var id   = btn.getAttribute("data-world-archive-id");
          var name = btn.getAttribute("data-world-archive-name");
          _showArchiveConfirm(container, type, tab, id, name, data);
        });
      })(btns[i]);
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

      // GM toolbar — "Create New" button, rendered imperatively by _renderCardList()
      '  <div id="world-gm-toolbar" class="world-gm-toolbar"></div>',

      // Card list — populated imperatively by _renderCardList()
      '  <div id="world-card-list"',
      '       class="world-card-list"',
      '       x-ignore',
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

    }
  };
})();
