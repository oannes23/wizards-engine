/* Wizards Engine — GM Queue view
 *
 * Route:  #/gm  and  #/gm/queue
 * Access: GM only
 *
 * Displays the pending proposal review queue. System proposals appear first
 * (distinct visual treatment), then player proposals in ULID (oldest-first) order.
 *
 * Features:
 *   - Fetches GET /api/v1/proposals?status=pending on mount
 *   - Registers 30s polling via Alpine.store('app').registerPoll('gm-queue', ...)
 *   - Unregisters polling on hashchange away from this view
 *   - Accordion expand: only one card open at a time
 *   - Approve (default): POST /proposals/{id}/approve with empty body
 *   - Approve (advanced): POST /proposals/{id}/approve with narrative + gm_overrides
 *   - Reject: POST /proposals/{id}/reject with optional rejection_note
 *   - Optimistic removal on approve/reject; rolls back on API error
 *
 * Registers as:  window.views.gmQueue
 * Called by:     router.js route table entries for "/gm" and "/gm/queue"
 */

window.views = window.views || {};

window.views.gmQueue = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var POLL_KEY = "gm-queue";
  var POLL_INTERVAL_MS = 30000;
  var PROPOSALS_URL = "/api/v1/proposals?status=pending";

  var QUEUE_SUMMARY_POLL_KEY = "gm-queue-summary";
  var QUEUE_SUMMARY_POLL_INTERVAL_MS = 60000;
  var QUEUE_SUMMARY_URL = "/api/v1/gm/queue-summary";

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** Currently rendered proposals list. Mutated by fetch/approve/reject. */
  var _proposals = [];

  /** PC cards from /gm/queue-summary — array of PCQueueCard objects. */
  var _pcCards = [];

  /** Group cards from /gm/queue-summary — array of GroupQueueCard objects. */
  var _groupCards = [];

  /** DataTable instance for the Groups section, or null when not mounted. */
  var _groupsTable = null;

  /** ID of the currently expanded proposal card, or null. */
  var _expandedId = null;

  /** Set of proposal IDs with an in-flight request. */
  var _inflightIds = {};

  /** The #view element — stored at render time. */
  var _viewEl = null;

  /** Whether we are the currently mounted view (prevents stale poll callbacks). */
  var _mounted = false;

  // ---------------------------------------------------------------------------
  // Sorting helpers
  // ---------------------------------------------------------------------------

  /**
   * Sort proposals: system proposals first, then player proposals in ULID order
   * (ULIDs are lexicographically sortable — smaller ULID = older record).
   *
   * @param {Array} proposals
   * @returns {Array} sorted copy
   */
  function _sortProposals(proposals) {
    var system = [];
    var player = [];

    for (var i = 0; i < proposals.length; i++) {
      if (proposals[i].origin === "system") {
        system.push(proposals[i]);
      } else {
        player.push(proposals[i]);
      }
    }

    // Sort player proposals oldest-first by ULID (lexicographic = chronological)
    player.sort(function (a, b) {
      if (a.id < b.id) return -1;
      if (a.id > b.id) return 1;
      return 0;
    });

    return system.concat(player);
  }

  // ---------------------------------------------------------------------------
  // DOM helpers
  // ---------------------------------------------------------------------------


  // ---------------------------------------------------------------------------
  // PC card grid rendering
  // ---------------------------------------------------------------------------

  /**
   * Format an event type string into a human-readable label.
   * Converts underscores to spaces and title-cases the result.
   *
   * @param {string} eventType — e.g. "use_skill", "gm_direct_action"
   * @returns {string}
   */
  function _formatEventType(eventType) {
    if (!eventType) return "";
    return String(eventType)
      .replace(/_/g, " ")
      .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  /**
   * Render a single PC queue card as an HTML string.
   *
   * @param {object} card — PCQueueCard from the API
   * @returns {string} HTML string
   */
  function _renderPcCard(card) {
    var esc = window.utils.esc;
    var relativeTime = window.utils.relativeTime;

    var id = card.id || "";
    var name = card.name || "Unknown";
    var stress = card.stress || 0;
    var stressMax = card.stress_max || 9;
    var freeTime = card.free_time || 0;
    var freeTimeMax = card.free_time_max || 20;
    var plot = card.plot || 0;
    var plotMax = card.plot_max || 5;
    var gnosis = card.gnosis || 0;
    var gnosisMax = card.gnosis_max || 23;

    // Stress proximity alert: within 2 of effective max
    var margin = stressMax - stress;
    var isAlert = margin <= 2;
    var cardClass = "queue-pc-card" + (isAlert ? " queue-pc-card--alert" : "");

    // Meter bars — compact rendering via meterBar component
    var stressBar = window.components.meterBar.render({
      label: "Stress",
      current: stress,
      max: stressMax,
      color: "var(--we-stress-red, #c0392b)",
    });
    var ftBar = window.components.meterBar.render({
      label: "FT",
      current: freeTime,
      max: freeTimeMax,
      color: "var(--we-ft-green, #27ae60)",
    });
    var plotBar = window.components.meterBar.render({
      label: "Plot",
      current: plot,
      max: plotMax,
      color: "var(--we-plot-amber, #f39c12)",
    });
    var gnosisBar = window.components.meterBar.render({
      label: "Gnosis",
      current: gnosis,
      max: gnosisMax,
      color: "var(--we-gnosis-blue, #2980b9)",
    });

    // Low-charge badges
    var lowChargeItems = (card.low_charge_traits || []).concat(card.low_charge_bonds || []);
    var badgesHtml = "";
    if (lowChargeItems.length > 0) {
      for (var i = 0; i < lowChargeItems.length; i++) {
        var item = lowChargeItems[i];
        badgesHtml +=
          '<span class="queue-alert" title="' + esc(item.slot_type) + ' — charge: ' + esc(item.charge) + '">' +
            esc(item.name) +
          '</span>';
      }
    }

    // Recent events
    var recentEvents = card.recent_events || [];
    var eventsHtml = "";
    if (recentEvents.length === 0) {
      eventsHtml = '<p class="queue-pc-card__no-events">No recent events</p>';
    } else {
      for (var j = 0; j < recentEvents.length; j++) {
        var evt = recentEvents[j];
        eventsHtml +=
          '<div class="queue-pc-event-row">' +
            '<span class="queue-pc-event-row__type">' + esc(_formatEventType(evt.type)) + '</span>' +
            '<span class="queue-pc-event-row__time">' + esc(relativeTime(evt.created_at)) + '</span>' +
          '</div>';
      }
    }

    // Character detail link — use GM world characters route
    var detailHash = "#/gm/world/characters/" + esc(id);

    return (
      '<div class="' + cardClass + '">' +
        '<p class="queue-pc-card__name">' +
          '<a href="' + detailHash + '">' + esc(name) + '</a>' +
        '</p>' +
        '<div class="queue-pc-card__meters">' +
          stressBar +
          ftBar +
          plotBar +
          gnosisBar +
        '</div>' +
        (lowChargeItems.length > 0
          ? '<div class="queue-pc-card__badges">' + badgesHtml + '</div>'
          : '') +
        '<div class="queue-pc-card__events">' +
          '<p class="queue-pc-card__events-label">Recent events</p>' +
          eventsHtml +
        '</div>' +
      '</div>'
    );
  }

  /**
   * Render the PC card grid section as an HTML string.
   * Returns empty string if there are no PC cards.
   *
   * @param {Array} pcCards
   * @returns {string} HTML string
   */
  function _renderPcGrid(pcCards) {
    if (!pcCards || pcCards.length === 0) {
      return "";
    }

    var cardsHtml = "";
    for (var i = 0; i < pcCards.length; i++) {
      cardsHtml += _renderPcCard(pcCards[i]);
    }

    return (
      '<p class="queue-section-heading">Player Characters</p>' +
      '<div class="queue-pc-grid">' +
        cardsHtml +
      '</div>'
    );
  }

  // ---------------------------------------------------------------------------
  // Groups section rendering (DataTable)
  // ---------------------------------------------------------------------------

  /**
   * Render the tier number as a small badge.
   * @param {number} tier
   * @returns {string} HTML
   */
  function _renderTierBadge(tier) {
    var esc = window.utils.esc;
    return (
      '<span class="queue-groups__tier-badge">' +
        esc(tier != null ? "Tier " + tier : "—") +
      '</span>'
    );
  }

  /**
   * Render a group's active clocks as a series of compact ClockProgress
   * components, one per clock, with the clock name as a label.
   * Returns "—" if there are no active clocks.
   *
   * @param {Array} activeClocks — array of ActiveClockSummary objects
   * @returns {string} HTML
   */
  function _renderActiveClocks(activeClocks) {
    if (!activeClocks || activeClocks.length === 0) {
      return '<span class="queue-groups__no-clocks">—</span>';
    }
    var esc = window.utils.esc;
    var parts = [];
    for (var i = 0; i < activeClocks.length; i++) {
      var clock = activeClocks[i];
      parts.push(
        '<span class="queue-groups__clock-row">' +
          '<span class="queue-groups__clock-name">' + esc(clock.name) + '</span>' +
          window.components.clockProgress.render({
            current: clock.progress,
            total: clock.segments,
            mode: "compact",
          }) +
        '</span>'
      );
    }
    return '<span class="queue-groups__clocks">' + parts.join("") + '</span>';
  }

  /**
   * Render the last-activity cell: relative timestamp or "No activity" if null.
   * @param {string|null} mostRecentEventAt — ISO timestamp or null
   * @returns {string} HTML
   */
  function _renderLastActivity(mostRecentEventAt) {
    if (!mostRecentEventAt) {
      return '<span class="queue-groups__no-activity">No recent activity</span>';
    }
    return (
      '<span class="queue-groups__last-activity">' +
        window.utils.esc(window.utils.relativeTime(mostRecentEventAt)) +
      '</span>'
    );
  }

  /**
   * Mount or update the Groups DataTable.
   * If _groupsTable already exists, call setRows() to update without
   * destroying the table (preserves sort state).
   * If groupCards is empty and there are no groups, render an empty-state
   * message inside the container instead.
   *
   * @param {HTMLElement} container — the .queue-groups__table-wrap element
   * @param {Array}       groupCards — array of GroupQueueCard objects
   */
  function _mountGroupsTable(container, groupCards) {
    if (!container) return;

    if (_groupsTable) {
      // Table already exists — just update the rows
      _groupsTable.setRows(groupCards);
      return;
    }

    var columns = [
      {
        key: "name",
        label: "Group Name",
        sortable: true,
        filter: "text",
        render: function (value) {
          return '<span class="queue-groups__name">' + window.utils.esc(value) + '</span>';
        },
      },
      {
        key: "tier",
        label: "Tier",
        sortable: true,
        filter: "select",
        width: "80px",
        render: function (value) {
          return _renderTierBadge(value);
        },
      },
      {
        key: "active_clocks",
        label: "Active Clocks",
        sortable: false,
        render: function (value) {
          return _renderActiveClocks(value);
        },
        hideMobile: true,
      },
      {
        key: "most_recent_event_at",
        label: "Last Activity",
        sortable: true,
        render: function (value) {
          return _renderLastActivity(value);
        },
      },
    ];

    _groupsTable = new window.components.DataTable(container, {
      columns: columns,
      emptyMessage: "No groups found.",
      onRowClick: function (row) {
        window.location.hash = "#/gm/world/groups/" + row.id;
      },
    });

    _groupsTable.setRows(groupCards);
  }

  /**
   * Destroy the groups DataTable if it exists.
   * Called on teardown and before full re-render when the table container
   * is about to be removed from the DOM.
   */
  function _destroyGroupsTable() {
    if (_groupsTable) {
      _groupsTable.destroy();
      _groupsTable = null;
    }
  }

  /**
   * Render the Groups section HTML wrapper.
   * The DataTable is mounted into the container after innerHTML is set.
   *
   * @returns {string} HTML string for the section wrapper
   */
  function _renderGroupsSectionHtml() {
    return (
      '<p class="queue-section-heading">Groups</p>' +
      '<div class="queue-groups" id="queue-groups-section">' +
        '<div class="queue-groups__table-wrap" id="queue-groups-table"></div>' +
      '</div>'
    );
  }

  /**
   * After _renderList() has written the Groups section HTML to the DOM,
   * mount the DataTable into the container element.
   *
   * @param {Array} groupCards
   */
  function _mountGroupsTableInDom(groupCards) {
    var container = document.getElementById("queue-groups-table");
    if (!container) return;
    _mountGroupsTable(container, groupCards);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  /**
   * Re-render the full proposals list into _viewEl.
   * Preserves the expanded state and inflight indicators.
   */
  function _renderList() {
    if (!_viewEl || !_mounted) return;

    // Destroy the DataTable before wiping innerHTML so its listeners
    // are properly removed before the container element disappears.
    _destroyGroupsTable();

    var sorted = _sortProposals(_proposals);

    var html =
      '<div class="gm-queue">' +
        '<hgroup>' +
          '<h2>GM Queue</h2>' +
          '<p class="gm-queue__subtitle">' +
            (sorted.length === 0
              ? 'No pending proposals'
              : sorted.length + ' pending proposal' + (sorted.length === 1 ? '' : 's')) +
          '</p>' +
        '</hgroup>' +
        _renderPcGrid(_pcCards);

    // Groups section — DataTable placeholder (table mounted after innerHTML)
    html += _renderGroupsSectionHtml();

    html += '<p class="queue-section-heading">Pending Proposals</p>';

    if (sorted.length === 0) {
      html +=
        '<div class="gm-queue__empty" role="status">' +
          '<p>No pending proposals. All caught up!</p>' +
        '</div>';
    } else {
      html += '<div class="gm-queue__list" id="gm-queue-list">';
      for (var i = 0; i < sorted.length; i++) {
        var p = sorted[i];
        html += window.components.proposalCard.render({
          proposal: p,
          expanded: _expandedId === p.id,
          inflight: !!_inflightIds[p.id],
          onApprove: _handleApprove,
          onReject: _handleReject,
          onToggle: _handleToggle,
        });
      }
      html += '</div>';
    }

    html += '</div>';

    _viewEl.innerHTML = html;

    // Mount the Groups DataTable now that the container is in the DOM
    _mountGroupsTableInDom(_groupCards);

    // Attach event listeners to all rendered proposal cards
    for (var j = 0; j < sorted.length; j++) {
      window.components.proposalCard.attach(_viewEl, {
        proposal: sorted[j],
        expanded: _expandedId === sorted[j].id,
        inflight: !!_inflightIds[sorted[j].id],
        onApprove: _handleApprove,
        onReject: _handleReject,
        onToggle: _handleToggle,
      });
    }
  }

  /**
   * Render the loading state.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-queue">' +
        '<hgroup>' +
          '<h2>Proposal Queue</h2>' +
          '<p aria-busy="true">Loading proposals...</p>' +
        '</hgroup>' +
      '</div>';
  }

  /**
   * Render an error state with a retry button.
   */
  function _renderError() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-queue">' +
        '<hgroup>' +
          '<h2>Proposal Queue</h2>' +
        '</hgroup>' +
        '<p class="error-text" role="alert">Failed to load proposals.</p>' +
        '<button id="gm-queue-retry">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("gm-queue-retry");
    if (retryBtn) {
      retryBtn.addEventListener("click", _fetchProposals);
    }
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Enrich a list of proposals with character_name resolved from the
   * characters summary endpoint.  Mutates each proposal object in-place.
   * Proposals with no character_id (system proposals) are left unchanged.
   *
   * @param {Array} proposals
   * @returns {Promise<Array>} the same array, mutated with character_name
   */
  function _enrichWithCharacterNames(proposals) {
    // Collect unique character IDs that need a name
    var ids = {};
    for (var i = 0; i < proposals.length; i++) {
      if (proposals[i].character_id) {
        ids[proposals[i].character_id] = true;
      }
    }
    if (Object.keys(ids).length === 0) {
      return Promise.resolve(proposals);
    }

    return api
      .get("/api/v1/characters/summary")
      .then(function (data) {
        var nameMap = {};
        var items = (data && data.items) ? data.items : [];
        for (var j = 0; j < items.length; j++) {
          nameMap[items[j].id] = items[j].name;
        }
        for (var k = 0; k < proposals.length; k++) {
          if (proposals[k].character_id) {
            proposals[k].character_name = nameMap[proposals[k].character_id] || null;
          }
        }
        return proposals;
      })
      .catch(function () {
        // Name resolution is best-effort; return proposals without names
        return proposals;
      });
  }

  /**
   * Fetch the pending proposals list and re-render.
   * Called on mount and by the poll callback.
   *
   * @param {boolean} [isInitial] — if true, show loading state first
   */
  function _fetchProposals(isInitial) {
    if (!_mounted) return;

    if (isInitial) {
      _renderLoading();
    }

    api
      .get(PROPOSALS_URL)
      .then(function (data) {
        if (!_mounted) return;
        var proposals = (data && data.items) ? data.items : [];
        return _enrichWithCharacterNames(proposals);
      })
      .then(function (proposals) {
        if (!_mounted) return;
        _proposals = proposals;
        _renderList();

        // Update the nav badge with the current pending count
        _updateQueueBadge(_proposals.length);
      })
      .catch(function () {
        if (!_mounted) return;
        _renderError();
      });
  }

  /**
   * Fetch the queue summary (PC cards) from /gm/queue-summary and re-render.
   * Called on mount and by the 60s poll callback.
   * Failures are silent — the PC grid simply won't update.
   */
  function _fetchQueueSummary() {
    if (!_mounted) return;

    api
      .get(QUEUE_SUMMARY_URL)
      .then(function (data) {
        if (!_mounted) return;
        _pcCards = (data && data.pc_cards) ? data.pc_cards : [];
        _groupCards = (data && data.group_cards) ? data.group_cards : [];
        _renderList();
      })
      .catch(function () {
        // Best-effort — do not change render state on error
      });
  }

  /**
   * Poll callback for queue-summary.
   * Updates PC cards and group cards, then re-renders.
   * @param {object} data — parsed response from GET /api/v1/gm/queue-summary
   */
  function _queueSummaryPollCallback(data) {
    if (!_mounted) return;
    _pcCards = (data && data.pc_cards) ? data.pc_cards : [];
    _groupCards = (data && data.group_cards) ? data.group_cards : [];
    _renderList();
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  /**
   * Toggle the expanded state of a proposal card.
   * Only one card can be expanded at a time (accordion).
   *
   * @param {string} id — proposal id
   */
  function _handleToggle(id) {
    _expandedId = (_expandedId === id) ? null : id;
    _renderList();
  }

  /**
   * Approve a proposal.
   * Optimistically removes it from the list; rolls back on error.
   *
   * @param {string} id — proposal id
   * @param {object} body — { narrative, gm_overrides, force }
   */
  function _handleApprove(id, body) {
    if (_inflightIds[id]) return;
    _inflightIds[id] = true;

    // Optimistic removal
    var removed = null;
    _proposals = _proposals.filter(function (p) {
      if (p.id === id) {
        removed = p;
        return false;
      }
      return true;
    });
    if (_expandedId === id) {
      _expandedId = null;
    }
    _renderList();

    var overrides = (body && body.gm_overrides) || {};
    if (body && body.force) {
      overrides.force = true;
    }
    var approveBody = {
      narrative: (body && body.narrative) || null,
      gm_overrides: Object.keys(overrides).length > 0 ? overrides : null,
    };

    api
      .post("/api/v1/proposals/" + id + "/approve", approveBody)
      .then(function () {
        delete _inflightIds[id];
        window.utils.showSuccess("Proposal approved.");
        // List already updated optimistically — no re-render needed
      })
      .catch(function () {
        // Roll back: re-insert the proposal at the end (will be re-sorted)
        delete _inflightIds[id];
        if (removed) {
          _proposals.push(removed);
        }
        _renderList();
      });
  }

  /**
   * Reject a proposal.
   * Optimistically removes it from the list; rolls back on error.
   *
   * @param {string} id — proposal id
   * @param {object} body — { rejection_note }
   */
  function _handleReject(id, body) {
    if (_inflightIds[id]) return;
    _inflightIds[id] = true;

    // Optimistic removal
    var removed = null;
    _proposals = _proposals.filter(function (p) {
      if (p.id === id) {
        removed = p;
        return false;
      }
      return true;
    });
    if (_expandedId === id) {
      _expandedId = null;
    }
    _renderList();

    var rejectBody = {
      rejection_note: (body && body.rejection_note) || null,
    };

    api
      .post("/api/v1/proposals/" + id + "/reject", rejectBody)
      .then(function () {
        delete _inflightIds[id];
        window.utils.showSuccess("Proposal rejected.");
      })
      .catch(function () {
        // Roll back
        delete _inflightIds[id];
        if (removed) {
          _proposals.push(removed);
        }
        _renderList();
      });
  }

  // ---------------------------------------------------------------------------
  // Poll callback
  // ---------------------------------------------------------------------------

  /**
   * Called by the store's polling infrastructure every 30 seconds.
   * Merges new proposals into the existing list without full re-render
   * to avoid disrupting the expanded state.
   *
   * Strategy: replace the proposals list but keep _expandedId if the
   * proposal still exists. If it was removed on the server, collapse.
   *
   * @param {object} data — parsed response from GET /api/v1/proposals?status=pending
   */
  /**
   * Update the nav badge for the GM Queue tab with the current pending count.
   * @param {number} count
   */
  function _updateQueueBadge(count) {
    if (typeof window.navBadges !== "undefined") {
      window.navBadges.queue = count;
      document.dispatchEvent(new CustomEvent("nav:refresh"));
    }
  }

  function _pollCallback(data) {
    if (!_mounted) return;
    var newProposals = (data && data.items) ? data.items : [];

    _enrichWithCharacterNames(newProposals).then(function (enriched) {
      if (!_mounted) return;
      _proposals = enriched;

      // If the expanded proposal was resolved elsewhere, collapse it
      if (_expandedId !== null) {
        var stillExists = false;
        for (var i = 0; i < _proposals.length; i++) {
          if (_proposals[i].id === _expandedId) {
            stillExists = true;
            break;
          }
        }
        if (!stillExists) {
          _expandedId = null;
        }
      }

      _renderList();

      // Update the nav badge with the current pending count
      _updateQueueBadge(_proposals.length);
    });
  }

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  /**
   * Called when navigating away from this view.
   * Unregisters the poll and clears mounted flag.
   */
  function _teardown() {
    _mounted = false;
    _expandedId = null;
    _inflightIds = {};
    _pcCards = [];
    _groupCards = [];

    // Destroy the DataTable to remove its event listeners
    _destroyGroupsTable();

    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").unregisterPoll(POLL_KEY);
      Alpine.store("app").unregisterPoll(QUEUE_SUMMARY_POLL_KEY);
    }

    // Clear the queue badge when leaving the view
    _updateQueueBadge(0);
  }

  /**
   * One-time hashchange listener that calls _teardown when leaving this view.
   * Removes itself after first navigation away.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/gm/queue") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the GM Queue view.
   * Called by router.js for the "/gm" and "/gm/queue" routes.
   */
  return function render() {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // Guard: only GMs should see this view
    if (!window.utils.requireGm(_viewEl)) return;

    // Reset state for a fresh mount
    _mounted = true;
    _proposals = [];
    _pcCards = [];
    _groupCards = [];
    _expandedId = null;
    _inflightIds = {};
    _destroyGroupsTable();

    // Initial fetch — proposals (shows loading state) + queue-summary (background)
    _fetchProposals(true);
    _fetchQueueSummary();

    // Register 30-second polling for proposals
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").registerPoll(POLL_KEY, {
        url: PROPOSALS_URL,
        intervalMs: POLL_INTERVAL_MS,
        callback: _pollCallback,
      });
    }

    // Register 60-second polling for queue-summary (PC cards)
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").registerPoll(QUEUE_SUMMARY_POLL_KEY, {
        url: QUEUE_SUMMARY_URL,
        intervalMs: QUEUE_SUMMARY_POLL_INTERVAL_MS,
        callback: _queueSummaryPollCallback,
      });
    }

    // Teardown when navigating away
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
