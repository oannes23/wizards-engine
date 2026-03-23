/* Wizards Engine — Game Objects Browser view
 *
 * Routes:  #/world   and   #/gm/world
 * Access:  All authenticated users (GM sees same content as players)
 *
 * Displays a tabbed browser with four categories:
 *   Characters — GET /api/v1/characters  → DataTable (with All/PC/NPC sub-tabs)
 *   Groups     — GET /api/v1/groups      → DataTable
 *   Locations  — GET /api/v1/locations   → DataTable
 *   Stories    — GET /api/v1/stories     → custom story cards (richer shape)
 *
 * Characters, Groups, and Locations render as sortable DataTables.
 * Sort requests are passed to the backend via sort_by/sort_dir query params.
 * The Stories tab keeps the existing card layout.
 *
 * Characters tab has sub-tabs: All | PCs | NPCs.
 *   PCs  → detail_level=full
 *   NPCs → detail_level=simplified
 *
 * Star toggle uses optimistic UI (existing pattern).
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
   * Also escapes single quotes for use inside Alpine attribute strings.
   * @param {*} str
   * @returns {string}
   */
  function window.utils.esc(str) {
    return window.utils.esc(str).replace(/'/g, "&#39;");
  }

  /**
   * Truncate a string to at most maxLen characters, appending an ellipsis.
   * @param {string} text
   * @param {number} maxLen
   * @returns {string}
   */

  // ---------------------------------------------------------------------------
  // DataTable column configurations
  // ---------------------------------------------------------------------------

  /**
   * Build column config for the Characters DataTable.
   * @param {object} context — {starredSet, activeTab}
   * @returns {Array}
   */
  function _characterColumns(context) {
    return [
      {
        key:      "name",
        label:    "Name",
        sortable: true,
        linkTo:   function (row) {
          return "#/world/characters/" + encodeURIComponent(row.id || "");
        },
      },
      {
        key:    "detail_level",
        label:  "Type",
        width:  "70px",
        render: function (val) {
          if (val === "full") {
            return '<mark class="world-dt-badge world-dt-badge--pc">PC</mark>';
          }
          return '<mark class="world-dt-badge world-dt-badge--npc">NPC</mark>';
        },
      },
      {
        key:        "description",
        label:      "Description",
        hideMobile: false,
        render:     function (val) {
          return window.utils.esc(window.utils.snippet(val || "", 120));
        },
      },
      {
        key:    "_star",
        label:  "",
        width:  "44px",
        render: function (val, row) {
          var type = "character";
          var id = row.id || "";
          var key = type + "/" + id;
          var starred = !!(context.starredSet && context.starredSet[key]);
          var icon = starred ? "\u2605" : "\u2606"; // ★ or ☆
          var label = starred ? "Unstar " + (row.name || "") : "Star " + (row.name || "");
          return (
            '<button class="world-dt-star-btn"' +
            '        data-star-type="' + window.utils.esc(type) + '"' +
            '        data-star-id="' + window.utils.esc(id) + '"' +
            '        data-starred="' + (starred ? "true" : "false") + '"' +
            '        aria-label="' + window.utils.esc(label) + '"' +
            '        aria-pressed="' + (starred ? "true" : "false") + '">' +
              icon +
            '</button>'
          );
        },
      },
    ];
  }

  /**
   * Build column config for the Groups DataTable.
   * @param {object} context — {starredSet}
   * @returns {Array}
   */
  function _groupColumns(context) {
    return [
      {
        key:      "name",
        label:    "Name",
        sortable: true,
        linkTo:   function (row) {
          return "#/world/groups/" + encodeURIComponent(row.id || "");
        },
      },
      {
        key:    "tier",
        label:  "Tier",
        width:  "70px",
        render: function (val) {
          if (val === null || val === undefined || val === "") return "";
          return '<mark class="world-dt-badge world-dt-badge--tier">Tier ' + window.utils.esc(String(val)) + '</mark>';
        },
      },
      {
        key:        "description",
        label:      "Description",
        hideMobile: false,
        render:     function (val) {
          return window.utils.esc(window.utils.snippet(val || "", 120));
        },
      },
      {
        key:    "_star",
        label:  "",
        width:  "44px",
        render: function (val, row) {
          var type = "group";
          var id = row.id || "";
          var key = type + "/" + id;
          var starred = !!(context.starredSet && context.starredSet[key]);
          var icon = starred ? "\u2605" : "\u2606";
          var label = starred ? "Unstar " + (row.name || "") : "Star " + (row.name || "");
          return (
            '<button class="world-dt-star-btn"' +
            '        data-star-type="' + window.utils.esc(type) + '"' +
            '        data-star-id="' + window.utils.esc(id) + '"' +
            '        data-starred="' + (starred ? "true" : "false") + '"' +
            '        aria-label="' + window.utils.esc(label) + '"' +
            '        aria-pressed="' + (starred ? "true" : "false") + '">' +
              icon +
            '</button>'
          );
        },
      },
    ];
  }

  /**
   * Build column config for the Locations DataTable.
   * @param {object} context — {starredSet}
   * @returns {Array}
   */
  function _locationColumns(context) {
    return [
      {
        key:      "name",
        label:    "Name",
        sortable: true,
        linkTo:   function (row) {
          return "#/world/locations/" + encodeURIComponent(row.id || "");
        },
      },
      {
        key:    "parent_name",
        label:  "Parent",
        width:  "150px",
        render: function (val) {
          if (!val) return '<span class="text-muted">—</span>';
          return window.utils.esc(String(val));
        },
      },
      {
        key:        "description",
        label:      "Description",
        hideMobile: false,
        render:     function (val) {
          return window.utils.esc(window.utils.snippet(val || "", 120));
        },
      },
      {
        key:    "_star",
        label:  "",
        width:  "44px",
        render: function (val, row) {
          var type = "location";
          var id = row.id || "";
          var key = type + "/" + id;
          var starred = !!(context.starredSet && context.starredSet[key]);
          var icon = starred ? "\u2605" : "\u2606";
          var label = starred ? "Unstar " + (row.name || "") : "Star " + (row.name || "");
          return (
            '<button class="world-dt-star-btn"' +
            '        data-star-type="' + window.utils.esc(type) + '"' +
            '        data-star-id="' + window.utils.esc(id) + '"' +
            '        data-starred="' + (starred ? "true" : "false") + '"' +
            '        aria-label="' + window.utils.esc(label) + '"' +
            '        aria-pressed="' + (starred ? "true" : "false") + '">' +
              icon +
            '</button>'
          );
        },
      },
    ];
  }

  // ---------------------------------------------------------------------------
  // Module-level DataTable instances (destroyed and re-created on tab switch)
  // ---------------------------------------------------------------------------

  var _currentTable = null;

  /**
   * Destroy the current DataTable instance and clear the container.
   */
  function _destroyTable() {
    if (_currentTable) {
      _currentTable.destroy();
      _currentTable = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Star / unstar handler (DataTable version)
  // ---------------------------------------------------------------------------

  /**
   * Wire star button click handlers within a DataTable container.
   * Uses event delegation on the container.
   *
   * @param {HTMLElement} container — the DataTable's container element
   * @param {object}      data      — Alpine data object (for _starredSet)
   * @param {string}      tab       — current tab ("characters"|"groups"|"locations")
   * @param {string}      charSubTab — current character sub-tab (if tab=characters)
   */
  function _bindDtStarClicks(container, data, tab, charSubTab) {
    container.addEventListener("click", function (evt) {
      var btn = evt.target.closest
        ? evt.target.closest("[data-star-id]")
        : null;
      if (!btn) return;
      evt.stopPropagation();

      var cardType = btn.getAttribute("data-star-type");
      var cardId   = btn.getAttribute("data-star-id");
      var starred  = btn.getAttribute("data-starred") === "true";

      _handleDtStar(data, container, tab, charSubTab, cardType, cardId, starred);
    });
  }

  /**
   * Handle a star button click inside a DataTable row.
   * Applies optimistic UI immediately, calls the API, reverts on failure.
   *
   * @param {object}  data         — Alpine data object
   * @param {HTMLElement} container — DataTable container
   * @param {string}  tab          — current main tab
   * @param {string}  charSubTab   — current character sub-tab
   * @param {string}  cardType     — "character" | "group" | "location"
   * @param {string}  cardId       — object ULID
   * @param {boolean} currentlyStarred — true if currently starred
   */
  function _handleDtStar(data, container, tab, charSubTab, cardType, cardId, currentlyStarred) {
    var key = cardType + "/" + cardId;

    // Find the specific button in the container
    var btn = container.querySelector(
      '[data-star-type="' + cardType + '"][data-star-id="' + cardId + '"]'
    );

    if (currentlyStarred) {
      // Unstar — optimistic
      if (btn) {
        btn.textContent = "\u2606"; // ☆
        btn.setAttribute("data-starred", "false");
        btn.setAttribute("aria-pressed", "false");
      }
      delete data._starredSet[key];

      api
        .del("/api/v1/me/starred/" + encodeURIComponent(cardType) + "/" + encodeURIComponent(cardId))
        .catch(function () {
          // Revert
          data._starredSet[key] = true;
          if (btn) {
            btn.textContent = "\u2605"; // ★
            btn.setAttribute("data-starred", "true");
            btn.setAttribute("aria-pressed", "true");
          }
        });
    } else {
      // Star — optimistic
      if (btn) {
        btn.textContent = "\u2605"; // ★
        btn.setAttribute("data-starred", "true");
        btn.setAttribute("aria-pressed", "true");
      }
      data._starredSet[key] = true;

      api
        .post("/api/v1/me/starred", { type: cardType, id: cardId })
        .catch(function () {
          // Revert
          delete data._starredSet[key];
          if (btn) {
            btn.textContent = "\u2606"; // ☆
            btn.setAttribute("data-starred", "false");
            btn.setAttribute("aria-pressed", "false");
          }
        });
    }
  }

  // ---------------------------------------------------------------------------
  // DataTable renderer (for character/group/location tabs)
  // ---------------------------------------------------------------------------

  /**
   * Create (or recreate) the DataTable for a non-story tab.
   * Wires row-click navigation and star button delegation.
   *
   * @param {object} data     — Alpine data object
   * @param {string} tab      — "characters" | "groups" | "locations"
   * @param {string} charSubTab — "all" | "pc" | "npc" (only used when tab=characters)
   */
  function _renderDataTable(data, tab, charSubTab) {
    _destroyTable();

    var container = document.getElementById("world-dt-container");
    if (!container) return;

    var context = { starredSet: data._starredSet || {} };
    var colsFn, type;

    if (tab === "characters") {
      colsFn = _characterColumns;
      type   = "character";
    } else if (tab === "groups") {
      colsFn = _groupColumns;
      type   = "group";
    } else if (tab === "locations") {
      colsFn = _locationColumns;
      type   = "location";
    } else {
      return;
    }

    var columns = colsFn(context);

    var table = new window.components.DataTable(container, {
      columns:      columns,
      emptyMessage: "No " + tab + " found.",
      onRowClick:   function (row) {
        var hash = "#/world/" + tab + "/" + encodeURIComponent(row.id || "");
        if (typeof router !== "undefined") {
          router.navigate(hash);
        } else {
          window.location.hash = hash;
        }
      },
    });

    _currentTable = table;

    // Wire star button delegation on the container
    _bindDtStarClicks(container, data, tab, charSubTab);

    // Determine which rows to show based on sub-tab
    var rows = _getTabRows(data, tab, charSubTab);

    if (data.loaded[tab] === "loading" || data.loaded[tab] === false) {
      table.setLoading(true);
    } else if (data.loaded[tab] === "done") {
      table.setRows(rows);
    }
    // If error, show nothing (error is displayed above the table)
  }

  /**
   * Get the rows for a given tab/sub-tab combination.
   * For characters, applies the sub-tab filter client-side.
   *
   * @param {object} data
   * @param {string} tab
   * @param {string} charSubTab
   * @returns {Array}
   */
  function _getTabRows(data, tab, charSubTab) {
    var all = data[tab] || [];
    if (tab !== "characters" || charSubTab === "all") {
      return all;
    }
    if (charSubTab === "pc") {
      return all.filter(function (r) { return r.detail_level === "full"; });
    }
    if (charSubTab === "npc") {
      return all.filter(function (r) { return r.detail_level === "simplified"; });
    }
    return all;
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
      activeTab:    "characters",
      charSubTab:   "all",  // "all" | "pc" | "npc"

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
      loading: false,
      error:   null,

      // ---- Starred state ---------------------------------------------------
      _starredSet: {},

      // ---- Render debounce timer --------------------------------------------
      _renderTimer: null,

      // ---- Tab switching ---------------------------------------------------

      /**
       * Switch to a main tab, fetching data if not yet loaded.
       * @param {string} tab — "characters" | "groups" | "locations" | "stories"
       */
      switchTab: function (tab) {
        var self = this;
        self.error = null;
        self.activeTab = tab;
        self._fetchIfNeeded(tab);
        self._scheduleRender();
      },

      /**
       * Switch the character sub-tab.
       * @param {string} sub — "all" | "pc" | "npc"
       */
      switchCharSubTab: function (sub) {
        var self = this;
        self.charSubTab = sub;
        self._scheduleRender();
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
       * @param {string} tab
       */
      _fetchData: function (tab) {
        var self   = this;
        var urlMap = {
          characters: "/api/v1/characters",
          groups:     "/api/v1/groups",
          locations:  "/api/v1/locations",
          stories:    "/api/v1/stories",
        };
        var url = urlMap[tab];
        if (!url) return;

        // Characters: fetch all (both PC and NPC) in one request.
        // Sub-tab filtering is done client-side.
        var params = "?sort_by=name&sort_dir=asc";
        if (tab === "characters") {
          // No detail_level filter — fetch all, sub-tabs filter client-side.
          params = "?sort_by=name&sort_dir=asc";
        }

        self.loaded[tab] = "loading";
        self.loading     = (self.activeTab === tab);
        self.error       = null;

        api
          .get(url + params)
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
            self._scheduleRender();
          });
      },

      /**
       * Debounce a re-render call via setTimeout so rapid successive calls
       * coalesce into a single render after Alpine has updated state.
       */
      _scheduleRender: function () {
        var self = this;
        clearTimeout(self._renderTimer);
        self._renderTimer = setTimeout(function () {
          _renderContent(self);
        }, 0);
      },

      // ---- Lifecycle -------------------------------------------------------

      /**
       * Called by Alpine when this x-data component initialises.
       * Loads starred objects, then triggers the initial Characters fetch.
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
            self._starredSet = {};
          })
          .finally(function () {
            self._fetchIfNeeded("characters");
          });
      },
    };
  }

  // ---------------------------------------------------------------------------
  // Content renderer (dispatches to DataTable or story cards)
  // ---------------------------------------------------------------------------

  /**
   * Render the content area for the active tab.
   * For Characters, Groups, Locations: create/update a DataTable.
   * For Stories: render custom story cards.
   *
   * @param {object} data — Alpine data object
   */
  function _renderContent(data) {
    var tab = data.activeTab;

    if (tab === "stories") {
      _destroyTable();
      _renderStoryCards(data);
      return;
    }

    // Characters sub-tab bar visibility
    var subTabBar = document.getElementById("world-char-sub-tabs");
    if (subTabBar) {
      subTabBar.style.display = (tab === "characters") ? "" : "none";
    }

    // DataTable-based tabs
    var container = document.getElementById("world-dt-container");
    if (!container) return;

    // If we have an existing table and data is already loaded, just update rows
    if (_currentTable && data.loaded[tab] === "done") {
      var rows = _getTabRows(data, tab, data.charSubTab);
      _currentTable.setRows(rows);
      return;
    }

    // Otherwise rebuild the table (tab changed or table was destroyed)
    _renderDataTable(data, tab, data.charSubTab);
  }

  // ---------------------------------------------------------------------------
  // Story card builder (unchanged from original)
  // ---------------------------------------------------------------------------

  /**
   * Render story cards into #world-story-cards.
   * @param {object} data — Alpine data object
   */
  function _renderStoryCards(data) {
    var container = document.getElementById("world-story-cards");
    if (!container) return;

    var tab   = "stories";
    var items = data.stories || [];

    if (data.loaded[tab] === "loading" || data.loaded[tab] === false) {
      container.innerHTML = "";
      return;
    }
    if (data.loaded[tab] === "error") {
      container.innerHTML = "";
      return;
    }
    if (items.length === 0) {
      container.innerHTML = '<p class="world-empty">No stories found.</p>';
      return;
    }

    var html = [];
    for (var i = 0; i < items.length; i++) {
      html.push(_renderStoryCard(items[i]));
    }
    container.innerHTML = html.join("");
    _bindStoryClicks(container);
  }

  /**
   * Render a single story card as an HTML string.
   * @param {object} story — StoryResponse from the API
   * @returns {string} HTML
   */
  function _renderStoryCard(story) {
    var id      = story.id || "";
    var name    = story.name || "Untitled";
    var status  = story.status || "active";
    var tags    = story.tags || [];
    var summary = window.utils.snippet(story.summary || story.description || "", 120);
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
        tagParts.push('<span class="world-story-card__tag">' + window.utils.esc(tags[i]) + '</span>');
      }
      tagHtml = '<div class="world-story-card__tags">' + tagParts.join("") + "</div>";
    }

    return (
      '<article class="world-story-card world-story-card--' + window.utils.esc(statusMod) + '"' +
               ' data-story-id="' + window.utils.esc(id) + '"' +
               ' data-story-hash="' + window.utils.esc(hash) + '"' +
               ' role="button"' +
               ' tabindex="0"' +
               ' aria-label="' + window.utils.esc(name) + '">' +
        '<header class="world-story-card__header">' +
          '<strong class="world-story-card__name">' + window.utils.esc(name) + '</strong>' +
          '<mark class="world-story-card__status world-story-card__status--' + window.utils.esc(statusMod) + '">' +
            window.utils.esc(status) +
          '</mark>' +
        '</header>' +
        (tagHtml) +
        (summary
          ? '<p class="world-story-card__summary">' + window.utils.esc(summary) + '</p>'
          : '') +
      '</article>'
    );
  }

  /**
   * Wire click and keyboard navigation handlers for story cards.
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
   * Build the static HTML scaffold for the game objects browser.
   * Alpine directives handle tab switching and loading/error states.
   * The DataTable and story cards are rendered imperatively.
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
                ' @click="switchTab(\'' + t.key + '\')"' +
                ' :aria-current="activeTab === \'' + t.key + '\' ? \'page\' : undefined"' +
                ' aria-label="' + window.utils.esc(t.label) + ' tab">' +
          window.utils.esc(t.label) +
        '</button>'
      );
    }).join("\n");

    // Character sub-tabs: All | PCs | NPCs
    var subTabs = [
      { key: "all", label: "All" },
      { key: "pc",  label: "PCs" },
      { key: "npc", label: "NPCs" },
    ];

    var subTabHtml = subTabs.map(function (s) {
      return (
        '<button class="world-sub-tab"' +
                ' :class="{ \'world-sub-tab--active\': charSubTab === \'' + s.key + '\' }"' +
                ' @click="switchCharSubTab(\'' + s.key + '\')"' +
                ' :aria-pressed="charSubTab === \'' + s.key + '\'">' +
          window.utils.esc(s.label) +
        '</button>'
      );
    }).join("\n");

    return [
      '<div id="world-root" x-data="worldData">',

      '  <h2 class="world-heading">Game Objects</h2>',

      // Main tab bar
      '  <nav class="world-tabs" role="tablist" aria-label="Game Objects categories">',
      tabHtml,
      '  </nav>',

      // Character sub-tabs (shown only when Characters tab is active)
      '  <nav id="world-char-sub-tabs"',
      '       class="world-sub-tabs"',
      '       role="tablist"',
      '       aria-label="Character type filter"',
      '       x-show="activeTab === \'characters\'">',
      subTabHtml,
      '  </nav>',

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

      // DataTable container — used for Characters, Groups, Locations
      '  <div id="world-dt-container"',
      '       class="world-dt-container"',
      '       x-show="activeTab !== \'stories\'"',
      '       x-ignore>',
      '  </div>',

      // Story cards container — used for Stories tab
      '  <div id="world-story-cards"',
      '       class="world-card-list"',
      '       x-show="activeTab === \'stories\'"',
      '       x-ignore',
      '       role="list"',
      '       aria-label="Stories">',
      '  </div>',

      '</div>', // end #world-root
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // Render (public entry point)
  // ---------------------------------------------------------------------------

  /**
   * Mount the game objects browser into #view.
   * Registers the Alpine data component, initialises the Alpine subtree.
   */
  return function render() {
    var el = document.getElementById("view");
    if (!el) return;

    // Destroy any previous DataTable instance before re-rendering
    _destroyTable();

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
