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

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** Currently rendered proposals list. Mutated by fetch/approve/reject. */
  var _proposals = [];

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
  // Render
  // ---------------------------------------------------------------------------

  /**
   * Re-render the full proposals list into _viewEl.
   * Preserves the expanded state and inflight indicators.
   */
  function _renderList() {
    if (!_viewEl || !_mounted) return;

    var sorted = _sortProposals(_proposals);

    var html =
      '<div class="gm-queue">' +
        '<hgroup>' +
          '<h2>Proposal Queue</h2>' +
          '<p class="gm-queue__subtitle">' +
            (sorted.length === 0
              ? 'No pending proposals'
              : sorted.length + ' pending proposal' + (sorted.length === 1 ? '' : 's')) +
          '</p>' +
        '</hgroup>';

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

    // Attach event listeners to all rendered cards
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

    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").unregisterPoll(POLL_KEY);
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
    _expandedId = null;
    _inflightIds = {};

    // Initial fetch
    _fetchProposals(true);

    // Register 30-second polling
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").registerPoll(POLL_KEY, {
        url: PROPOSALS_URL,
        intervalMs: POLL_INTERVAL_MS,
        callback: _pollCallback,
      });
    }

    // Teardown when navigating away
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
