/* Wizards Engine — GM Dashboard view
 *
 * Route:  #/gm
 * Access: GM only
 *
 * The GM's primary landing page. Provides an at-a-glance summary of:
 *   - Pending proposals (count badge + summary list)
 *   - PC summaries (name, stress, free time, plot, gnosis)
 *   - Near-completion clocks (clocks at segments-1 progress)
 *
 * Features:
 *   - Fetches GET /api/v1/gm/dashboard on mount
 *   - Registers 60s polling via Alpine.store('app').registerPoll('gm-dashboard', ...)
 *   - Unregisters polling on hashchange away from this view
 *   - _renderList / _renderLoading / _renderError pattern from gm-queue.js
 *
 * Navigation:
 *   - Proposals section → #/gm/queue
 *   - PC card → #/gm/world/characters/{id}
 *   - Clock card → #/gm/world/{associated_type}/{associated_id}
 *
 * Registers as:  window.views.gmDashboard
 * Called by:     router.js route table entry for "/gm"
 *
 * Dependencies (must already be loaded):
 *   utils.js, api.js, store.js, meter-bar.js, clock-progress.js
 */

window.views = window.views || {};

window.views.gmDashboard = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var POLL_KEY = "gm-dashboard";
  var POLL_INTERVAL_MS = 60000;
  var DASHBOARD_URL = "/api/v1/gm/dashboard";

  // Meter maximums are now supplied by the API in each PC summary object:
  //   stress_max     — 9 minus trauma bond count (per-character, computed server-side)
  //   free_time_max  — always 20
  //   plot_max       — always 5
  //   gnosis_max     — always 23
  // These fallbacks are used only when a field is unexpectedly absent.
  var STRESS_MAX_FALLBACK = 9;
  var FREE_TIME_MAX_FALLBACK = 20;
  var PLOT_MAX_FALLBACK = 5;
  var GNOSIS_MAX_FALLBACK = 23;

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** Parsed dashboard response data, or null before first load. */
  var _data = null;

  /** The #view element — stored at render time. */
  var _viewEl = null;

  /** Whether we are the currently mounted view (prevents stale poll callbacks). */
  var _mounted = false;

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------


  /**
   * Render a meter bar using window.components.meterBar if available,
   * otherwise fall back to a simple inline progress representation.
   *
   * @param {string} label
   * @param {number} current
   * @param {number} max
   * @param {string} color — CSS value
   * @returns {string} HTML string
   */
  function _meterBar(label, current, max, color) {
    if (window.components && window.components.meterBar) {
      return window.components.meterBar.render({
        label: label,
        current: current,
        max: max,
        color: color,
      });
    }
    // Fallback: plain text progress
    var pct = max > 0 ? Math.round((current / max) * 100) : 0;
    return (
      '<div class="meter-bar">' +
        '<span class="meter-bar__label">' + window.utils.esc(label) + ': ' + current + '/' + max + '</span>' +
        '<div style="height:6px;background:linear-gradient(to right,' + color + ' ' + pct + '%,#444 ' + pct + '%)"></div>' +
      '</div>'
    );
  }

  /**
   * Render a clock progress indicator using window.components.clockProgress if
   * available, otherwise fall back to a plain "X/Y" text representation.
   *
   * @param {number} current
   * @param {number} total
   * @returns {string} HTML string
   */
  function _clockProgress(current, total) {
    if (window.components && window.components.clockProgress) {
      return window.components.clockProgress.render({
        current: current,
        total: total,
        mode: "compact",
      });
    }
    return '<span>' + current + '/' + total + '</span>';
  }

  /**
   * Map an associated_type value from the dashboard response to its
   * URL segment. Returns the type string unchanged as a safe default.
   *
   * @param {string} type — e.g. "characters", "groups", "locations"
   * @returns {string}
   */
  function _clockDetailPath(clock) {
    var type = clock.associated_type || "clocks";
    var id = clock.associated_id || clock.id;
    return "#/gm/world/" + type + "/" + id;
  }

  // ---------------------------------------------------------------------------
  // Section renderers
  // ---------------------------------------------------------------------------

  /**
   * Render the pending proposals section.
   *
   * @param {Array} proposals
   * @param {object} nameMap — character_id → name, built from pc_summaries
   * @returns {string} HTML string
   */
  function _renderProposalsSection(proposals, nameMap) {
    var count = proposals.length;
    var badge = count > 0
      ? ' <span class="gm-dashboard__badge" aria-label="' + count + ' pending">' + count + '</span>'
      : "";

    var html =
      '<section class="gm-dashboard__section" id="gm-dashboard-proposals">' +
        '<hgroup>' +
          '<h3>Pending Proposals' + badge + '</h3>' +
          '<p>' +
            (count === 0
              ? 'No pending proposals — all caught up!'
              : count + ' proposal' + (count === 1 ? '' : 's') + ' awaiting review. ') +
            (count > 0
              ? '<a href="#/gm/queue" class="gm-dashboard__queue-link">Go to queue &rarr;</a>'
              : '') +
          '</p>' +
        '</hgroup>';

    if (count === 0) {
      html +=
        '<div class="gm-dashboard__empty" role="status">' +
          '<p>Queue is empty.</p>' +
        '</div>';
    } else {
      html += '<ul class="gm-dashboard__proposal-list">';
      for (var i = 0; i < proposals.length; i++) {
        var p = proposals[i];
        var charName = (p.character_id && nameMap[p.character_id])
          ? nameMap[p.character_id]
          : (p.origin === "system" ? "System" : "Unknown");
        var actionLabel = window.utils.esc(p.action_type || "—");
        var timeLabel = window.utils.esc(window.utils.relativeTime(p.created_at));

        html +=
          '<li class="gm-dashboard__proposal-item">' +
            '<a href="#/gm/queue" class="gm-dashboard__proposal-link">' +
              '<span class="gm-dashboard__proposal-char">' + window.utils.esc(charName) + '</span>' +
              '<span class="gm-dashboard__proposal-meta">' +
                '<span class="gm-dashboard__proposal-type">' + actionLabel + '</span>' +
                (timeLabel ? '<span class="gm-dashboard__proposal-time">' + timeLabel + '</span>' : '') +
              '</span>' +
            '</a>' +
          '</li>';
      }
      html += '</ul>';

      if (count > 5) {
        html +=
          '<p class="gm-dashboard__see-all">' +
            '<a href="#/gm/queue">See all ' + count + ' proposals &rarr;</a>' +
          '</p>';
      }
    }

    html += '</section>';
    return html;
  }

  /**
   * Render the PC summaries section.
   *
   * @param {Array} pcs — array of PC summary objects from the API, each with:
   *   id, name, stress, stress_max, free_time, free_time_max,
   *   plot, plot_max, gnosis, gnosis_max
   * @returns {string} HTML string
   */
  function _renderPcSection(pcs) {
    var html =
      '<section class="gm-dashboard__section" id="gm-dashboard-pcs">' +
        '<hgroup>' +
          '<h3>Player Characters</h3>' +
          '<p>' + pcs.length + ' PC' + (pcs.length === 1 ? '' : 's') + '</p>' +
        '</hgroup>';

    if (pcs.length === 0) {
      html +=
        '<div class="gm-dashboard__empty" role="status">' +
          '<p>No player characters found.</p>' +
        '</div>';
    } else {
      html += '<div class="gm-dashboard__pc-grid">';
      for (var i = 0; i < pcs.length; i++) {
        var pc = pcs[i];
        var stress      = Number(pc.stress)       || 0;
        var stressMax   = Number(pc.stress_max)   || STRESS_MAX_FALLBACK;
        var freetime    = Number(pc.free_time)     || 0;
        var freetimeMax = Number(pc.free_time_max) || FREE_TIME_MAX_FALLBACK;
        var plot        = Number(pc.plot)          || 0;
        var plotMax     = Number(pc.plot_max)      || PLOT_MAX_FALLBACK;
        var gnosis      = Number(pc.gnosis)        || 0;
        var gnosisMax   = Number(pc.gnosis_max)    || GNOSIS_MAX_FALLBACK;

        html +=
          '<a href="#/gm/world/characters/' + window.utils.esc(pc.id) + '" class="gm-dashboard__pc-card">' +
            '<article>' +
              '<header class="gm-dashboard__pc-name">' + window.utils.esc(pc.name) + '</header>' +
              '<div class="gm-dashboard__pc-meters">' +
                _meterBar("Stress",    stress,   stressMax,   "var(--we-stress-red, #c0392b)") +
                _meterBar("Free Time", freetime, freetimeMax, "var(--we-ft-green, #27ae60)") +
                _meterBar("Plot",      plot,     plotMax,     "var(--we-plot-amber, #e67e22)") +
                _meterBar("Gnosis",    gnosis,   gnosisMax,   "var(--we-gnosis-blue, #2980b9)") +
              '</div>' +
            '</article>' +
          '</a>';
      }
      html += '</div>';
    }

    html += '</section>';
    return html;
  }

  /**
   * Render the near-completion clocks section.
   *
   * Clocks are "near-completion" when progress === segments - 1.
   *
   * @param {Array} clocks — array of { id, name, progress, segments, associated_type, associated_id }
   * @returns {string} HTML string
   */
  function _renderClocksSection(clocks) {
    var html =
      '<section class="gm-dashboard__section" id="gm-dashboard-clocks">' +
        '<hgroup>' +
          '<h3>Near-Completion Clocks</h3>' +
          '<p>' +
            (clocks.length === 0
              ? 'No clocks approaching completion.'
              : clocks.length + ' clock' + (clocks.length === 1 ? '' : 's') + ' one tick away') +
          '</p>' +
        '</hgroup>';

    if (clocks.length === 0) {
      html +=
        '<div class="gm-dashboard__empty" role="status">' +
          '<p>No clocks are near completion.</p>' +
        '</div>';
    } else {
      html += '<ul class="gm-dashboard__clock-list">';
      for (var i = 0; i < clocks.length; i++) {
        var clock = clocks[i];
        var href = window.utils.esc(_clockDetailPath(clock));
        var assocLabel = clock.associated_type
          ? window.utils.esc(clock.associated_type.replace(/_/g, " "))
          : "";

        html +=
          '<li class="gm-dashboard__clock-item">' +
            '<a href="' + href + '" class="gm-dashboard__clock-link">' +
              '<span class="gm-dashboard__clock-name">' + window.utils.esc(clock.name) + '</span>' +
              '<span class="gm-dashboard__clock-meta">' +
                _clockProgress(clock.progress, clock.segments) +
                (assocLabel ? ' &middot; ' + assocLabel : '') +
              '</span>' +
            '</a>' +
          '</li>';
      }
      html += '</ul>';
    }

    html += '</section>';
    return html;
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  /**
   * Build a name-lookup map from the pc_summaries array.
   * @param {Array} pcs
   * @returns {object} { id: name }
   */
  function _buildNameMap(pcs) {
    var map = {};
    for (var i = 0; i < pcs.length; i++) {
      map[pcs[i].id] = pcs[i].name;
    }
    return map;
  }

  /**
   * Re-render the full dashboard into _viewEl using the current _data.
   */
  function _renderList() {
    if (!_viewEl || !_mounted) return;

    var proposals = (_data && _data.pending_proposals)    ? _data.pending_proposals    : [];
    var pcs       = (_data && _data.pc_summaries)         ? _data.pc_summaries         : [];
    var clocks    = (_data && _data.near_completion_clocks) ? _data.near_completion_clocks : [];

    // Build a name-map from pc_summaries so proposals can show character names
    // without an extra API call (dashboard already includes this data).
    var nameMap = _buildNameMap(pcs);

    var html =
      '<div class="gm-dashboard">' +
        '<hgroup>' +
          '<h2>GM Dashboard</h2>' +
          '<p>Campaign overview</p>' +
        '</hgroup>' +
        _renderProposalsSection(proposals, nameMap) +
        _renderPcSection(pcs) +
        _renderClocksSection(clocks) +
      '</div>';

    _viewEl.innerHTML = html;
  }

  /**
   * Render the loading state.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-dashboard">' +
        '<hgroup>' +
          '<h2>GM Dashboard</h2>' +
          '<p aria-busy="true">Loading...</p>' +
        '</hgroup>' +
      '</div>';
  }

  /**
   * Render an error state with a retry button.
   */
  function _renderError() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-dashboard">' +
        '<hgroup>' +
          '<h2>GM Dashboard</h2>' +
        '</hgroup>' +
        '<p class="error-text" role="alert">Failed to load dashboard data.</p>' +
        '<button id="gm-dashboard-retry">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("gm-dashboard-retry");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () { _fetchDashboard(false); });
    }
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Fetch the dashboard data and re-render.
   * Called on mount and by the poll callback.
   *
   * @param {boolean} [isInitial] — if true, show loading state first
   */
  function _fetchDashboard(isInitial) {
    if (!_mounted) return;

    if (isInitial) {
      _renderLoading();
    }

    api
      .get(DASHBOARD_URL)
      .then(function (data) {
        if (!_mounted) return;
        _data = data || {};
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
   * Updates _data and re-renders without disrupting any in-flight requests.
   *
   * @param {object} data — parsed response from GET /api/v1/gm/dashboard
   */
  function _pollCallback(data) {
    if (!_mounted) return;
    _data = data || {};
    _renderList();
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
    _data = null;

    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").unregisterPoll(POLL_KEY);
    }
  }

  /**
   * One-time hashchange listener that calls _teardown when leaving this view.
   * Removes itself after first navigation away.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/gm") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the GM Dashboard view.
   * Called by router.js for the "/gm" route.
   */
  return function render() {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // Guard: only GMs should see this view
    if (!window.utils.requireGm(_viewEl)) return;

    // Reset state for a fresh mount
    _mounted = true;
    _data = null;

    // Initial fetch (shows loading state first)
    _fetchDashboard(true);

    // Register 60-second polling
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").registerPoll(POLL_KEY, {
        url: DASHBOARD_URL,
        intervalMs: POLL_INTERVAL_MS,
        callback: _pollCallback,
      });
    }

    // Teardown when navigating away
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
