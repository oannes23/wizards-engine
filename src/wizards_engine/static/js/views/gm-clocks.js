/* Wizards Engine — GM Clock Management view
 *
 * Route:  #/gm/clocks
 * Access: GM only
 *
 * Displays all clocks grouped by association type (character/group/location/standalone).
 * Supports create, inline progress adjustment (+1/-1), and soft-delete.
 *
 * Features:
 *   - Fetches GET /api/v1/clocks on mount (cursor-paginated, "Load more")
 *   - Resolves entity names by fetching /characters/summary, /groups, /locations once
 *   - Groups clocks: "Character Clocks" | "Group Clocks" | "Location Clocks" | "Standalone"
 *   - Clock cards: name, association link, ClockProgress component, completed badge
 *   - Tap clock → expanded detail: full progress display, notes, inline +1/-1 buttons
 *   - Create form: name (required), segments (default 5), association type + target picker
 *   - Delete: confirmation dialog with soft-delete warning
 *
 * Registers as:  window.views.gmClocks
 * Called by:     router.js route entry for "/gm/clocks"
 */

window.views = window.views || {};

window.views.gmClocks = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var CLOCKS_URL = "/api/v1/clocks";
  var PAGE_LIMIT = 50;

  var GROUP_ORDER = ["character", "group", "location", null];
  var GROUP_LABELS = {
    "character": "Character Clocks",
    "group":     "Group Clocks",
    "location":  "Location Clocks",
    null:        "Standalone Clocks",
  };

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** Loaded clock objects. */
  var _clocks = [];

  /** Cursor for next page, or null when exhausted. */
  var _nextCursor = null;

  /** Whether a page fetch is in flight. */
  var _loading = false;

  /** The #view element. */
  var _viewEl = null;

  /** Whether we are the currently mounted view. */
  var _mounted = false;

  /** ID of the currently expanded clock card, or null. */
  var _expandedId = null;

  /** Clock pending deletion confirmation, or null. */
  var _deletingClock = null;

  /** Whether the create form is visible. */
  var _showCreateForm = false;

  /**
   * Entity name maps, built once on mount.
   * Keys are entity IDs; values are display names.
   */
  var _characterNames = {};
  var _groupNames = {};
  var _locationNames = {};

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /**
   * HTML-escape a value.
   * @param {*} str
   * @returns {string}
   */
  function _esc(str) {
    return window.utils.esc(str);
  }

  /**
   * Dispatch a success toast.
   * @param {string} message
   */
  function _showSuccess(message) {
    document.dispatchEvent(
      new CustomEvent("api:success", {
        detail: { message: message },
        bubbles: true,
      })
    );
  }

  /**
   * Resolve an entity display name given its type and ID.
   * Returns the name if found, or the raw ID as a fallback.
   * @param {string|null} assocType
   * @param {string|null} assocId
   * @returns {string}
   */
  function _resolveName(assocType, assocId) {
    if (!assocType || !assocId) return "";
    if (assocType === "character") return _characterNames[assocId] || assocId;
    if (assocType === "group")     return _groupNames[assocId]     || assocId;
    if (assocType === "location")  return _locationNames[assocId]  || assocId;
    return assocId;
  }

  /**
   * Group clocks by association type.
   * @returns {object} mapping group key → array of clocks
   */
  function _groupClocks() {
    var groups = {
      "character": [],
      "group":     [],
      "location":  [],
      null:        [],
    };
    for (var i = 0; i < _clocks.length; i++) {
      var c = _clocks[i];
      var key = c.associated_type || null;
      if (key !== null && key !== "character" && key !== "group" && key !== "location") {
        key = null;
      }
      groups[key].push(c);
    }
    return groups;
  }

  /**
   * Find a clock by ID.
   * @param {string} id
   * @returns {object|null}
   */
  function _findById(id) {
    for (var i = 0; i < _clocks.length; i++) {
      if (_clocks[i].id === id) return _clocks[i];
    }
    return null;
  }

  /**
   * Update a clock in the in-memory list.
   * @param {object} updated
   */
  function _updateInList(updated) {
    for (var i = 0; i < _clocks.length; i++) {
      if (_clocks[i].id === updated.id) {
        _clocks[i] = updated;
        return;
      }
    }
  }

  /**
   * Remove a clock from the in-memory list.
   * @param {string} id
   */
  function _removeFromList(id) {
    _clocks = _clocks.filter(function (c) { return c.id !== id; });
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  /**
   * Full re-render of the view.
   */
  function _render() {
    if (!_viewEl || !_mounted) return;

    var groups = _groupClocks();
    var totalCount = _clocks.length;

    var html =
      '<div class="gm-clocks">' +
        '<hgroup>' +
          '<h2>Clock Management</h2>' +
          '<p>' + totalCount + ' clock' + (totalCount === 1 ? '' : 's') + ' total</p>' +
        '</hgroup>' +

        // Action bar
        '<div class="gm-clocks__actions">' +
          '<button id="gm-clocks-create-btn"' +
                  ' aria-expanded="' + (_showCreateForm ? 'true' : 'false') + '">' +
            (_showCreateForm ? 'Cancel' : '+ New Clock') +
          '</button>' +
        '</div>' +

        // Create form
        (_showCreateForm ? _renderCreateForm() : '');

    // Clock groups
    var hasAnyClocks = false;
    for (var g = 0; g < GROUP_ORDER.length; g++) {
      var groupKey = GROUP_ORDER[g];
      var groupClocks = groups[groupKey];
      if (!groupClocks || groupClocks.length === 0) continue;
      hasAnyClocks = true;
      html += _renderGroup(groupKey, groupClocks);
    }

    if (!hasAnyClocks && totalCount === 0) {
      html +=
        '<p class="gm-clocks__empty" role="status">' +
          'No clocks yet. Create the first one above.' +
        '</p>';
    }

    // Load more
    if (_nextCursor) {
      html +=
        '<div class="gm-clocks__load-more">' +
          '<button id="gm-clocks-load-more"' +
                  (_loading ? ' aria-busy="true" disabled' : '') + '>' +
            (_loading ? 'Loading...' : 'Load more') +
          '</button>' +
        '</div>';
    }

    // Delete confirmation dialog
    if (_deletingClock) {
      html += _renderDeleteDialog(_deletingClock);
    }

    html += '</div>'; // end .gm-clocks

    _viewEl.innerHTML = html;
    _attachEventListeners();
  }

  /**
   * Render a group section.
   * @param {string|null} groupKey
   * @param {Array} clocks
   * @returns {string} HTML
   */
  function _renderGroup(groupKey, clocks) {
    var label = GROUP_LABELS[groupKey] || "Other Clocks";
    var html =
      '<section class="gm-clocks__group">' +
        '<h3 class="gm-clocks__group-heading">' + _esc(label) + '</h3>' +
        '<div class="gm-clocks__list" role="list">';

    for (var i = 0; i < clocks.length; i++) {
      html += _renderClockCard(clocks[i]);
    }

    html += '</div></section>';
    return html;
  }

  /**
   * Render a single clock card (collapsed or expanded).
   * @param {object} clock
   * @returns {string} HTML
   */
  function _renderClockCard(clock) {
    var isExpanded = _expandedId === clock.id;
    var assocName = _resolveName(clock.associated_type, clock.associated_id);
    var assocLink = "";
    if (assocName) {
      var assocHash = _assocHash(clock.associated_type, clock.associated_id);
      assocLink =
        '<a class="gm-clocks__assoc-link" href="' + _esc(assocHash) + '"' +
           ' aria-label="View ' + _esc(clock.associated_type) + ': ' + _esc(assocName) + '">' +
          _esc(assocName) +
        '</a>';
    }

    var progressHtml = window.components.clockProgress.render({
      current: clock.progress || 0,
      total: clock.segments || 5,
      mode: isExpanded ? "detail" : "compact",
    });

    var completedBadge = clock.is_completed
      ? '<span class="gm-clocks__completed-badge">Completed</span>'
      : "";

    var expandedContent = "";
    if (isExpanded) {
      expandedContent =
        '<div class="gm-clocks__detail">' +
          (clock.notes
            ? '<p class="gm-clocks__notes"><em>' + _esc(clock.notes) + '</em></p>'
            : '') +
          '<div class="gm-clocks__progress-controls">' +
            '<button class="gm-clocks__progress-btn secondary outline"' +
                    ' data-progress-id="' + _esc(clock.id) + '"' +
                    ' data-progress-delta="-1"' +
                    ' aria-label="Decrease progress"' +
                    (clock.progress <= 0 ? ' disabled' : '') + '>' +
              '&#x2212; 1' +
            '</button>' +
            '<button class="gm-clocks__progress-btn"' +
                    ' data-progress-id="' + _esc(clock.id) + '"' +
                    ' data-progress-delta="1"' +
                    ' aria-label="Increase progress"' +
                    (clock.is_completed ? ' disabled' : '') + '>' +
              '+ 1' +
            '</button>' +
          '</div>' +
          '<div class="gm-clocks__detail-actions">' +
            '<button class="gm-clocks__delete-btn contrast outline"' +
                    ' data-delete-id="' + _esc(clock.id) + '"' +
                    ' aria-label="Delete ' + _esc(clock.name) + '">' +
              'Delete' +
            '</button>' +
          '</div>' +
        '</div>';
    }

    return (
      '<article class="gm-clocks__card' + (isExpanded ? ' gm-clocks__card--expanded' : '') + '"' +
               ' role="listitem"' +
               ' data-clock-id="' + _esc(clock.id) + '">' +
        '<header class="gm-clocks__card-header"' +
                ' role="button"' +
                ' tabindex="0"' +
                ' aria-expanded="' + (isExpanded ? 'true' : 'false') + '"' +
                ' data-toggle-id="' + _esc(clock.id) + '">' +
          '<div class="gm-clocks__card-title">' +
            '<strong class="gm-clocks__card-name">' + _esc(clock.name) + '</strong>' +
            completedBadge +
          '</div>' +
          (assocLink
            ? '<div class="gm-clocks__card-assoc">' + assocLink + '</div>'
            : '') +
          '<div class="gm-clocks__card-progress">' +
            progressHtml +
          '</div>' +
        '</header>' +
        expandedContent +
      '</article>'
    );
  }

  /**
   * Build a navigation hash for a given association.
   * @param {string|null} type
   * @param {string|null} id
   * @returns {string}
   */
  function _assocHash(type, id) {
    if (!type || !id) return "#/gm/world";
    var segments = {
      character: "characters",
      group: "groups",
      location: "locations",
    };
    var segment = segments[type];
    if (!segment) return "#/gm/world";
    return "#/gm/world/" + segment + "/" + encodeURIComponent(id);
  }

  /**
   * Render the create form.
   * @returns {string} HTML
   */
  function _renderCreateForm() {
    // Build association target picker options — starts empty; populated by JS after render
    return (
      '<form id="gm-clocks-create-form" class="gm-clocks__create-form" novalidate>' +
        '<fieldset>' +
          '<legend>New Clock</legend>' +
          '<label>' +
            'Name <span aria-hidden="true">*</span>' +
            '<input type="text" id="clk-create-name" name="name"' +
                   ' required maxlength="100" autocomplete="off"' +
                   ' placeholder="Clock name" />' +
          '</label>' +
          '<label>' +
            'Segments' +
            '<input type="number" id="clk-create-segments" name="segments"' +
                   ' value="5" min="1" max="24" inputmode="numeric" />' +
          '</label>' +
          '<label>' +
            'Association Type' +
            '<select id="clk-create-assoc-type" name="associated_type">' +
              '<option value="">None (standalone)</option>' +
              '<option value="character">Character</option>' +
              '<option value="group">Group</option>' +
              '<option value="location">Location</option>' +
            '</select>' +
          '</label>' +
          '<div id="clk-assoc-target-wrapper" hidden>' +
            '<label>' +
              'Association Target' +
              '<select id="clk-create-assoc-id" name="associated_id">' +
                '<option value="">Select...</option>' +
              '</select>' +
            '</label>' +
          '</div>' +
          '<label>' +
            'Notes' +
            '<textarea id="clk-create-notes" name="notes"' +
                      ' maxlength="500" rows="2"' +
                      ' placeholder="Optional context or narrative notes"></textarea>' +
          '</label>' +
          '<div class="gm-clocks__form-actions">' +
            '<button type="submit" id="clk-create-submit">Create Clock</button>' +
          '</div>' +
        '</fieldset>' +
      '</form>'
    );
  }

  /**
   * Render the delete confirmation dialog.
   * @param {object} clock
   * @returns {string} HTML
   */
  function _renderDeleteDialog(clock) {
    return (
      '<dialog id="gm-clocks-delete-dialog" open aria-modal="true"' +
              ' role="alertdialog"' +
              ' aria-label="Confirm deletion: ' + _esc(clock.name) + '">' +
        '<article>' +
          '<header><h3>Delete Clock?</h3></header>' +
          '<p>Delete <strong>' + _esc(clock.name) + '</strong>?</p>' +
          '<p class="gm-clocks__delete-warning">' +
            'The clock will be hidden. This action cannot be undone.' +
          '</p>' +
          '<div class="gm-clocks__form-actions">' +
            '<button id="clk-delete-confirm" class="contrast"' +
                    ' data-delete-id="' + _esc(clock.id) + '">' +
              'Delete' +
            '</button>' +
            '<button id="clk-delete-cancel" class="secondary">Cancel</button>' +
          '</div>' +
        '</article>' +
      '</dialog>'
    );
  }

  /**
   * Render a loading placeholder.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-clocks">' +
        '<hgroup><h2>Clock Management</h2></hgroup>' +
        '<p aria-busy="true">Loading clocks...</p>' +
      '</div>';
  }

  /**
   * Render an error state with retry button.
   */
  function _renderError() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-clocks">' +
        '<hgroup><h2>Clock Management</h2></hgroup>' +
        '<p class="error-text" role="alert">Failed to load clocks.</p>' +
        '<button id="gm-clocks-retry">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("gm-clocks-retry");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () { _fetchPage(true); });
    }
  }

  // ---------------------------------------------------------------------------
  // Event wiring
  // ---------------------------------------------------------------------------

  /**
   * Attach all DOM event listeners after a render pass.
   */
  function _attachEventListeners() {
    // Toggle create form
    var createBtn = document.getElementById("gm-clocks-create-btn");
    if (createBtn) {
      createBtn.addEventListener("click", function () {
        _showCreateForm = !_showCreateForm;
        _render();
        if (_showCreateForm) {
          var nameInput = document.getElementById("clk-create-name");
          if (nameInput) nameInput.focus();
        }
      });
    }

    // Create form: association type picker drives the target list
    var assocTypeSelect = document.getElementById("clk-create-assoc-type");
    if (assocTypeSelect) {
      assocTypeSelect.addEventListener("change", function () {
        _updateAssocTargetPicker(assocTypeSelect.value);
      });
    }

    // Create form submit
    var createForm = document.getElementById("gm-clocks-create-form");
    if (createForm) {
      createForm.addEventListener("submit", function (evt) {
        evt.preventDefault();
        _handleCreate(createForm);
      });
    }

    // Card toggle: expand/collapse on header click or keyboard
    var toggleHeaders = _viewEl.querySelectorAll("[data-toggle-id]");
    for (var i = 0; i < toggleHeaders.length; i++) {
      (function (header) {
        function _activate() {
          var id = header.getAttribute("data-toggle-id");
          _expandedId = (_expandedId === id) ? null : id;
          _render();
        }
        header.addEventListener("click", _activate);
        header.addEventListener("keydown", function (evt) {
          if (evt.key === "Enter" || evt.key === " ") {
            evt.preventDefault();
            _activate();
          }
        });
      })(toggleHeaders[i]);
    }

    // Progress +1/-1 buttons
    var progressBtns = _viewEl.querySelectorAll("[data-progress-id]");
    for (var j = 0; j < progressBtns.length; j++) {
      (function (btn) {
        btn.addEventListener("click", function (evt) {
          evt.stopPropagation(); // prevent toggle
          var id = btn.getAttribute("data-progress-id");
          var delta = parseInt(btn.getAttribute("data-progress-delta"), 10);
          if (!isNaN(delta)) {
            _handleProgressChange(id, delta);
          }
        });
      })(progressBtns[j]);
    }

    // Delete buttons (on expanded cards)
    var deleteBtns = _viewEl.querySelectorAll(".gm-clocks__delete-btn[data-delete-id]");
    for (var k = 0; k < deleteBtns.length; k++) {
      (function (btn) {
        btn.addEventListener("click", function (evt) {
          evt.stopPropagation();
          var id = btn.getAttribute("data-delete-id");
          var clock = _findById(id);
          if (clock) {
            _deletingClock = clock;
            _render();
          }
        });
      })(deleteBtns[k]);
    }

    // Delete dialog: confirm
    var deleteConfirm = document.getElementById("clk-delete-confirm");
    if (deleteConfirm) {
      deleteConfirm.addEventListener("click", function () {
        var id = deleteConfirm.getAttribute("data-delete-id");
        if (id) _handleDelete(id);
      });
    }

    // Delete dialog: cancel
    var deleteCancel = document.getElementById("clk-delete-cancel");
    if (deleteCancel) {
      deleteCancel.addEventListener("click", function () {
        _deletingClock = null;
        _render();
      });
    }

    // Suppress click propagation on association links so they don't toggle the card
    var assocLinks = _viewEl.querySelectorAll(".gm-clocks__assoc-link");
    for (var m = 0; m < assocLinks.length; m++) {
      assocLinks[m].addEventListener("click", function (evt) {
        evt.stopPropagation();
      });
    }

    // Load more
    var loadMoreBtn = document.getElementById("gm-clocks-load-more");
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", function () {
        _fetchPage(false);
      });
    }
  }

  /**
   * Populate the association target <select> based on the chosen type.
   * Reads from the in-memory name maps populated on mount.
   * @param {string} type
   */
  function _updateAssocTargetPicker(type) {
    var wrapper = document.getElementById("clk-assoc-target-wrapper");
    var select = document.getElementById("clk-create-assoc-id");
    if (!wrapper || !select) return;

    if (!type) {
      wrapper.hidden = true;
      select.innerHTML = '<option value="">Select...</option>';
      return;
    }

    wrapper.hidden = false;
    var nameMap = {};
    if (type === "character") nameMap = _characterNames;
    else if (type === "group") nameMap = _groupNames;
    else if (type === "location") nameMap = _locationNames;

    var options = '<option value="">Select...</option>';
    var ids = Object.keys(nameMap);
    ids.sort(function (a, b) {
      var na = nameMap[a] || "";
      var nb = nameMap[b] || "";
      return na.localeCompare(nb);
    });
    for (var i = 0; i < ids.length; i++) {
      options +=
        '<option value="' + _esc(ids[i]) + '">' + _esc(nameMap[ids[i]]) + '</option>';
    }
    select.innerHTML = options;
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Fetch one page of clocks.
   * @param {boolean} isInitial
   */
  function _fetchPage(isInitial) {
    if (!_mounted || _loading) return;

    _loading = true;

    if (isInitial) {
      _clocks = [];
      _nextCursor = null;
      _renderLoading();
    }

    var url = CLOCKS_URL + "?limit=" + PAGE_LIMIT;
    if (_nextCursor) {
      url += "&after=" + encodeURIComponent(_nextCursor);
    }

    api
      .get(url)
      .then(function (data) {
        if (!_mounted) return;
        var items = (data && data.items) ? data.items : [];
        _clocks = _clocks.concat(items);
        _nextCursor = (data && data.has_more && data.next_cursor) ? data.next_cursor : null;
        _loading = false;
        _render();
      })
      .catch(function () {
        if (!_mounted) return;
        _loading = false;
        if (isInitial) {
          _renderError();
        } else {
          _render();
        }
      });
  }

  /**
   * Fetch character, group, and location name maps for association resolution.
   * All three requests are made in parallel; failures are silently ignored
   * (cards fall back to showing the raw ID).
   * @returns {Promise}
   */
  function _fetchEntityNames() {
    var charReq = api
      .get("/api/v1/characters/summary", { silent: true })
      .then(function (data) {
        var items = (data && data.items) ? data.items : [];
        var map = {};
        for (var i = 0; i < items.length; i++) {
          map[items[i].id] = items[i].name;
        }
        _characterNames = map;
      })
      .catch(function () { _characterNames = {}; });

    var groupReq = api
      .get("/api/v1/groups?limit=100", { silent: true })
      .then(function (data) {
        var items = (data && data.items) ? data.items : [];
        var map = {};
        for (var i = 0; i < items.length; i++) {
          map[items[i].id] = items[i].name;
        }
        _groupNames = map;
      })
      .catch(function () { _groupNames = {}; });

    var locReq = api
      .get("/api/v1/locations?limit=100", { silent: true })
      .then(function (data) {
        var items = (data && data.items) ? data.items : [];
        var map = {};
        for (var i = 0; i < items.length; i++) {
          map[items[i].id] = items[i].name;
        }
        _locationNames = map;
      })
      .catch(function () { _locationNames = {}; });

    return Promise.all([charReq, groupReq, locReq]);
  }

  // ---------------------------------------------------------------------------
  // Action handlers
  // ---------------------------------------------------------------------------

  /**
   * Handle the create form submission.
   * @param {HTMLFormElement} form
   */
  function _handleCreate(form) {
    var name = (form.elements["name"] ? form.elements["name"].value : "").trim();
    var segmentsRaw = form.elements["segments"] ? form.elements["segments"].value : "5";
    var segments = parseInt(segmentsRaw, 10);
    var assocType = form.elements["associated_type"] ? form.elements["associated_type"].value : "";
    var assocId = form.elements["associated_id"] ? form.elements["associated_id"].value : "";
    var notes = (form.elements["notes"] ? form.elements["notes"].value : "").trim();

    if (!name || isNaN(segments) || segments < 1) return;

    var body = {
      name: name,
      segments: segments,
    };
    if (assocType) {
      body.associated_type = assocType;
      body.associated_id = assocId || null;
    }
    if (notes) {
      body.notes = notes;
    }

    var submitBtn = document.getElementById("clk-create-submit");
    if (submitBtn) submitBtn.disabled = true;

    api
      .post(CLOCKS_URL, body)
      .then(function (created) {
        if (!_mounted) return;
        _clocks.unshift(created);
        _showCreateForm = false;
        _render();
        _showSuccess('Clock "' + created.name + '" created.');
      })
      .catch(function () {
        if (!_mounted) return;
        if (submitBtn) submitBtn.disabled = false;
      });
  }

  /**
   * Handle a progress +1/-1 button click.
   * Patches via a GM direct action (PATCH on the clock's progress field).
   * Uses api.patch() with { progress: newValue }.
   * @param {string} id
   * @param {number} delta — +1 or -1
   */
  function _handleProgressChange(id, delta) {
    var clock = _findById(id);
    if (!clock) return;

    var newProgress = (clock.progress || 0) + delta;
    if (newProgress < 0) newProgress = 0;
    if (newProgress > clock.segments) newProgress = clock.segments;
    if (newProgress === clock.progress) return;

    // Optimistically update
    var prev = clock.progress;
    clock.progress = newProgress;
    clock.is_completed = (newProgress >= clock.segments);
    _render();

    api
      .post("/api/v1/gm/actions", {
        action_type: "modify_clock",
        target_id: id,
        changes: { progress: { op: "set", value: newProgress } },
        narrative: null,
      })
      .then(function () {
        if (!_mounted) return;
        // Refresh the clock from the server to get authoritative state
        api.get(CLOCKS_URL + "/" + encodeURIComponent(id)).then(function (updated) {
          if (!_mounted) return;
          _updateInList(updated);
          _render();
        });
      })
      .catch(function () {
        if (!_mounted) return;
        // Roll back
        clock.progress = prev;
        clock.is_completed = (prev >= clock.segments);
        _render();
      });
  }

  /**
   * Handle soft-delete confirmation.
   * @param {string} id
   */
  function _handleDelete(id) {
    var confirmBtn = document.getElementById("clk-delete-confirm");
    if (confirmBtn) confirmBtn.disabled = true;

    var clock = _findById(id);
    var name = clock ? clock.name : "clock";

    api
      .del(CLOCKS_URL + "/" + encodeURIComponent(id))
      .then(function () {
        if (!_mounted) return;
        _removeFromList(id);
        if (_expandedId === id) _expandedId = null;
        _deletingClock = null;
        _render();
        _showSuccess('"' + name + '" deleted.');
      })
      .catch(function () {
        if (!_mounted) return;
        if (confirmBtn) confirmBtn.disabled = false;
      });
  }

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  /**
   * Reset all state when navigating away.
   */
  function _teardown() {
    _mounted = false;
    _clocks = [];
    _nextCursor = null;
    _loading = false;
    _expandedId = null;
    _deletingClock = null;
    _showCreateForm = false;
    _characterNames = {};
    _groupNames = {};
    _locationNames = {};
  }

  /**
   * One-time hashchange listener — tears down when leaving this route.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/gm/clocks") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Mount the Clock Management view.
   * Called by router.js for the "/gm/clocks" route.
   */
  return function render() {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // Guard: GM only
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      if (!Alpine.store("app").isGm()) {
        _viewEl.innerHTML =
          '<div class="gm-clocks">' +
            '<p class="error-text" role="alert">Access denied — GM only.</p>' +
          '</div>';
        return;
      }
    }

    // Reset state for a fresh mount
    _mounted = true;
    _clocks = [];
    _nextCursor = null;
    _loading = false;
    _expandedId = null;
    _deletingClock = null;
    _showCreateForm = false;
    _characterNames = {};
    _groupNames = {};
    _locationNames = {};

    // Fetch entity names and clocks in parallel, then render
    _renderLoading();
    _fetchEntityNames().then(function () {
      if (!_mounted) return;
      _fetchPage(true);
    });

    // Teardown when navigating away
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
