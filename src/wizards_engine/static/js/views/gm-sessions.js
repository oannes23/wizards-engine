/* Wizards Engine — GM Sessions view
 *
 * Route:  #/gm/sessions  and  #/gm/sessions/new
 * Access: GM only
 *
 * Displays a DataTable of sessions (active → draft → ended order).
 * Supports creating new sessions, starting/ending sessions, editing draft
 * sessions, managing participants, and navigating to session detail/timeline.
 *
 * Registers as:  window.views.gmSessions
 * Called by:     router.js route entries for "/gm/sessions" and "/gm/sessions/new"
 *
 * Dependencies (loaded before this file):
 *   data-table.js  — window.components.DataTable
 *   utils.js       — window.utils.esc, window.utils.requireGm, window.utils.showSuccess
 */

window.views = window.views || {};

window.views.gmSessions = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var SESSIONS_URL = "/api/v1/sessions";
  var CHARACTERS_URL = "/api/v1/characters/summary";

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** All loaded sessions, flat. */
  var _sessions = [];

  /** All characters loaded for participant picker. */
  var _characters = [];

  /** Whether we are the currently mounted view. */
  var _mounted = false;

  /** The #view element. */
  var _viewEl = null;

  /** Current UI mode: 'list' | 'create' | 'edit' | 'participants' | 'confirm-start' | 'confirm-end' | 'confirm-delete' */
  var _mode = "list";

  /** ID of the session currently being acted on. */
  var _activeSessionId = null;

  /** In-flight flag map keyed by session id. */
  var _inflightIds = {};

  /** DataTable instance for the session list. Null when not in list mode. */
  var _table = null;

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /** Find a session by id from _sessions. */
  function _findSession(id) {
    for (var i = 0; i < _sessions.length; i++) {
      if (_sessions[i].id === id) return _sessions[i];
    }
    return null;
  }

  /** Find a character by id from _characters. */
  function _findCharacter(id) {
    for (var i = 0; i < _characters.length; i++) {
      if (_characters[i].id === id) return _characters[i];
    }
    return null;
  }

  /** Format a date string for display (YYYY-MM-DD → locale date). */
  function _formatDate(dateStr) {
    if (!dateStr) return "";
    try {
      var d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString();
    } catch (_) {
      return dateStr;
    }
  }

  /** Destroy the DataTable instance if it exists. */
  function _destroyTable() {
    if (_table) {
      _table.destroy();
      _table = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Status badge helper
  // ---------------------------------------------------------------------------

  /**
   * Return HTML for a session status badge.
   * Uses the .session-status-badge base class with a status-specific modifier.
   * @param {string} status — "active" | "draft" | "ended"
   * @returns {string} HTML string
   */
  function _statusBadge(status) {
    var map = {
      active: { label: "Active", cls: "session-status-badge--active" },
      draft:  { label: "Draft",  cls: "session-status-badge--draft"  },
      ended:  { label: "Ended",  cls: "session-status-badge--ended"  },
    };
    var info = map[status] || { label: status || "Unknown", cls: "session-status-badge--unknown" };
    return (
      '<mark class="session-status-badge ' +
      window.utils.esc(info.cls) +
      '">' +
      window.utils.esc(info.label) +
      '</mark>'
    );
  }

  // ---------------------------------------------------------------------------
  // Participant avatar helper
  // ---------------------------------------------------------------------------

  /**
   * Return HTML for overlapping initials circles for a participants array.
   * Shows up to 4 avatars; if more, shows "+N" overflow pill.
   * @param {Array} participants — array of participant objects with character_id
   * @returns {string} HTML string
   */
  function _participantAvatars(participants) {
    if (!participants || participants.length === 0) {
      return '<span class="session-participants--empty">—</span>';
    }

    var MAX_VISIBLE = 4;
    var html = '<span class="session-participants">';

    var visible = participants.slice(0, MAX_VISIBLE);
    for (var i = 0; i < visible.length; i++) {
      var p = visible[i];
      var chr = _findCharacter(p.character_id);
      var name = chr ? (chr.name || chr.display_name || "") : "";
      var initial = name ? name.charAt(0).toUpperCase() : "?";
      var title = name ? window.utils.esc(name) : window.utils.esc(p.character_id || "");
      html +=
        '<span class="session-avatar" title="' + title + '">' +
          window.utils.esc(initial) +
        '</span>';
    }

    if (participants.length > MAX_VISIBLE) {
      var overflow = participants.length - MAX_VISIBLE;
      html +=
        '<span class="session-avatar session-avatar--overflow">+' +
          window.utils.esc(String(overflow)) +
        '</span>';
    }

    html += '</span>';
    return html;
  }

  // ---------------------------------------------------------------------------
  // Row actions renderer
  // ---------------------------------------------------------------------------

  /**
   * Return HTML for per-row action buttons based on session status.
   * Rendered inside a custom DataTable cell (not via rowActions API, because
   * the button set differs by status).
   * @param {object} session
   * @returns {string} HTML string
   */
  function _rowActionsHtml(session) {
    var id     = session.id || "";
    var status = session.status || "draft";
    var esc    = window.utils.esc;
    var html   = '<div class="session-row-actions">';

    if (status === "draft") {
      html +=
        '<button class="session-row-btn outline secondary" ' +
        'data-action="edit-session" data-id="' + esc(id) + '">Edit</button> ' +
        '<button class="session-row-btn outline secondary" ' +
        'data-action="manage-participants" data-id="' + esc(id) + '">Participants</button> ' +
        '<button class="session-row-btn" ' +
        'data-action="confirm-start" data-id="' + esc(id) + '">Start</button> ' +
        '<button class="session-row-btn outline secondary" ' +
        'data-action="confirm-delete" data-id="' + esc(id) + '">Delete</button>';
    } else if (status === "active") {
      html +=
        '<button class="session-row-btn outline secondary" ' +
        'data-action="manage-participants" data-id="' + esc(id) + '">Participants</button> ' +
        '<button class="session-row-btn outline secondary" ' +
        'data-action="confirm-end" data-id="' + esc(id) + '">End Session</button>';
    } else {
      // ended — view/timeline only (row click handles primary navigation)
      html +=
        '<a href="#/gm/sessions/' + esc(id) + '/timeline" ' +
        'class="session-row-btn outline secondary">Timeline</a>';
    }

    html += '</div>';
    return html;
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="sessions-view">' +
        '<hgroup>' +
          '<h2>Sessions</h2>' +
          '<p aria-busy="true">Loading sessions...</p>' +
        '</hgroup>' +
      '</div>';
  }

  function _renderError(msg) {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="sessions-view">' +
        '<hgroup><h2>Sessions</h2></hgroup>' +
        '<p class="error-text" role="alert">' +
          window.utils.esc(msg || "Failed to load sessions.") +
        '</p>' +
        '<button id="sessions-retry">Retry</button>' +
      '</div>';
    var btn = document.getElementById("sessions-retry");
    if (btn) btn.addEventListener("click", function () { _fetchSessions(true); });
  }

  // ---------------------------------------------------------------------------
  // Session list render (DataTable)
  // ---------------------------------------------------------------------------

  /**
   * Return a display name for a session row.
   * Uses summary if available, otherwise falls back to "Untitled Session".
   * @param {object} session
   * @returns {string}
   */
  function _sessionDisplayName(session) {
    return session.summary ? session.summary.slice(0, 80) : "Untitled Session";
  }

  /**
   * Sort sessions so Active comes first, then Draft, then Ended.
   * @param {Array} sessions
   * @returns {Array}
   */
  function _sortedSessions(sessions) {
    var order = { active: 0, draft: 1, ended: 2 };
    return sessions.slice().sort(function (a, b) {
      var oa = order[a.status] != null ? order[a.status] : 3;
      var ob = order[b.status] != null ? order[b.status] : 3;
      return oa - ob;
    });
  }

  function _renderList() {
    if (!_viewEl || !_mounted) return;

    _destroyTable();

    var html =
      '<div class="sessions-view">' +
        '<div class="sessions-view__header">' +
          '<h2>Sessions</h2>' +
          '<button id="sessions-create-btn">+ New Session</button>' +
        '</div>' +
        '<div id="sessions-table-container"></div>' +
      '</div>';

    _viewEl.innerHTML = html;

    // Wire create button
    var createBtn = document.getElementById("sessions-create-btn");
    if (createBtn) {
      createBtn.addEventListener("click", function () {
        _mode = "create";
        _activeSessionId = null;
        _destroyTable();
        _renderCreateForm();
      });
    }

    // Wire delegated action buttons (inside the table container)
    var tableContainer = document.getElementById("sessions-table-container");
    if (tableContainer) {
      tableContainer.addEventListener("click", function (evt) {
        var btn = evt.target.closest("[data-action]");
        if (!btn) return;
        var action = btn.getAttribute("data-action");
        var id     = btn.getAttribute("data-id");
        if (!action || !id) return;
        evt.stopPropagation(); // prevent row-click handler

        if (action === "edit-session")        { _openEdit(id); }
        if (action === "confirm-start")       { _openConfirmStart(id); }
        if (action === "confirm-end")         { _openConfirmEnd(id); }
        if (action === "confirm-delete")      { _openConfirmDelete(id); }
        if (action === "manage-participants") { _openParticipants(id); }
      });
    }

    if (!tableContainer) return;

    // Build DataTable columns
    var columns = [
      {
        key:      "summary",
        label:    "Session",
        sortable: true,
        render:   function (val, row) {
          return window.utils.esc(_sessionDisplayName(row));
        },
      },
      {
        key:      "status",
        label:    "Status",
        sortable: true,
        filter:   "select",
        width:    "90px",
        render:   function (val) {
          return _statusBadge(val);
        },
      },
      {
        key:        "date",
        label:      "Date",
        sortable:   true,
        hideMobile: true,
        render:     function (val) {
          return window.utils.esc(_formatDate(val));
        },
      },
      {
        key:        "participants",
        label:      "Participants",
        hideMobile: true,
        render:     function (val) {
          return _participantAvatars(val);
        },
      },
      {
        key:    "_actions",
        label:  "Actions",
        width:  "260px",
        render: function (val, row) {
          return _rowActionsHtml(row);
        },
      },
    ];

    _table = new window.components.DataTable(tableContainer, {
      columns:      columns,
      emptyMessage: "No sessions yet. Click '+ New Session' to create one.",
      onRowClick: function (session) {
        window.location.hash = "#/gm/sessions/" + encodeURIComponent(session.id);
      },
    });

    var sorted = _sortedSessions(_sessions);
    _table.setRows(sorted);
  }

  // ---------------------------------------------------------------------------
  // Create form
  // ---------------------------------------------------------------------------

  function _renderCreateForm() {
    if (!_viewEl || !_mounted) return;
    _viewEl.innerHTML =
      '<div class="sessions-view">' +
        '<hgroup><h2>New Session</h2></hgroup>' +
        '<form id="session-create-form" class="sessions-form">' +
          '<label for="sc-summary">Summary' +
            '<input type="text" id="sc-summary" name="summary" placeholder="Brief description of the session" maxlength="200">' +
          '</label>' +
          '<label for="sc-date">Date' +
            '<input type="date" id="sc-date" name="date">' +
          '</label>' +
          '<label for="sc-time-now">Time Now (hours)' +
            '<input type="number" id="sc-time-now" name="time_now" min="0" max="999" step="1" placeholder="e.g. 4" inputmode="numeric">' +
          '</label>' +
          '<label for="sc-notes">Notes' +
            '<textarea id="sc-notes" name="notes" rows="3" placeholder="GM notes (not shown to players)"></textarea>' +
          '</label>' +
          '<div class="sessions-form__actions">' +
            '<button type="submit" id="session-create-submit">Create Session</button> ' +
            '<button type="button" id="session-create-cancel" class="outline secondary">Cancel</button>' +
          '</div>' +
        '</form>' +
      '</div>';

    var form = document.getElementById("session-create-form");
    var cancelBtn = document.getElementById("session-create-cancel");

    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        _mode = "list";
        _renderList();
      });
    }

    if (form) {
      form.addEventListener("submit", function (evt) {
        evt.preventDefault();
        _submitCreate(form);
      });
    }
  }

  function _submitCreate(form) {
    var submitBtn = document.getElementById("session-create-submit");
    if (submitBtn) {
      submitBtn.setAttribute("aria-busy", "true");
      submitBtn.disabled = true;
    }

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
      .post(SESSIONS_URL, body)
      .then(function (session) {
        if (!_mounted) return;
        _sessions.unshift(session);
        _mode = "list";
        window.utils.showSuccess("Session created.");
        _renderList();
      })
      .catch(function () {
        if (submitBtn) {
          submitBtn.removeAttribute("aria-busy");
          submitBtn.disabled = false;
        }
      });
  }

  // ---------------------------------------------------------------------------
  // Edit form
  // ---------------------------------------------------------------------------

  function _openEdit(id) {
    var session = _findSession(id);
    if (!session) return;
    _mode = "edit";
    _activeSessionId = id;
    _destroyTable();
    _renderEditForm(session);
  }

  function _renderEditForm(session) {
    if (!_viewEl || !_mounted) return;

    var dateValue = session.date ? session.date.slice(0, 10) : "";

    _viewEl.innerHTML =
      '<div class="sessions-view">' +
        '<hgroup><h2>Edit Session</h2></hgroup>' +
        '<form id="session-edit-form" class="sessions-form">' +
          '<label for="se-summary">Summary' +
            '<input type="text" id="se-summary" name="summary" value="' + window.utils.esc(session.summary || "") + '" maxlength="200">' +
          '</label>' +
          '<label for="se-date">Date' +
            '<input type="date" id="se-date" name="date" value="' + window.utils.esc(dateValue) + '">' +
          '</label>' +
          '<label for="se-time-now">Time Now (hours)' +
            '<input type="number" id="se-time-now" name="time_now" min="0" max="999" step="1" inputmode="numeric" value="' + window.utils.esc(session.time_now != null ? String(session.time_now) : "") + '">' +
          '</label>' +
          '<label for="se-notes">Notes' +
            '<textarea id="se-notes" name="notes" rows="3">' + window.utils.esc(session.notes || "") + '</textarea>' +
          '</label>' +
          '<div class="sessions-form__actions">' +
            '<button type="submit" id="session-edit-submit">Save Changes</button> ' +
            '<button type="button" id="session-edit-cancel" class="outline secondary">Cancel</button>' +
          '</div>' +
        '</form>' +
      '</div>';

    var form      = document.getElementById("session-edit-form");
    var cancelBtn = document.getElementById("session-edit-cancel");

    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        _mode = "list";
        _renderList();
      });
    }

    if (form) {
      form.addEventListener("submit", function (evt) {
        evt.preventDefault();
        _submitEdit(session.id, form);
      });
    }
  }

  function _submitEdit(id, form) {
    var submitBtn = document.getElementById("session-edit-submit");
    if (submitBtn) {
      submitBtn.setAttribute("aria-busy", "true");
      submitBtn.disabled = true;
    }

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
      .patch(SESSIONS_URL + "/" + encodeURIComponent(id), body)
      .then(function (updated) {
        if (!_mounted) return;
        for (var i = 0; i < _sessions.length; i++) {
          if (_sessions[i].id === id) {
            _sessions[i] = updated;
            break;
          }
        }
        _mode = "list";
        window.utils.showSuccess("Session updated.");
        _renderList();
      })
      .catch(function () {
        if (submitBtn) {
          submitBtn.removeAttribute("aria-busy");
          submitBtn.disabled = false;
        }
      });
  }

  // ---------------------------------------------------------------------------
  // Confirm dialogs: Start / End / Delete
  // ---------------------------------------------------------------------------

  function _openConfirmStart(id) {
    var session = _findSession(id);
    if (!session) return;
    _mode = "confirm-start";
    _activeSessionId = id;
    _destroyTable();

    var timeNow = session.time_now != null ? session.time_now : 0;
    var infoHtml =
      '<p>Starting this session will:</p>' +
      '<ul>' +
        '<li>Distribute <strong>' + window.utils.esc(String(timeNow)) + '</strong> hour(s) of Free Time to all participants</li>' +
        '<li>Award 1 Plot point to each participant</li>' +
        '<li>Move the session from <em>Draft</em> to <em>Active</em></li>' +
      '</ul>';

    _renderConfirmDialog({
      title:   "Start Session",
      body:    infoHtml,
      confirm: "Start Session",
      cancel:  "Cancel",
      onConfirm: function () { _doStart(id); },
    });
  }

  function _openConfirmEnd(id) {
    _mode = "confirm-end";
    _activeSessionId = id;
    _destroyTable();

    _renderConfirmDialog({
      title:   "End Session",
      body:    "<p>Are you sure you want to end this session? This cannot be undone.</p>",
      confirm: "End Session",
      cancel:  "Cancel",
      onConfirm: function () { _doEnd(id); },
    });
  }

  function _openConfirmDelete(id) {
    _mode = "confirm-delete";
    _activeSessionId = id;
    _destroyTable();

    _renderConfirmDialog({
      title:   "Delete Session",
      body:    "<p>Delete this draft session? This cannot be undone.</p>",
      confirm: "Delete",
      cancel:  "Cancel",
      onConfirm: function () { _doDelete(id); },
    });
  }

  function _renderConfirmDialog(opts) {
    if (!_viewEl || !_mounted) return;
    _viewEl.innerHTML =
      '<div class="sessions-view">' +
        '<hgroup><h2>' + window.utils.esc(opts.title) + '</h2></hgroup>' +
        opts.body +
        '<div class="sessions-form__actions">' +
          '<button id="confirm-yes">' + window.utils.esc(opts.confirm) + '</button> ' +
          '<button id="confirm-no" class="outline secondary">' + window.utils.esc(opts.cancel) + '</button>' +
        '</div>' +
      '</div>';

    var yesBtn = document.getElementById("confirm-yes");
    var noBtn  = document.getElementById("confirm-no");

    if (noBtn) {
      noBtn.addEventListener("click", function () {
        _mode = "list";
        _renderList();
      });
    }

    if (yesBtn) {
      yesBtn.addEventListener("click", function () {
        yesBtn.setAttribute("aria-busy", "true");
        yesBtn.disabled = true;
        opts.onConfirm();
      });
    }
  }

  function _doStart(id) {
    if (_inflightIds[id]) return;
    _inflightIds[id] = true;

    api
      .post(SESSIONS_URL + "/" + encodeURIComponent(id) + "/start", {})
      .then(function (updated) {
        if (!_mounted) return;
        delete _inflightIds[id];
        for (var i = 0; i < _sessions.length; i++) {
          if (_sessions[i].id === id) { _sessions[i] = updated; break; }
        }
        _mode = "list";
        window.utils.showSuccess("Session started.");
        _renderList();
      })
      .catch(function () {
        if (!_mounted) return;
        delete _inflightIds[id];
        _mode = "list";
        _renderList();
      });
  }

  function _doEnd(id) {
    if (_inflightIds[id]) return;
    _inflightIds[id] = true;

    api
      .post(SESSIONS_URL + "/" + encodeURIComponent(id) + "/end", {})
      .then(function (updated) {
        if (!_mounted) return;
        delete _inflightIds[id];
        for (var i = 0; i < _sessions.length; i++) {
          if (_sessions[i].id === id) { _sessions[i] = updated; break; }
        }
        _mode = "list";
        window.utils.showSuccess("Session ended.");
        _renderList();
      })
      .catch(function () {
        if (!_mounted) return;
        delete _inflightIds[id];
        _mode = "list";
        _renderList();
      });
  }

  function _doDelete(id) {
    if (_inflightIds[id]) return;
    _inflightIds[id] = true;

    api
      .del(SESSIONS_URL + "/" + encodeURIComponent(id))
      .then(function () {
        if (!_mounted) return;
        delete _inflightIds[id];
        _sessions = _sessions.filter(function (s) { return s.id !== id; });
        _mode = "list";
        window.utils.showSuccess("Session deleted.");
        _renderList();
      })
      .catch(function () {
        if (!_mounted) return;
        delete _inflightIds[id];
        _mode = "list";
        _renderList();
      });
  }

  // ---------------------------------------------------------------------------
  // Participant management
  // ---------------------------------------------------------------------------

  function _openParticipants(id) {
    _mode = "participants";
    _activeSessionId = id;
    _destroyTable();

    // Fetch session detail and characters in parallel
    var sessionDetailP = api.get(SESSIONS_URL + "/" + encodeURIComponent(id));
    var charactersP = _characters.length > 0
      ? Promise.resolve({ items: _characters })
      : api.get(CHARACTERS_URL);

    Promise.all([sessionDetailP, charactersP])
      .then(function (results) {
        if (!_mounted) return;
        var detail   = results[0];
        var charData = results[1];
        _characters = (charData && charData.items) ? charData.items : _characters;
        _renderParticipants(detail);
      })
      .catch(function () {
        if (!_mounted) return;
        _renderError("Failed to load participant data.");
      });
  }

  function _renderParticipants(sessionDetail) {
    if (!_viewEl || !_mounted) return;

    var id           = sessionDetail.id || _activeSessionId;
    var participants = sessionDetail.participants || [];
    var status       = sessionDetail.status || "draft";
    var isDraft      = status === "draft";

    // Build a set of already-added character ids
    var addedIds = {};
    for (var i = 0; i < participants.length; i++) {
      addedIds[participants[i].character_id] = true;
    }

    // Current participants list
    var participantRows = "";
    for (var j = 0; j < participants.length; j++) {
      var p   = participants[j];
      var chr = _findCharacter(p.character_id);
      var charName = chr ? chr.name : (p.character_id || "Unknown");
      var addlChecked = p.additional_contribution ? ' checked' : '';
      var removeBtn = isDraft
        ? '<button class="outline secondary sm" data-action="remove-participant" data-session-id="' + window.utils.esc(id) + '" data-char-id="' + window.utils.esc(p.character_id) + '">Remove</button>'
        : "";

      participantRows +=
        '<tr>' +
          '<td>' + window.utils.esc(charName) + '</td>' +
          '<td>' +
            '<input type="checkbox" class="participant-addl" aria-label="Additional contribution"' +
            ' data-session-id="' + window.utils.esc(id) + '"' +
            ' data-char-id="' + window.utils.esc(p.character_id) + '"' +
            (isDraft ? '' : ' disabled') +
            addlChecked + '>' +
          '</td>' +
          '<td>' + removeBtn + '</td>' +
        '</tr>';
    }

    // Available characters to add
    var available = _characters.filter(function (c) { return !addedIds[c.id]; });
    var addOptions = '<option value="">Select a character...</option>';
    for (var k = 0; k < available.length; k++) {
      addOptions += '<option value="' + window.utils.esc(available[k].id) + '">' + window.utils.esc(available[k].name) + '</option>';
    }

    var addRowHtml = (isDraft || status === "active")
      ? '<div class="participant-add-row">' +
          '<select id="participant-char-select">' + addOptions + '</select> ' +
          '<button id="participant-add-btn" type="button">Add Participant</button>' +
        '</div>'
      : "";

    _viewEl.innerHTML =
      '<div class="sessions-view">' +
        '<hgroup><h2>Participants</h2></hgroup>' +
        (participants.length > 0
          ? '<table><thead><tr><th>Character</th><th>Extra Contribution</th><th></th></tr></thead>' +
            '<tbody id="participant-tbody">' + participantRows + '</tbody></table>'
          : '<p>No participants yet.</p>'
        ) +
        addRowHtml +
        '<div class="sessions-form__actions">' +
          '<button id="participants-back" class="outline secondary">Back to Sessions</button>' +
        '</div>' +
      '</div>';

    // Wire events
    var backBtn = document.getElementById("participants-back");
    if (backBtn) {
      backBtn.addEventListener("click", function () {
        _mode = "list";
        _renderList();
      });
    }

    var addBtn = document.getElementById("participant-add-btn");
    if (addBtn) {
      addBtn.addEventListener("click", function () {
        var sel = document.getElementById("participant-char-select");
        var charId = sel ? sel.value : "";
        if (!charId) return;
        _doAddParticipant(id, charId);
      });
    }

    // Additional contribution checkboxes
    var checkboxes = _viewEl.querySelectorAll(".participant-addl");
    for (var m = 0; m < checkboxes.length; m++) {
      (function (cb) {
        cb.addEventListener("change", function () {
          var sId = cb.getAttribute("data-session-id");
          var cId = cb.getAttribute("data-char-id");
          _doUpdateParticipant(sId, cId, cb.checked);
        });
      })(checkboxes[m]);
    }

    // Remove buttons
    var removeBtns = _viewEl.querySelectorAll("[data-action='remove-participant']");
    for (var n = 0; n < removeBtns.length; n++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var sId = btn.getAttribute("data-session-id");
          var cId = btn.getAttribute("data-char-id");
          _doRemoveParticipant(sId, cId);
        });
      })(removeBtns[n]);
    }
  }

  function _doAddParticipant(sessionId, charId) {
    api
      .post(SESSIONS_URL + "/" + encodeURIComponent(sessionId) + "/participants", {
        character_id: charId,
        additional_contribution: false,
      })
      .then(function () {
        if (!_mounted) return;
        _openParticipants(sessionId);
      })
      .catch(function () {
        // Error toast shown by api.js
      });
  }

  function _doRemoveParticipant(sessionId, charId) {
    api
      .del(SESSIONS_URL + "/" + encodeURIComponent(sessionId) + "/participants/" + encodeURIComponent(charId))
      .then(function () {
        if (!_mounted) return;
        _openParticipants(sessionId);
      })
      .catch(function () {
        // Error toast shown by api.js
      });
  }

  function _doUpdateParticipant(sessionId, charId, additionalContribution) {
    api
      .patch(SESSIONS_URL + "/" + encodeURIComponent(sessionId) + "/participants/" + encodeURIComponent(charId), {
        additional_contribution: additionalContribution,
      })
      .catch(function () {
        if (_mounted) _openParticipants(sessionId);
      });
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  function _fetchSessions(isInitial) {
    if (!_mounted) return;
    if (isInitial) _renderLoading();

    api
      .get(SESSIONS_URL)
      .then(function (data) {
        if (!_mounted) return;
        _sessions = (data && data.items) ? data.items : [];
        _renderList();
      })
      .catch(function () {
        if (!_mounted) return;
        _renderError();
      });
  }

  // ---------------------------------------------------------------------------
  // Teardown and hashchange
  // ---------------------------------------------------------------------------

  function _teardown() {
    _destroyTable();
    _mounted = false;
    _mode = "list";
    _activeSessionId = null;
    _inflightIds = {};
  }

  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/gm/sessions" && path !== "/gm/sessions/new") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Mount the GM Sessions view.
   * @param {object} [opts]
   * @param {string} [opts.mode] - 'new' to open create form immediately
   */
  return function render(opts) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    if (!window.utils.requireGm(_viewEl)) return;

    _mounted = true;
    _sessions = [];
    _inflightIds = {};

    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);

    // If launched with mode: 'new', open create form immediately
    if (opts && opts.mode === "new") {
      _mode = "create";
      _renderCreateForm();
      return;
    }

    _fetchSessions(true);
  };
})();
