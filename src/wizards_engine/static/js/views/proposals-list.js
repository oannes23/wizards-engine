/* Wizards Engine — Player Proposals List view
 *
 * Route:  #/proposals
 * Access: Player only
 *
 * Displays the player's own proposals grouped by status:
 *   Pending → Approved → Rejected
 *
 * Features:
 *   - Fetches GET /api/v1/proposals?character_id={store.character_id} on mount
 *   - Registers 60s polling via Alpine.store('app').registerPoll
 *   - Updates window.navBadges.proposals on each poll (count of newly
 *     approved/rejected since last viewed)
 *   - Clears badge count (updates lastViewed in sessionStorage) on mount
 *   - Tap a proposal card → navigates to #/proposals/{id}
 *
 * Registers as:  window.views.proposalsList
 * Called by:     router.js route table entry for "/proposals"
 */

window.views = window.views || {};

window.views.proposalsList = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var POLL_KEY = "proposals-list";
  var POLL_INTERVAL_MS = 60000;
  var SESSION_KEY = "proposals_last_viewed";

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** All proposals for this character, keyed by status group. */
  var _proposals = [];

  /** The #view element — stored at render time. */
  var _viewEl = null;

  /** Whether we are the currently mounted view. */
  var _mounted = false;

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  var _relativeTime = function (s) { return window.utils.relativeTime(s); };

  /** Human-readable action type labels (mirrors proposal-card.js constants). */
  var ACTION_LABELS = {
    use_skill:        "Use Skill",
    use_magic:        "Use Magic",
    charge_magic:     "Charge Magic",
    regain_gnosis:    "Regain Gnosis",
    work_on_project:  "Work on Project",
    rest:             "Rest",
    new_trait:        "New Trait",
    new_bond:         "New Bond",
    resolve_clock:    "Resolve Clock",
    resolve_trauma:   "Resolve Trauma",
  };

  function _actionLabel(actionType) {
    return ACTION_LABELS[actionType] || actionType;
  }

  /**
   * Truncate a string to maxLen characters, appending "..." if truncated.
   * @param {string} str
   * @param {number} maxLen
   * @returns {string}
   */
  function _truncate(str, maxLen) {
    if (!str) return "";
    if (str.length <= maxLen) return str;
    return str.slice(0, maxLen) + "...";
  }

  /**
   * Return the stored "last viewed" timestamp from sessionStorage.
   * Returns 0 if not set (meaning everything is "new").
   * @returns {number} Unix timestamp in ms
   */
  function _getLastViewed() {
    try {
      var val = sessionStorage.getItem(SESSION_KEY);
      return val ? parseInt(val, 10) : 0;
    } catch (_) {
      return 0;
    }
  }

  /**
   * Update the "last viewed" timestamp to now.
   */
  function _setLastViewed() {
    try {
      sessionStorage.setItem(SESSION_KEY, String(Date.now()));
    } catch (_) {
      // sessionStorage may be unavailable in some contexts — ignore
    }
  }

  /**
   * Count proposals where status is approved or rejected and updated_at
   * is after lastViewed.
   * @param {Array} proposals
   * @returns {number}
   */
  function _countNewStatusChanges(proposals) {
    var lastViewed = _getLastViewed();
    if (!lastViewed) return 0;
    var count = 0;
    for (var i = 0; i < proposals.length; i++) {
      var p = proposals[i];
      if (p.status === "approved" || p.status === "rejected") {
        var updatedMs = 0;
        try {
          updatedMs = new Date(p.updated_at).getTime();
        } catch (_) {}
        if (updatedMs > lastViewed) {
          count++;
        }
      }
    }
    return count;
  }

  /**
   * Update the nav badge count for the Proposals tab.
   * @param {number} count
   */
  function _updateBadge(count) {
    if (typeof window.navBadges !== "undefined") {
      window.navBadges.proposals = count;
      document.dispatchEvent(new CustomEvent("nav:refresh"));
    }
  }

  // ---------------------------------------------------------------------------
  // Grouping
  // ---------------------------------------------------------------------------

  /**
   * Group proposals by status into { pending, approved, rejected } arrays.
   * Within each group, sort newest-first by updated_at.
   * @param {Array} proposals
   * @returns {{ pending: Array, approved: Array, rejected: Array }}
   */
  function _groupByStatus(proposals) {
    var groups = { pending: [], approved: [], rejected: [] };
    for (var i = 0; i < proposals.length; i++) {
      var p = proposals[i];
      if (groups[p.status]) {
        groups[p.status].push(p);
      } else {
        // Unknown status — treat as pending
        groups.pending.push(p);
      }
    }

    // Sort each group newest-first by updated_at
    function newestFirst(a, b) {
      var at = new Date(a.updated_at).getTime() || 0;
      var bt = new Date(b.updated_at).getTime() || 0;
      return bt - at;
    }
    groups.pending.sort(newestFirst);
    groups.approved.sort(newestFirst);
    groups.rejected.sort(newestFirst);

    return groups;
  }

  // ---------------------------------------------------------------------------
  // Card rendering
  // ---------------------------------------------------------------------------

  /**
   * Render a single proposal summary card.
   * Clicking navigates to #/proposals/{id}.
   * @param {object} proposal — ProposalResponse
   * @returns {string} HTML
   */
  function _renderCard(proposal) {
    var badgeClass = "proposal-status-badge";
    var statusLabel = "";
    if (proposal.status === "pending") {
      badgeClass += " proposal-status-badge--pending";
      statusLabel = "Pending";
    } else if (proposal.status === "approved") {
      badgeClass += " proposal-status-badge--approved";
      statusLabel = "Approved";
    } else if (proposal.status === "rejected") {
      badgeClass += " proposal-status-badge--rejected";
      statusLabel = "Rejected";
    } else {
      statusLabel = window.utils.esc(proposal.status);
    }

    var narrativePreview = window.utils.esc(_truncate(proposal.narrative, 80));
    var timeLabel = window.utils.esc(_relativeTime(proposal.updated_at));

    return (
      '<article class="proposal-list-card" role="button" tabindex="0" ' +
              'data-proposal-id="' + window.utils.esc(proposal.id) + '" ' +
              'aria-label="' + window.utils.esc(_actionLabel(proposal.action_type)) + ' proposal, ' + statusLabel + '">' +
        '<div class="proposal-list-card__header">' +
          '<span class="proposal-list-card__action-type">' + window.utils.esc(_actionLabel(proposal.action_type)) + '</span>' +
          '<span class="' + badgeClass + '">' + statusLabel + '</span>' +
        '</div>' +
        '<div class="proposal-list-card__body">' +
          (narrativePreview
            ? '<p class="proposal-list-card__narrative">' + narrativePreview + '</p>'
            : '<p class="proposal-list-card__narrative proposal-list-card__narrative--empty"><em>No narrative</em></p>') +
        '</div>' +
        '<div class="proposal-list-card__footer">' +
          '<span class="proposal-list-card__time">' + timeLabel + '</span>' +
        '</div>' +
      '</article>'
    );
  }

  /**
   * Render a group section (e.g. "Pending (2)").
   * @param {string} label — group heading
   * @param {Array} proposals — sorted proposals for this group
   * @returns {string} HTML
   */
  function _renderGroup(label, proposals) {
    if (proposals.length === 0) return "";

    var cards = "";
    for (var i = 0; i < proposals.length; i++) {
      cards += _renderCard(proposals[i]);
    }

    return (
      '<section class="proposals-group">' +
        '<h3 class="proposals-group__heading">' +
          window.utils.esc(label) +
          ' <span class="proposals-group__count">(' + proposals.length + ')</span>' +
        '</h3>' +
        '<div class="proposals-group__list">' + cards + '</div>' +
      '</section>'
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  /**
   * Re-render the full proposals list into _viewEl.
   */
  function _renderList() {
    if (!_viewEl || !_mounted) return;

    var groups = _groupByStatus(_proposals);
    var total = groups.pending.length + groups.approved.length + groups.rejected.length;

    var html =
      '<div class="proposals-list">' +
        '<div class="proposals-list__header">' +
          '<hgroup>' +
            '<h2>My Proposals</h2>' +
            '<p class="proposals-list__subtitle">' +
              (total === 0
                ? "No proposals yet"
                : total + " proposal" + (total === 1 ? "" : "s")) +
            '</p>' +
          '</hgroup>' +
          '<a href="#/proposals/new" role="button" class="proposals-list__new-btn">New Proposal</a>' +
        '</div>';

    if (total === 0) {
      html +=
        '<div class="proposals-list__empty" role="status">' +
          '<p>You have not submitted any proposals yet.</p>' +
          '<a href="#/proposals/new" role="button">Submit a Proposal</a>' +
        '</div>';
    } else {
      html += _renderGroup("Pending", groups.pending);
      html += _renderGroup("Approved", groups.approved);
      html += _renderGroup("Rejected", groups.rejected);
    }

    html += '</div>';

    _viewEl.innerHTML = html;

    // Attach click handlers for each card
    var cards = _viewEl.querySelectorAll("[data-proposal-id]");
    for (var i = 0; i < cards.length; i++) {
      _attachCardHandler(cards[i]);
    }
  }

  /**
   * Render the loading state.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="proposals-list">' +
        '<hgroup>' +
          '<h2>My Proposals</h2>' +
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
      '<div class="proposals-list">' +
        '<hgroup>' +
          '<h2>My Proposals</h2>' +
        '</hgroup>' +
        '<p class="error-text" role="alert">Failed to load proposals.</p>' +
        '<button id="proposals-list-retry">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("proposals-list-retry");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () { _fetchProposals(true); });
    }
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  /**
   * Attach click and keyboard handlers to a proposal card element.
   * Navigates to #/proposals/{id} on activation.
   * @param {HTMLElement} cardEl
   */
  function _attachCardHandler(cardEl) {
    var id = cardEl.getAttribute("data-proposal-id");
    if (!id) return;

    cardEl.addEventListener("click", function () {
      window.location.hash = "#/proposals/" + id;
    });

    cardEl.addEventListener("keydown", function (evt) {
      if (evt.key === "Enter" || evt.key === " ") {
        evt.preventDefault();
        window.location.hash = "#/proposals/" + id;
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Fetch proposals for the current character and re-render.
   * @param {boolean} [isInitial] — if true, show loading state first
   */
  function _fetchProposals(isInitial) {
    if (!_mounted) return;

    var characterId = null;
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      characterId = Alpine.store("app").character_id;
    }

    if (!characterId) {
      if (!_viewEl) return;
      _viewEl.innerHTML =
        '<div class="proposals-list">' +
          '<p class="error-text" role="alert">No linked character. Contact your GM.</p>' +
        '</div>';
      return;
    }

    if (isInitial) {
      _renderLoading();
    }

    var url = "/api/v1/proposals?character_id=" + encodeURIComponent(characterId);

    api
      .get(url)
      .then(function (data) {
        if (!_mounted) return;
        _proposals = (data && data.items) ? data.items : [];
        _renderList();
      })
      .catch(function () {
        if (!_mounted) return;
        _renderError();
      });
  }

  // ---------------------------------------------------------------------------
  // Poll callback
  // ---------------------------------------------------------------------------

  /**
   * Called by the store's polling infrastructure every 60 seconds.
   * Updates the proposals list and refreshes the notification badge.
   *
   * @param {object} data — parsed response from the proposals endpoint
   */
  function _pollCallback(data) {
    if (!_mounted) return;
    _proposals = (data && data.items) ? data.items : [];
    _renderList();

    // Update the notification badge with count of newly-resolved proposals
    var badgeCount = _countNewStatusChanges(_proposals);
    _updateBadge(badgeCount);
  }

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  /**
   * Called when navigating away from this view.
   */
  function _teardown() {
    _mounted = false;

    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").unregisterPoll(POLL_KEY);
    }
  }

  /**
   * One-time hashchange listener that calls _teardown when leaving this view.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/proposals") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the Proposals List view.
   * Called by router.js for the "/proposals" route.
   */
  return function render() {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // Reset state for a fresh mount
    _mounted = true;
    _proposals = [];

    // Clear the notification badge and update last-viewed timestamp
    _setLastViewed();
    _updateBadge(0);

    // Initial fetch
    _fetchProposals(true);

    // Register 60-second polling
    var characterId = null;
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      characterId = Alpine.store("app").character_id;
    }

    if (characterId && typeof Alpine !== "undefined" && Alpine.store("app")) {
      var pollUrl = "/api/v1/proposals?character_id=" + encodeURIComponent(characterId);
      Alpine.store("app").registerPoll(POLL_KEY, {
        url: pollUrl,
        intervalMs: POLL_INTERVAL_MS,
        callback: _pollCallback,
      });
    }

    // Teardown when navigating away
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
