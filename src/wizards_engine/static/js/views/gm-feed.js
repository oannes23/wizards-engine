/* Wizards Engine — GM Event Feed view (DataTable)
 *
 * Replaces the card-based FeedList for GM feed routes with a rich,
 * sortable, filterable DataTable.
 *
 * Routes:
 *   #/gm/feed         — Full GM event feed (Full tab)
 *   #/gm/feed/silent  — Silent/bookkeeping events (Silent tab)
 *
 * API endpoints consumed:
 *   GET /api/v1/me/feed         — full feed (GMs see everything)
 *   GET /api/v1/me/feed/silent  — GM-only silent events
 *
 * Features:
 *   - Category filter tabs: All | Events | Story Entries | Proposals
 *   - Per-tab (Full/Silent) via secondary tab bar
 *   - Actor type dropdown filter (Player / GM / System)
 *   - Session dropdown filter (populated from session_id values in loaded data)
 *   - Global text search (DataTable built-in)
 *   - Sortable columns: Timestamp, Actor, Event Type
 *   - Actor name link → #/gm/world/characters/{actor_id}
 *   - Target name link → #/gm/world/{target_type}/{target_id}
 *   - Source type badges: Event / Story / Proposal
 *   - Cursor-based "Load more" button
 *
 * Registers:
 *   window.views.gmFeed        — GM full feed (#/gm/feed)
 *   window.views.gmFeedSilent  — GM silent feed (#/gm/feed/silent)
 *
 * Dependencies (must already be loaded):
 *   utils.js, api.js, store.js, data-table.js
 */

window.views = window.views || {};

(function () {
  // --------------------------------------------------------------------------
  // Constants
  // --------------------------------------------------------------------------

  var FEED_URL    = "/api/v1/me/feed";
  var SILENT_URL  = "/api/v1/me/feed/silent";
  var LIMIT       = 30;

  /** Human-readable event type labels — copied from feed-item.js. */
  var EVENT_TYPE_LABELS = {
    "proposal.approved":                  "proposal approved",
    "proposal.rejected":                  "proposal rejected",
    "proposal.revised":                   "proposal revised",
    "character.stress_changed":           "stress changed",
    "character.gnosis_changed":           "gnosis changed",
    "character.meter_updated":            "meter updated",
    "character.skill_changed":            "skill changed",
    "character.magic_stat_changed":       "magic stat changed",
    "character.updated":                  "character updated",
    "character.resolve_trauma_generated": "trauma resolution pending",
    "session.started":                    "session started",
    "session.ended":                      "session ended",
    "session.ft_distributed":             "free time distributed",
    "session.plot_distributed":           "plot points distributed",
    "session.participant_added":          "participant added",
    "clock.advanced":                     "clock advanced",
    "clock.resolve_generated":            "clock resolution pending",
    "bond.created":                       "bond created",
    "bond.charges_changed":               "bond charges changed",
    "bond.updated":                       "bond updated",
    "bond.retired":                       "bond retired",
    "trait.created":                      "trait created",
    "trait.recharged":                    "trait recharged",
    "trait.updated":                      "trait updated",
    "trait.retired":                      "trait retired",
    "magic.effect_created":               "effect created",
    "magic.effect_charged":               "effect charged",
    "magic.effect_updated":               "effect updated",
    "magic.effect_retired":               "effect retired",
    "group.updated":                      "group updated",
    "location.updated":                   "location updated",
  };

  // Type-to-plural path segment for link building.
  var TYPE_TO_PATH = {
    character: "characters",
    group:     "groups",
    location:  "locations",
  };

  // Category tabs above the table.
  var CATEGORY_TABS = [
    { key: "all",     label: "All"           },
    { key: "event",   label: "Events"        },
    { key: "story",   label: "Story Entries" },
    { key: "proposal",label: "Proposals"     },
  ];

  // Actor type filter options.
  var ACTOR_TYPE_OPTIONS = [
    { value: "",       label: "All Actors" },
    { value: "player", label: "Player"     },
    { value: "gm",     label: "GM"         },
    { value: "system", label: "System"     },
  ];

  // --------------------------------------------------------------------------
  // Module-level state
  // --------------------------------------------------------------------------

  /** The DataTable instance, or null when unmounted. */
  var _dt = null;

  /** All loaded rows (across all pages). */
  var _allRows = [];

  /** Pagination state. */
  var _nextCursor = null;
  var _hasMore    = false;
  var _loading    = false;

  /** Currently active URL (full or silent). */
  var _baseUrl = null;

  /** Active category filter (matches CATEGORY_TABS key). */
  var _category = "all";

  /** Active actor type filter. */
  var _actorType = "";

  /** Active session ID filter. */
  var _sessionId = "";

  /** Whether the view is mounted. */
  var _mounted = false;

  /** Set of hash strings belonging to this view family. */
  var _ownHashes = ["#/gm/feed", "#/gm/feed/silent"];

  // --------------------------------------------------------------------------
  // Helpers
  // --------------------------------------------------------------------------
  var _rel = function (s) { return window.utils.relativeTime(s); };

  /**
   * Resolve a human-readable label for an event_type string.
   * @param {string} et
   * @returns {string}
   */
  function _eventLabel(et) {
    if (EVENT_TYPE_LABELS[et]) return EVENT_TYPE_LABELS[et];
    return String(et || "—").replace(/[._]/g, " ");
  }

  /**
   * Map an actor_type and actor_id to a display name string.
   * Uses actor_name from enriched API when present.
   * @param {object} item
   * @returns {string}
   */
  function _actorName(item) {
    if (item.actor_name) return item.actor_name;
    var t = item.actor_type || "";
    if (t === "system") return "System";
    if (t === "gm")     return "GM";
    return "Player";
  }

  /**
   * Build an actor cell HTML string — linked to character detail when actor_id present.
   * @param {object} item
   * @returns {string}
   */
  function _actorCell(item) {
    var name = _actorName(item);
    if (item.actor_id && item.actor_type !== "system") {
      return '<a href="#/gm/world/characters/' + window.utils.esc(item.actor_id) + '" class="gm-feed__link">' + window.utils.esc(name) + '</a>';
    }
    return window.utils.esc(name);
  }

  /**
   * Build a primary target cell HTML string.
   * Uses primary_target_name from enriched API when present.
   * Falls back to deriving from targets array.
   * @param {object} item
   * @returns {string}
   */
  function _targetCell(item) {
    // Enriched API fields (Story 8.3.1).
    if (item.primary_target_name && item.primary_target_id && item.primary_target_type) {
      var pathSeg = TYPE_TO_PATH[item.primary_target_type] || (item.primary_target_type + "s");
      return '<a href="#/gm/world/' + window.utils.esc(pathSeg) + '/' + window.utils.esc(item.primary_target_id) + '" class="gm-feed__link">' +
        window.utils.esc(item.primary_target_name) + '</a>';
    }

    // Fall back to targets array.
    var targets = item.targets || [];
    if (!targets.length) return '<span class="dt-null">—</span>';

    // Find primary target (is_primary === true), or use first.
    var primary = null;
    for (var i = 0; i < targets.length; i++) {
      if (targets[i].is_primary || targets[i].is_primary === undefined) {
        primary = targets[i];
        break;
      }
    }
    if (!primary) primary = targets[0];

    var type = primary.target_type || primary.type || "object";
    var id   = primary.target_id   || primary.id   || "";
    var pathSeg2 = TYPE_TO_PATH[type] || (type + "s");
    var label = type;

    if (id) {
      return '<a href="#/gm/world/' + window.utils.esc(pathSeg2) + '/' + window.utils.esc(id) + '" class="gm-feed__link">' + window.utils.esc(label) + '</a>';
    }
    return window.utils.esc(label);
  }

  /**
   * Build the changes summary cell.
   * Uses changes_summary from enriched API when present.
   * Falls back to deriving from changes object.
   * @param {object} item
   * @returns {string}
   */
  function _changesCell(item) {
    // Enriched API field (Story 8.3.1).
    if (item.changes_summary) {
      return '<span class="gm-feed__changes" title="' + window.utils.esc(item.changes_summary) + '">' +
        window.utils.esc(item.changes_summary.length > 60 ? item.changes_summary.slice(0, 57) + "..." : item.changes_summary) +
        '</span>';
    }

    // Derive from changes dict.
    var changes = item.changes;
    if (!changes || typeof changes !== "object" || !Object.keys(changes).length) {
      return '<span class="dt-null">—</span>';
    }
    var parts = [];
    for (var k in changes) {
      if (!changes.hasOwnProperty(k)) continue;
      var ch = changes[k];
      if (ch && typeof ch === "object" && "before" in ch && "after" in ch) {
        parts.push(k + ": " + ch.before + " \u2192 " + ch.after);
      } else {
        parts.push(k);
      }
    }
    var summary = parts.join(", ");
    return '<span class="gm-feed__changes" title="' + window.utils.esc(summary) + '">' +
      window.utils.esc(summary.length > 60 ? summary.slice(0, 57) + "..." : summary) +
      '</span>';
  }

  /**
   * Build a source-type badge HTML string.
   * @param {object} item
   * @returns {string}
   */
  function _sourceTypeBadge(item) {
    var sourceType = item._source_type || "event";
    var label = sourceType === "story_entry" ? "Story" : sourceType === "proposal" ? "Proposal" : "Event";
    var mod   = sourceType === "story_entry" ? "story" : sourceType === "proposal" ? "proposal" : "event";
    return '<span class="gm-feed__badge gm-feed__badge--' + window.utils.esc(mod) + '">' + window.utils.esc(label) + '</span>';
  }

  /**
   * Build the narrative cell — truncated with full text on hover.
   * @param {object} item
   * @returns {string}
   */
  function _narrativeCell(item) {
    var text = item.narrative || item.entry_text || "";
    if (!text) return '<span class="dt-null">—</span>';
    var short = text.length > 80 ? text.slice(0, 77) + "..." : text;
    return '<span class="gm-feed__narrative" title="' + window.utils.esc(text) + '">' + window.utils.esc(short) + '</span>';
  }

  // --------------------------------------------------------------------------
  // Data normalization
  // --------------------------------------------------------------------------

  /**
   * Normalize a raw feed item into a flat row object for the DataTable.
   * Adds computed fields used by column renderers.
   * @param {object} item
   * @returns {object}
   */
  function _normalizeItem(item) {
    var type = item.type || "event";

    // Determine source_type for category filtering.
    var sourceType;
    if (type === "story_entry") {
      sourceType = "story_entry";
    } else if (item.event_type && item.event_type.startsWith("proposal.")) {
      sourceType = "proposal";
    } else {
      sourceType = "event";
    }

    return {
      id:             item.id,
      // Sort/filter keys
      _timestamp:     item.timestamp || item.created_at || "",
      _actor_type:    item.actor_type || "",
      _event_type:    item.event_type || (type === "story_entry" ? "story_entry" : ""),
      _source_type:   sourceType,
      _session_id:    item.session_id || "",
      // Display values
      actor_id:       item.actor_id || null,
      actor_name:     item.actor_name || null,
      actor_type:     item.actor_type || null,
      primary_target_id:   item.primary_target_id   || null,
      primary_target_name: item.primary_target_name || null,
      primary_target_type: item.primary_target_type || null,
      targets:        item.targets || [],
      changes:        item.changes || {},
      changes_summary: item.changes_summary || null,
      narrative:      item.narrative || item.entry_text || null,
      // Pass-through for renderers
      _raw: item,
    };
  }

  // --------------------------------------------------------------------------
  // DataTable column definitions
  // --------------------------------------------------------------------------

  /**
   * Build the column definitions array for the DataTable.
   * @returns {Array}
   */
  function _buildColumns() {
    return [
      {
        key:      "_timestamp",
        label:    "When",
        sortable: true,
        width:    "90px",
        render: function (val) {
          if (!val) return '<span class="dt-null">—</span>';
          return (
            '<time datetime="' + window.utils.esc(val) + '" title="' + window.utils.esc(val) + '">' +
            window.utils.esc(_rel(val)) +
            '</time>'
          );
        },
      },
      {
        key:   "_source_type",
        label: "Source",
        width: "80px",
        render: function (val, row) {
          return _sourceTypeBadge(row);
        },
      },
      {
        key:      "actor_id",
        label:    "Actor",
        sortable: true,
        width:    "110px",
        render: function (val, row) {
          return _actorCell(row);
        },
      },
      {
        key:      "_event_type",
        label:    "Event Type",
        sortable: true,
        width:    "130px",
        render: function (val) {
          if (!val) return '<span class="dt-null">—</span>';
          return window.utils.esc(_eventLabel(val));
        },
      },
      {
        key:   "primary_target_id",
        label: "Target",
        width: "110px",
        render: function (val, row) {
          return _targetCell(row);
        },
      },
      {
        key:   "changes_summary",
        label: "Changes",
        render: function (val, row) {
          return _changesCell(row);
        },
        hideMobile: true,
      },
      {
        key:   "narrative",
        label: "Narrative",
        render: function (val, row) {
          return _narrativeCell(row);
        },
        hideMobile: true,
      },
    ];
  }

  // --------------------------------------------------------------------------
  // Filter application (category + actor type + session)
  // --------------------------------------------------------------------------

  /**
   * Return the subset of _allRows that pass the active category,
   * actor-type, and session filters.
   * @returns {Array}
   */
  function _filteredRows() {
    return _allRows.filter(function (row) {
      // Category filter.
      if (_category !== "all") {
        if (_category === "event"   && row._source_type !== "event")       return false;
        if (_category === "story"   && row._source_type !== "story_entry") return false;
        if (_category === "proposal"&& row._source_type !== "proposal")    return false;
      }
      // Actor type filter.
      if (_actorType && row._actor_type !== _actorType) return false;
      // Session filter.
      if (_sessionId && row._session_id !== _sessionId) return false;
      return true;
    });
  }

  // --------------------------------------------------------------------------
  // Shell HTML rendering
  // --------------------------------------------------------------------------

  /**
   * Build the tab bar for Full / Silent toggle.
   * @param {string} activeKey — 'full' | 'silent'
   * @returns {string}
   */
  function _buildViewTabs(activeKey) {
    var tabs = [
      { key: "full",   label: "Full",   hash: "#/gm/feed" },
      { key: "silent", label: "Silent", hash: "#/gm/feed/silent" },
    ];
    var html = '<nav class="feed-tabs" role="tablist" aria-label="Feed type">';
    for (var i = 0; i < tabs.length; i++) {
      var t = tabs[i];
      var active = t.key === activeKey;
      html +=
        '<a href="' + window.utils.esc(t.hash) + '"' +
        '   class="feed-tab' + (active ? ' feed-tab--active' : '') + '"' +
        '   role="tab" aria-selected="' + (active ? 'true' : 'false') + '">' +
        window.utils.esc(t.label) +
        '</a>';
    }
    html += '</nav>';
    return html;
  }

  /**
   * Build the category tab bar HTML.
   * @returns {string}
   */
  function _buildCategoryTabs() {
    var html = '<div class="gm-feed__category-tabs" role="tablist" aria-label="Category filter">';
    for (var i = 0; i < CATEGORY_TABS.length; i++) {
      var t = CATEGORY_TABS[i];
      var active = t.key === _category;
      html +=
        '<button class="gm-feed__cat-tab' + (active ? ' gm-feed__cat-tab--active' : '') + '"' +
        '   role="tab"' +
        '   aria-selected="' + (active ? 'true' : 'false') + '"' +
        '   data-category="' + window.utils.esc(t.key) + '">' +
        window.utils.esc(t.label) +
        '</button>';
    }
    html += '</div>';
    return html;
  }

  /**
   * Build the additional filter controls row (actor type + session).
   * @returns {string}
   */
  function _buildExtraFilters() {
    // Collect distinct session IDs from all rows.
    var sessions = {};
    for (var i = 0; i < _allRows.length; i++) {
      var sid = _allRows[i]._session_id;
      if (sid) sessions[sid] = true;
    }
    var sessionIds = Object.keys(sessions).sort();

    var html = '<div class="gm-feed__extra-filters">';

    // Actor type dropdown.
    html += '<select class="dt-select gm-feed__actor-filter" aria-label="Filter by actor type">';
    for (var a = 0; a < ACTOR_TYPE_OPTIONS.length; a++) {
      var opt = ACTOR_TYPE_OPTIONS[a];
      html += '<option value="' + window.utils.esc(opt.value) + '"' +
        (opt.value === _actorType ? ' selected' : '') + '>' +
        window.utils.esc(opt.label) + '</option>';
    }
    html += '</select>';

    // Session dropdown (only if there are sessions).
    if (sessionIds.length > 0) {
      html += '<select class="dt-select gm-feed__session-filter" aria-label="Filter by session">';
      html += '<option value="">All Sessions</option>';
      for (var s = 0; s < sessionIds.length; s++) {
        var sid2 = sessionIds[s];
        html += '<option value="' + window.utils.esc(sid2) + '"' +
          (sid2 === _sessionId ? ' selected' : '') + '>' +
          'Session ' + window.utils.esc(sid2.slice(0, 8)) + '</option>';
      }
      html += '</select>';
    }

    html += '</div>';
    return html;
  }

  /**
   * Build the "Load more" button HTML.
   * @returns {string}
   */
  function _buildLoadMore() {
    if (!_hasMore && !_loading) return "";
    return (
      '<div class="gm-feed__load-more">' +
        '<button id="gm-feed-load-more" class="outline secondary"' +
        (_loading ? ' aria-busy="true" disabled' : '') + '>' +
        (_loading ? 'Loading...' : 'Load more') +
        '</button>' +
      '</div>'
    );
  }

  // --------------------------------------------------------------------------
  // Full view mount / update
  // --------------------------------------------------------------------------

  /** Outer #view element. */
  var _viewEl = null;

  /** Container for the DataTable. */
  var _tableContainerEl = null;

  /** Container for the extra filters row. */
  var _extraFiltersEl = null;

  /** Container for the load-more button. */
  var _loadMoreEl = null;

  /** Container for the category tabs. */
  var _categoryTabsEl = null;

  /**
   * Render the full view shell. Called once on mount.
   * @param {string} activeViewTab — 'full' | 'silent'
   */
  function _mountShell(activeViewTab) {
    if (!_viewEl) return;

    _viewEl.innerHTML =
      '<div class="gm-feed">' +
        '<hgroup>' +
          '<h2 class="gm-feed__heading">GM Event Feed</h2>' +
          '<p class="gm-feed__subheading">Sortable, filterable audit log</p>' +
        '</hgroup>' +
        _buildViewTabs(activeViewTab) +
        '<div id="gm-feed-category-tabs"></div>' +
        '<div id="gm-feed-extra-filters"></div>' +
        '<div id="gm-feed-table-container"></div>' +
        '<div id="gm-feed-load-more-container"></div>' +
      '</div>';

    _tableContainerEl  = document.getElementById("gm-feed-table-container");
    _extraFiltersEl    = document.getElementById("gm-feed-extra-filters");
    _loadMoreEl        = document.getElementById("gm-feed-load-more-container");
    _categoryTabsEl    = document.getElementById("gm-feed-category-tabs");

    // Create DataTable.
    if (_tableContainerEl) {
      _dt = new window.components.DataTable(_tableContainerEl, {
        columns:      _buildColumns(),
        onRowClick:   _onRowClick,
        emptyMessage: "No events match the current filters.",
      });
    }
  }

  /**
   * Update the dynamic regions (category tabs, extra filters, load-more, table rows).
   * Called after every load / filter change without rebuilding the shell.
   */
  function _update() {
    if (!_mounted) return;

    if (_categoryTabsEl) {
      _categoryTabsEl.innerHTML = _buildCategoryTabs();
      _wireCategoryTabs();
    }

    if (_extraFiltersEl) {
      _extraFiltersEl.innerHTML = _buildExtraFilters();
      _wireExtraFilters();
    }

    if (_loadMoreEl) {
      _loadMoreEl.innerHTML = _buildLoadMore();
      _wireLoadMore();
    }

    if (_dt) {
      _dt.setRows(_filteredRows());
    }
  }

  // --------------------------------------------------------------------------
  // Event wiring
  // --------------------------------------------------------------------------

  /**
   * Wire category tab button click listeners.
   */
  function _wireCategoryTabs() {
    if (!_categoryTabsEl) return;
    var btns = _categoryTabsEl.querySelectorAll("[data-category]");
    for (var i = 0; i < btns.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          _category = btn.getAttribute("data-category");
          _update();
        });
      })(btns[i]);
    }
  }

  /**
   * Wire actor type and session filter change listeners.
   */
  function _wireExtraFilters() {
    if (!_extraFiltersEl) return;

    var actorEl = _extraFiltersEl.querySelector(".gm-feed__actor-filter");
    if (actorEl) {
      actorEl.addEventListener("change", function () {
        _actorType = actorEl.value;
        _update();
      });
    }

    var sessionEl = _extraFiltersEl.querySelector(".gm-feed__session-filter");
    if (sessionEl) {
      sessionEl.addEventListener("change", function () {
        _sessionId = sessionEl.value;
        _update();
      });
    }
  }

  /**
   * Wire the "Load more" button.
   */
  function _wireLoadMore() {
    if (!_loadMoreEl) return;
    var btn = _loadMoreEl.querySelector("#gm-feed-load-more");
    if (btn && !_loading && _hasMore) {
      btn.addEventListener("click", function () {
        _fetchPage(false);
      });
    }
  }

  /**
   * Row click handler — navigate to primary target's detail.
   * Individual cell links are handled separately.
   * @param {object} row — normalized row object
   */
  function _onRowClick(row) {
    if (row.primary_target_type && row.primary_target_id) {
      var pathSeg = TYPE_TO_PATH[row.primary_target_type] || (row.primary_target_type + "s");
      window.location.hash = "#/gm/world/" + pathSeg + "/" + row.primary_target_id;
      return;
    }
    // Fall back to first target.
    var targets = row.targets || [];
    if (targets.length > 0) {
      var t = targets[0];
      var type = t.target_type || t.type || "characters";
      var id   = t.target_id   || t.id   || "";
      var ps   = TYPE_TO_PATH[type] || (type + "s");
      if (id) {
        window.location.hash = "#/gm/world/" + ps + "/" + id;
      }
    }
  }

  // --------------------------------------------------------------------------
  // Data fetching
  // --------------------------------------------------------------------------

  /**
   * Build the request URL with pagination and filter params.
   * @param {string|null} cursor
   * @returns {string}
   */
  function _buildUrl(cursor) {
    var url = _baseUrl + "?limit=" + LIMIT;
    if (cursor) url += "&after=" + encodeURIComponent(cursor);
    return url;
  }

  /**
   * Fetch one page of feed data.
   * @param {boolean} reset — true = first page (clears existing rows)
   */
  function _fetchPage(reset) {
    if (!_alive_fetch()) return;
    if (_loading && !reset) return;

    _loading = true;
    _update();

    var cursor = reset ? null : _nextCursor;

    api.get(_buildUrl(cursor))
      .then(function (data) {
        if (!_mounted) return;
        var items = (data && data.items) ? data.items : [];
        _nextCursor = (data && data.next_cursor) ? data.next_cursor : null;
        _hasMore    = !!(data && data.has_more);

        var normalized = items.map(_normalizeItem);
        if (reset) {
          _allRows = normalized;
        } else {
          _allRows = _allRows.concat(normalized);
        }
      })
      .catch(function () {
        // Errors surfaced via api:error event in api.js.
      })
      .finally(function () {
        _loading = false;
        if (_mounted) {
          _update();
        }
      });
  }

  /**
   * Returns true when the view is still mounted (guard for async callbacks).
   */
  function _alive_fetch() {
    return _mounted && !!_viewEl;
  }

  // --------------------------------------------------------------------------
  // Teardown
  // --------------------------------------------------------------------------

  function _teardown() {
    _mounted = false;
    if (_dt) {
      _dt.destroy();
      _dt = null;
    }
    _allRows    = [];
    _nextCursor = null;
    _hasMore    = false;
    _loading    = false;
    _category   = "all";
    _actorType  = "";
    _sessionId  = "";
    _viewEl             = null;
    _tableContainerEl   = null;
    _extraFiltersEl     = null;
    _loadMoreEl         = null;
    _categoryTabsEl     = null;
  }

  function _onHashChange() {
    var hash = window.location.hash || "#/";
    var stillHere = false;
    for (var i = 0; i < _ownHashes.length; i++) {
      if (_ownHashes[i] === hash) { stillHere = true; break; }
    }
    if (!stillHere) {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // --------------------------------------------------------------------------
  // Entry points
  // --------------------------------------------------------------------------

  /**
   * Shared mount logic.
   * @param {string} viewTab — 'full' | 'silent'
   * @param {string} url     — feed endpoint URL
   */
  function _mount(viewTab, url) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // Guard: GM only.
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      if (!Alpine.store("app").isGm()) {
        _viewEl.innerHTML =
          '<div class="gm-feed">' +
            '<p class="error-text" role="alert">Access denied — GM only.</p>' +
          '</div>';
        return;
      }
    }

    // Teardown any prior instance.
    _teardown();

    _mounted = true;
    _baseUrl = url;

    _mountShell(viewTab);
    _fetchPage(true);

    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  }

  // --------------------------------------------------------------------------
  // Public view registrations
  // --------------------------------------------------------------------------

  /**
   * GM full feed — #/gm/feed.
   */
  window.views.gmFeed = function () {
    _mount("full", FEED_URL);
  };

  /**
   * GM silent feed — #/gm/feed/silent.
   */
  window.views.gmFeedSilent = function () {
    _mount("silent", SILENT_URL);
  };

})();
