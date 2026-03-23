/* Wizards Engine — Session Detail + Timeline view
 *
 * Routes:
 *   #/gm/sessions/:id              — session detail (read-only / edit for draft)
 *   #/gm/sessions/:id/edit         — open in edit mode directly
 *   #/gm/sessions/:id/timeline     — session event timeline
 *
 * Features:
 *   - Fetches GET /api/v1/sessions/{id} to show detail and participants
 *   - Timeline tab: GET /api/v1/sessions/{id}/timeline with cursor pagination
 *   - Registers 30s polling on the timeline for active sessions only
 *   - Unregisters polling on hashchange away from this view
 *   - Renders timeline items using window.components.feedItem
 *
 * Registers as:  window.views.sessionDetail
 * Called by:     router.js parameterized route entries for "/gm/sessions/:id/*"
 */

window.views = window.views || {};

window.views.sessionDetail = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var POLL_KEY         = "session-timeline";
  var POLL_INTERVAL_MS = 30000;
  var TIMELINE_LIMIT   = 20;

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** Currently viewed session id. */
  var _sessionId = null;

  /** Loaded session detail object (includes participants). */
  var _session = null;

  /** Current active tab: 'detail' | 'timeline' */
  var _activeTab = "detail";

  /** Timeline items (newest-first, as returned by the API). */
  var _timelineItems = [];

  /** ULID cursor for timeline pagination (next page). */
  var _timelineCursor = null;

  /** Whether there are more timeline pages. */
  var _timelineHasMore = false;

  /** Whether a timeline fetch is in flight. */
  var _timelineLoading = false;

  /** Whether we are the currently mounted view. */
  var _mounted = false;

  /** The #view element. */
  var _viewEl = null;

  /** Whether the edit form is open. */
  var _editMode = false;

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  function _formatDate(dateStr) {
    if (!dateStr) return "";
    try {
      var d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString();
    } catch (_) { return dateStr; }
  }

  function _statusBadge(status) {
    var map = {
      active:  { label: "Active",  cls: "session-badge--active"  },
      draft:   { label: "Draft",   cls: "session-badge--draft"   },
      ended:   { label: "Ended",   cls: "session-badge--ended"   },
    };
    var info = map[status] || { label: status || "Unknown", cls: "session-badge--unknown" };
    return '<mark class="session-badge ' + window.utils.esc(info.cls) + '">' + window.utils.esc(info.label) + '</mark>';
  }

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="session-detail">' +
        '<p aria-busy="true">Loading session...</p>' +
      '</div>';
  }

  function _renderError(msg) {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="session-detail">' +
        '<p class="error-text" role="alert">' + window.utils.esc(msg || "Failed to load session.") + '</p>' +
        '<a href="#/gm/sessions" class="outline secondary">Back to Sessions</a>' +
      '</div>';
  }

  // ---------------------------------------------------------------------------
  // Main shell (tabs)
  // ---------------------------------------------------------------------------

  function _renderShell() {
    if (!_viewEl || !_mounted || !_session) return;

    var status  = _session.status || "draft";
    var summary = _session.summary || "Untitled Session";

    var html =
      '<div class="session-detail">' +
        '<div class="session-detail__breadcrumb">' +
          '<a href="#/gm/sessions">&larr; Sessions</a>' +
        '</div>' +
        '<hgroup>' +
          '<h2>' + window.utils.esc(summary) + '</h2>' +
          _statusBadge(status) +
        '</hgroup>' +
        '<nav class="session-detail__tabs" role="tablist">' +
          '<button id="tab-btn-detail"' +
          '        class="session-tab' + (_activeTab === "detail" ? " session-tab--active" : "") + '"' +
          '        role="tab"' +
          '        aria-selected="' + (_activeTab === "detail" ? "true" : "false") + '">' +
          'Detail' +
          '</button>' +
          '<button id="tab-btn-timeline"' +
          '        class="session-tab' + (_activeTab === "timeline" ? " session-tab--active" : "") + '"' +
          '        role="tab"' +
          '        aria-selected="' + (_activeTab === "timeline" ? "true" : "false") + '">' +
          'Timeline' +
          '</button>' +
        '</nav>' +
        '<div id="session-tab-content">' +
        '</div>' +
      '</div>';

    _viewEl.innerHTML = html;

    document.getElementById("tab-btn-detail").addEventListener("click", function () {
      _activeTab = "detail";
      _stopTimelinePoll();
      _renderTabContent();
    });

    document.getElementById("tab-btn-timeline").addEventListener("click", function () {
      _activeTab = "timeline";
      _renderTabContent();
    });

    _renderTabContent();
  }

  function _renderTabContent() {
    // Update tab button active state
    var detailBtn   = document.getElementById("tab-btn-detail");
    var timelineBtn = document.getElementById("tab-btn-timeline");
    if (detailBtn) {
      detailBtn.classList.toggle("session-tab--active", _activeTab === "detail");
      detailBtn.setAttribute("aria-selected", _activeTab === "detail" ? "true" : "false");
    }
    if (timelineBtn) {
      timelineBtn.classList.toggle("session-tab--active", _activeTab === "timeline");
      timelineBtn.setAttribute("aria-selected", _activeTab === "timeline" ? "true" : "false");
    }

    var content = document.getElementById("session-tab-content");
    if (!content) return;

    if (_activeTab === "detail") {
      _stopTimelinePoll();
      if (_editMode) {
        content.innerHTML = _buildEditFormHtml();
        _bindEditForm();
      } else {
        content.innerHTML = _buildDetailHtml();
        _bindDetailEvents();
      }
    } else {
      // Timeline tab
      if (_timelineItems.length === 0 && !_timelineLoading) {
        _fetchTimeline(true);
      } else {
        _renderTimelineContent();
      }
      // Register polling only for active sessions
      if (_session && _session.status === "active") {
        _startTimelinePoll();
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Detail tab
  // ---------------------------------------------------------------------------

  function _buildDetailHtml() {
    if (!_session) return "";

    var status   = _session.status || "draft";
    var date     = _formatDate(_session.date);
    var timeNow  = _session.time_now != null ? _session.time_now : "";
    var summary  = _session.summary || "";
    var notes    = _session.notes || "";
    var participants = _session.participants || [];
    var isDraft  = status === "draft";
    var isActive = status === "active";

    var metaHtml = '<dl class="session-detail__meta">';
    if (date)        metaHtml += '<dt>Date</dt><dd>' + window.utils.esc(date) + '</dd>';
    if (timeNow !== "") metaHtml += '<dt>Time Now</dt><dd>' + window.utils.esc(String(timeNow)) + ' hours</dd>';
    if (summary)     metaHtml += '<dt>Summary</dt><dd>' + window.utils.esc(summary) + '</dd>';
    if (notes)       metaHtml += '<dt>Notes</dt><dd>' + window.utils.esc(notes) + '</dd>';
    metaHtml += '</dl>';

    // Participants table
    var partHtml = '<h3>Participants</h3>';
    if (participants.length === 0) {
      partHtml += '<p>No participants.</p>';
    } else {
      partHtml += '<table><thead><tr><th>Character</th><th>Extra Contribution</th></tr></thead><tbody>';
      for (var i = 0; i < participants.length; i++) {
        var p = participants[i];
        var charName = p.character_id || "Unknown";
        partHtml +=
          '<tr>' +
            '<td>' + window.utils.esc(charName) + '</td>' +
            '<td>' + (p.additional_contribution ? "Yes" : "No") + '</td>' +
          '</tr>';
      }
      partHtml += '</tbody></table>';
    }

    // Action buttons (GM only)
    var actionsHtml = "";
    if (window.utils.isGm()) {
      actionsHtml = '<div class="session-detail__actions">';
      if (isDraft) {
        actionsHtml += '<button id="detail-edit-btn">Edit</button> ';
        actionsHtml += '<button id="detail-start-btn">Start Session</button> ';
        actionsHtml += '<button class="outline secondary" id="detail-delete-btn">Delete</button> ';
      }
      if (isActive) {
        actionsHtml += '<button class="outline secondary" id="detail-end-btn">End Session</button> ';
      }
      actionsHtml += '</div>';
    }

    return metaHtml + partHtml + actionsHtml;
  }

  function _bindDetailEvents() {
    var editBtn   = document.getElementById("detail-edit-btn");
    var startBtn  = document.getElementById("detail-start-btn");
    var deleteBtn = document.getElementById("detail-delete-btn");
    var endBtn    = document.getElementById("detail-end-btn");

    if (editBtn) {
      editBtn.addEventListener("click", function () {
        _editMode = true;
        _renderTabContent();
      });
    }

    if (startBtn) {
      startBtn.addEventListener("click", function () {
        _doStart(_session.id);
      });
    }

    if (endBtn) {
      endBtn.addEventListener("click", function () {
        _doEnd(_session.id);
      });
    }

    if (deleteBtn) {
      deleteBtn.addEventListener("click", function () {
        _doDelete(_session.id);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Inline edit form (on detail tab)
  // ---------------------------------------------------------------------------

  function _buildEditFormHtml() {
    if (!_session) return "";
    var dateValue = _session.date ? _session.date.slice(0, 10) : "";
    return (
      '<form id="sd-edit-form">' +
        '<label for="sd-summary">Summary<br>' +
          '<input type="text" id="sd-summary" name="summary" value="' + window.utils.esc(_session.summary || "") + '" maxlength="200">' +
        '</label>' +
        '<label for="sd-date">Date<br>' +
          '<input type="date" id="sd-date" name="date" value="' + window.utils.esc(dateValue) + '">' +
        '</label>' +
        '<label for="sd-time-now">Time Now (hours)<br>' +
          '<input type="number" id="sd-time-now" name="time_now" min="0" max="999" step="1" inputmode="numeric" value="' + window.utils.esc(_session.time_now != null ? String(_session.time_now) : "") + '">' +
        '</label>' +
        '<label for="sd-notes">Notes<br>' +
          '<textarea id="sd-notes" name="notes" rows="3">' + window.utils.esc(_session.notes || "") + '</textarea>' +
        '</label>' +
        '<div class="sessions-form__actions">' +
          '<button type="submit" id="sd-edit-save">Save</button> ' +
          '<button type="button" id="sd-edit-cancel" class="outline secondary">Cancel</button>' +
        '</div>' +
      '</form>'
    );
  }

  function _bindEditForm() {
    var form = document.getElementById("sd-edit-form");
    var cancelBtn = document.getElementById("sd-edit-cancel");

    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        _editMode = false;
        _renderTabContent();
      });
    }

    if (form) {
      form.addEventListener("submit", function (evt) {
        evt.preventDefault();
        _submitEdit(form);
      });
    }
  }

  function _submitEdit(form) {
    var saveBtn = document.getElementById("sd-edit-save");
    if (saveBtn) { saveBtn.setAttribute("aria-busy", "true"); saveBtn.disabled = true; }

    var summaryEl = form.querySelector('[name="summary"]');
    var dateEl    = form.querySelector('[name="date"]');
    var timeNowEl = form.querySelector('[name="time_now"]');
    var notesEl   = form.querySelector('[name="notes"]');

    var body = {
      summary:  summaryEl  ? summaryEl.value.trim()  : null,
      date:     dateEl     ? (dateEl.value || null)  : null,
      time_now: timeNowEl  ? (timeNowEl.value !== "" ? Number(timeNowEl.value) : null) : null,
      notes:    notesEl    ? (notesEl.value.trim() || null) : null,
    };

    api
      .patch("/api/v1/sessions/" + encodeURIComponent(_sessionId), body)
      .then(function (updated) {
        if (!_mounted) return;
        _session = Object.assign({}, _session, updated, { participants: _session.participants });
        _editMode = false;
        window.utils.showSuccess("Session updated.");
        _renderShell();
      })
      .catch(function () {
        if (saveBtn) { saveBtn.removeAttribute("aria-busy"); saveBtn.disabled = false; }
      });
  }

  // ---------------------------------------------------------------------------
  // Session lifecycle actions (from detail tab)
  // ---------------------------------------------------------------------------

  function _doStart(id) {
    api
      .post("/api/v1/sessions/" + encodeURIComponent(id) + "/start", {})
      .then(function (updated) {
        if (!_mounted) return;
        _session = Object.assign({}, _session, updated, { participants: _session.participants });
        window.utils.showSuccess("Session started.");
        _renderShell();
      })
      .catch(function () { /* toast shown by api.js */ });
  }

  function _doEnd(id) {
    api
      .post("/api/v1/sessions/" + encodeURIComponent(id) + "/end", {})
      .then(function (updated) {
        if (!_mounted) return;
        _session = Object.assign({}, _session, updated, { participants: _session.participants });
        window.utils.showSuccess("Session ended.");
        _renderShell();
      })
      .catch(function () { /* toast shown by api.js */ });
  }

  function _doDelete(id) {
    if (!confirm("Delete this draft session? This cannot be undone.")) return;
    api
      .del("/api/v1/sessions/" + encodeURIComponent(id))
      .then(function () {
        if (!_mounted) return;
        window.utils.showSuccess("Session deleted.");
        window.location.hash = "#/gm/sessions";
      })
      .catch(function () { /* toast shown by api.js */ });
  }

  // ---------------------------------------------------------------------------
  // Timeline tab
  // ---------------------------------------------------------------------------

  function _renderTimelineContent() {
    var content = document.getElementById("session-tab-content");
    if (!content || !_mounted) return;

    if (_timelineLoading && _timelineItems.length === 0) {
      content.innerHTML = '<p class="feed-list__loading" aria-busy="true">Loading timeline...</p>';
      return;
    }

    if (!_timelineLoading && _timelineItems.length === 0) {
      content.innerHTML = '<p class="session-timeline__empty">No events in this session yet.</p>';
      return;
    }

    var html = '<div class="session-timeline">';

    for (var i = 0; i < _timelineItems.length; i++) {
      var item = _timelineItems[i];
      // Use feedItem component if available, otherwise fall back to simple text
      if (typeof window.components !== "undefined" && window.components.feedItem) {
        html += window.components.feedItem.render({
          item: item,
          type: item.type || "event",
          isOwn: false,
        });
      } else {
        var eventType = item.event_type || item.type || "";
        var narrative = item.narrative || item.description || "";
        var ts        = item.created_at || item.timestamp || "";
        html +=
          '<div class="feed-item feed-item--event">' +
            '<div class="feed-item__meta">' +
              '<span class="feed-item__action">' + window.utils.esc(eventType) + '</span>' +
              (ts ? '<time class="feed-item__time">' + window.utils.esc(ts) + '</time>' : '') +
            '</div>' +
            (narrative ? '<p class="feed-item__narrative">' + window.utils.esc(narrative) + '</p>' : '') +
          '</div>';
      }
    }

    html += '</div>';

    if (_timelineHasMore || _timelineLoading) {
      html +=
        '<div class="feed-list__more">' +
          '<button id="timeline-load-more"' +
          '        class="outline secondary"' +
          '        ' + (_timelineLoading ? 'aria-busy="true" disabled' : '') + '>' +
          (_timelineLoading ? 'Loading...' : 'Load more') +
          '</button>' +
        '</div>';
    }

    content.innerHTML = html;

    var loadMoreBtn = document.getElementById("timeline-load-more");
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", function () {
        _fetchTimeline(false);
      });
    }
  }

  function _fetchTimeline(reset) {
    if (!_mounted || _timelineLoading) return;
    _timelineLoading = true;

    if (reset) {
      _timelineItems  = [];
      _timelineCursor = null;
      _timelineHasMore = false;
    }

    _renderTimelineContent();

    var url = "/api/v1/sessions/" + encodeURIComponent(_sessionId) + "/timeline" +
              "?limit=" + TIMELINE_LIMIT;
    if (!reset && _timelineCursor) {
      url += "&after=" + encodeURIComponent(_timelineCursor);
    }

    api
      .get(url)
      .then(function (data) {
        if (!_mounted) return;
        var incoming = (data && data.items) ? data.items : [];
        _timelineCursor = (data && data.next_cursor) ? data.next_cursor : null;
        _timelineHasMore = !!(data && data.has_more);

        if (reset) {
          _timelineItems = incoming;
        } else {
          _timelineItems = _timelineItems.concat(incoming);
        }
      })
      .catch(function () {
        // api.js shows the toast; leave existing items in place
      })
      .finally(function () {
        _timelineLoading = false;
        if (_mounted && _activeTab === "timeline") {
          _renderTimelineContent();
        }
      });
  }

  // ---------------------------------------------------------------------------
  // Timeline polling
  // ---------------------------------------------------------------------------

  function _startTimelinePoll() {
    if (typeof Alpine === "undefined" || !Alpine.store("app")) return;

    var url = "/api/v1/sessions/" + encodeURIComponent(_sessionId) + "/timeline" +
              "?limit=" + TIMELINE_LIMIT;

    Alpine.store("app").registerPoll(POLL_KEY, {
      url: url,
      intervalMs: POLL_INTERVAL_MS,
      callback: function (data) {
        if (!_mounted || _activeTab !== "timeline") return;
        var incoming = (data && data.items) ? data.items : [];
        // Merge new items at the front: find any items not already in our list
        var existingIds = {};
        for (var i = 0; i < _timelineItems.length; i++) {
          if (_timelineItems[i].id) existingIds[_timelineItems[i].id] = true;
        }
        var newItems = [];
        for (var j = 0; j < incoming.length; j++) {
          if (!existingIds[incoming[j].id]) {
            newItems.push(incoming[j]);
          }
        }
        if (newItems.length > 0) {
          _timelineItems = newItems.concat(_timelineItems);
          _renderTimelineContent();
        }
      },
    });
  }

  function _stopTimelinePoll() {
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").unregisterPoll(POLL_KEY);
    }
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  function _fetchSessionDetail() {
    _renderLoading();

    api
      .get("/api/v1/sessions/" + encodeURIComponent(_sessionId))
      .then(function (data) {
        if (!_mounted) return;
        _session = data;
        _renderShell();

        // If starting on timeline tab, kick off the timeline fetch and poll
        if (_activeTab === "timeline") {
          _fetchTimeline(true);
          if (data && data.status === "active") {
            _startTimelinePoll();
          }
        }
      })
      .catch(function () {
        if (!_mounted) return;
        _renderError("Failed to load session.");
      });
  }

  // ---------------------------------------------------------------------------
  // Teardown and hashchange
  // ---------------------------------------------------------------------------

  function _teardown() {
    _mounted = false;
    _editMode = false;
    _stopTimelinePoll();
    _timelineItems   = [];
    _timelineCursor  = null;
    _timelineHasMore = false;
    _timelineLoading = false;
  }

  function _isOnThisView(path) {
    if (!_sessionId) return false;
    var prefix = "/gm/sessions/" + _sessionId;
    return path === prefix ||
           path === prefix + "/timeline" ||
           path === prefix + "/edit";
  }

  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (!_isOnThisView(path)) {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Mount the session detail view for a given session id.
   * Called by router.js for the parameterized /gm/sessions/:id routes.
   *
   * @param {string} id     — session ULID
   * @param {object} [opts] — { tab: 'timeline' } | { edit: true }
   */
  return function render(id, opts) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    if (!window.utils.isGm()) {
      _viewEl.innerHTML =
        '<div class="session-detail">' +
          '<p class="error-text" role="alert">Access denied — GM only.</p>' +
        '</div>';
      return;
    }

    // Reset state for fresh mount
    _sessionId       = id;
    _session         = null;
    _mounted         = true;
    _editMode        = !!(opts && opts.edit);
    _timelineItems   = [];
    _timelineCursor  = null;
    _timelineHasMore = false;
    _timelineLoading = false;

    _activeTab = (opts && opts.tab === "timeline") ? "timeline" : "detail";

    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);

    _fetchSessionDetail();
  };
})();
