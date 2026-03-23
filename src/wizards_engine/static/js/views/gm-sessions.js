/* Wizards Engine — GM Sessions view
 *
 * Route:  #/gm/sessions  and  #/gm/sessions/new
 * Access: GM only
 *
 * Displays a session list grouped by status (active → draft → ended).
 * Supports creating new sessions, starting/ending sessions, editing draft
 * sessions, managing participants, and navigating to session detail/timeline.
 *
 * Registers as:  window.views.gmSessions
 * Called by:     router.js route entries for "/gm/sessions" and "/gm/sessions/new"
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

  /** All loaded sessions, flat. Grouped on render. */
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

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  function _isGm() {
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      return Alpine.store("app").isGm();
    }
    return false;
  }

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

  // ---------------------------------------------------------------------------
  // Status badge helpers
  // ---------------------------------------------------------------------------

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
        '<p class="error-text" role="alert">' + window.utils.esc(msg || "Failed to load sessions.") + '</p>' +
        '<button id="sessions-retry">Retry</button>' +
      '</div>';
    var btn = document.getElementById("sessions-retry");
    if (btn) btn.addEventListener("click", function () { _fetchSessions(true); });
  }

  // ---------------------------------------------------------------------------
  // Session list render
  // ---------------------------------------------------------------------------

  function _renderSessionCard(session) {
    var id       = session.id || "";
    var status   = session.status || "draft";
    var summary  = session.summary || "";
    var date     = _formatDate(session.date);
    var timeNow  = session.time_now != null ? session.time_now : "";
    var isActive = status === "active";
    var isDraft  = status === "draft";
    var isEnded  = status === "ended";

    var summaryHtml = summary
      ? '<p class="session-card__summary">' + window.utils.esc(summary) + '</p>'
      : "";

    var metaHtml = "";
    if (date || timeNow !== "") {
      metaHtml = '<p class="session-card__meta">';
      if (date)        metaHtml += '<span>Date: ' + window.utils.esc(date) + '</span> ';
      if (timeNow !== "") metaHtml += '<span>Time: ' + window.utils.esc(String(timeNow)) + '</span>';
      metaHtml += '</p>';
    }

    var actionsHtml = '<div class="session-card__actions">';
    actionsHtml += '<a href="#/gm/sessions/' + window.utils.esc(id) + '" class="outline secondary">View</a> ';
    actionsHtml += '<a href="#/gm/sessions/' + window.utils.esc(id) + '/timeline" class="outline secondary">Timeline</a> ';

    if (isDraft) {
      actionsHtml += '<button class="outline" data-action="edit-session" data-id="' + window.utils.esc(id) + '">Edit</button> ';
      actionsHtml += '<button class="outline secondary" data-action="manage-participants" data-id="' + window.utils.esc(id) + '">Participants</button> ';
      actionsHtml += '<button data-action="confirm-start" data-id="' + window.utils.esc(id) + '">Start</button> ';
      actionsHtml += '<button class="outline secondary" data-action="confirm-delete" data-id="' + window.utils.esc(id) + '">Delete</button> ';
    }

    if (isActive) {
      actionsHtml += '<button class="outline secondary" data-action="manage-participants" data-id="' + window.utils.esc(id) + '">Participants</button> ';
      actionsHtml += '<button class="outline secondary" data-action="confirm-end" data-id="' + window.utils.esc(id) + '">End Session</button> ';
    }

    actionsHtml += '</div>';

    var inflight = !!_inflightIds[id];
    var inflightAttr = inflight ? ' aria-busy="true"' : "";

    return (
      '<article class="session-card session-card--' + window.utils.esc(status) + '"' + inflightAttr + '>' +
        '<header class="session-card__header">' +
          _statusBadge(status) +
          (summary ? '<strong class="session-card__name">' + window.utils.esc(summary.slice(0, 60)) + '</strong>' : '<em class="session-card__name">Untitled Session</em>') +
        '</header>' +
        metaHtml +
        actionsHtml +
      '</article>'
    );
  }

  function _renderList() {
    if (!_viewEl || !_mounted) return;

    var active  = _sessions.filter(function (s) { return s.status === "active";  });
    var draft   = _sessions.filter(function (s) { return s.status === "draft";   });
    var ended   = _sessions.filter(function (s) { return s.status === "ended";   });

    var html = '<div class="sessions-view">';
    html += '<hgroup><h2>Sessions</h2></hgroup>';
    html += '<div class="sessions-view__toolbar"><button id="sessions-create-btn">+ New Session</button></div>';

    if (_sessions.length === 0) {
      html += '<p class="sessions-view__empty" role="status">No sessions yet. Create one to get started.</p>';
    } else {
      if (active.length > 0) {
        html += '<h3 class="sessions-view__group-heading">Active</h3>';
        for (var i = 0; i < active.length; i++) html += _renderSessionCard(active[i]);
      }
      if (draft.length > 0) {
        html += '<h3 class="sessions-view__group-heading">Draft</h3>';
        for (var j = 0; j < draft.length; j++) html += _renderSessionCard(draft[j]);
      }
      if (ended.length > 0) {
        html += '<h3 class="sessions-view__group-heading">Ended</h3>';
        for (var k = 0; k < ended.length; k++) html += _renderSessionCard(ended[k]);
      }
    }

    html += '</div>';

    _viewEl.innerHTML = html;
    _bindListEvents();
  }

  function _bindListEvents() {
    var createBtn = document.getElementById("sessions-create-btn");
    if (createBtn) {
      createBtn.addEventListener("click", function () {
        _mode = "create";
        _activeSessionId = null;
        _renderCreateForm();
      });
    }

    // Delegate action buttons
    if (_viewEl) {
      _viewEl.addEventListener("click", function (evt) {
        var btn = evt.target.closest("[data-action]");
        if (!btn) return;
        var action = btn.getAttribute("data-action");
        var id     = btn.getAttribute("data-id");
        if (!action || !id) return;

        if (action === "edit-session")        { _openEdit(id); }
        if (action === "confirm-start")       { _openConfirmStart(id); }
        if (action === "confirm-end")         { _openConfirmEnd(id); }
        if (action === "confirm-delete")      { _openConfirmDelete(id); }
        if (action === "manage-participants") { _openParticipants(id); }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Create form
  // ---------------------------------------------------------------------------

  function _renderCreateForm() {
    if (!_viewEl || !_mounted) return;
    _viewEl.innerHTML =
      '<div class="sessions-view">' +
        '<hgroup><h2>New Session</h2></hgroup>' +
        '<form id="session-create-form">' +
          '<label for="sc-summary">Summary<br>' +
            '<input type="text" id="sc-summary" name="summary" placeholder="Brief description of the session" maxlength="200">' +
          '</label>' +
          '<label for="sc-date">Date<br>' +
            '<input type="date" id="sc-date" name="date">' +
          '</label>' +
          '<label for="sc-time-now">Time Now (hours)<br>' +
            '<input type="number" id="sc-time-now" name="time_now" min="0" max="999" step="1" placeholder="e.g. 4" inputmode="numeric">' +
          '</label>' +
          '<label for="sc-notes">Notes<br>' +
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

    var summaryEl  = form.querySelector('[name="summary"]');
    var dateEl     = form.querySelector('[name="date"]');
    var timeNowEl  = form.querySelector('[name="time_now"]');
    var notesEl    = form.querySelector('[name="notes"]');

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
    _renderEditForm(session);
  }

  function _renderEditForm(session) {
    if (!_viewEl || !_mounted) return;

    var dateValue = session.date ? session.date.slice(0, 10) : "";

    _viewEl.innerHTML =
      '<div class="sessions-view">' +
        '<hgroup><h2>Edit Session</h2></hgroup>' +
        '<form id="session-edit-form">' +
          '<label for="se-summary">Summary<br>' +
            '<input type="text" id="se-summary" name="summary" value="' + window.utils.esc(session.summary || "") + '" maxlength="200">' +
          '</label>' +
          '<label for="se-date">Date<br>' +
            '<input type="date" id="se-date" name="date" value="' + window.utils.esc(dateValue) + '">' +
          '</label>' +
          '<label for="se-time-now">Time Now (hours)<br>' +
            '<input type="number" id="se-time-now" name="time_now" min="0" max="999" step="1" inputmode="numeric" value="' + window.utils.esc(session.time_now != null ? String(session.time_now) : "") + '">' +
          '</label>' +
          '<label for="se-notes">Notes<br>' +
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

    var summaryEl  = form.querySelector('[name="summary"]');
    var dateEl     = form.querySelector('[name="date"]');
    var timeNowEl  = form.querySelector('[name="time_now"]');
    var notesEl    = form.querySelector('[name="notes"]');

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
        // Update the local list
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

    var timeNow  = session.time_now != null ? session.time_now : 0;
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

    // Fetch session detail and characters in parallel
    var sessionDetailP = api.get(SESSIONS_URL + "/" + encodeURIComponent(id));
    var charactersP = _characters.length > 0
      ? Promise.resolve({ items: _characters })
      : api.get(CHARACTERS_URL);

    Promise.all([sessionDetailP, charactersP])
      .then(function (results) {
        if (!_mounted) return;
        var detail     = results[0];
        var charData   = results[1];
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
          var sId   = cb.getAttribute("data-session-id");
          var cId   = cb.getAttribute("data-char-id");
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
        // Re-open participants view to refresh
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
        // On failure, re-render to restore the checkbox state
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
   * @param {boolean} [opts.mode] - 'new' to open create form immediately
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

    _fetchSessions(true);

    // If launched with mode: 'new', open create form after fetch
    if (opts && opts.mode === "new") {
      // Show create form immediately (no loading wait needed)
      _mode = "create";
      _renderCreateForm();
    }
  };
})();
