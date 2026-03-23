/* Wizards Engine — Group Edit view
 *
 * Routes:
 *   #/gm/world/groups/new        — Create a new group
 *   #/gm/world/groups/{id}/edit  — Edit an existing group
 *
 * This single view handles both create and edit modes, determined by the
 * route URL. The router passes the group ID when editing, or calls with
 * no argument when creating.
 *
 * Create mode:
 *   Fields: Name (required), Description (textarea), Tier (select 1-5, default 1)
 *   Uses POST /api/v1/groups
 *   On success: navigates to #/gm/world/groups/{new_id}
 *
 * Edit mode:
 *   Fields: Name (required), Description (textarea)
 *   Tier is shown as read-only — tier changes require GM actions, not PATCH.
 *   Uses PATCH /api/v1/groups/{id}
 *   On success: navigates to #/gm/world/groups/{id}
 *   Archive button: DELETE /api/v1/groups/{id} with confirmation dialog
 *   On archive: navigates to #/gm/world
 *
 * Access control:
 *   GM only. Non-GM users are redirected to #/.
 *
 * Registers as: window.views.groupEdit
 * Called by:    router.js parameterized routes
 */

window.views = window.views || {};

window.views.groupEdit = (function () {
  // ---------------------------------------------------------------------------
  // Module-level state
  // ---------------------------------------------------------------------------

  /** The #view DOM element — set at render time. */
  var _viewEl = null;

  /** Whether this view is currently mounted. */
  var _mounted = false;

  /** "create" | "edit" */
  var _mode = null;

  /** The group ID being edited (null in create mode). */
  var _groupId = null;

  /** Original values fetched from the API (edit mode only). */
  var _original = null;

  /** Whether the archive confirmation dialog is visible. */
  var _showArchiveDialog = false;

  // ---------------------------------------------------------------------------
  // HTML helpers
  // ---------------------------------------------------------------------------

  /**
   * HTML-escape for text content. Delegates to window.utils.esc.
   * @param {*} str
   * @returns {string}
   */
  function _esc(str) {
    return window.utils.esc(str);
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  /**
   * Render the loading state.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    var title = _mode === "edit" ? "Edit Group" : "New Group";
    _viewEl.innerHTML =
      '<div class="ge-root">' +
        '<hgroup>' +
          '<h2>' + _esc(title) + '</h2>' +
          '<p aria-busy="true">Loading...</p>' +
        '</hgroup>' +
      '</div>';
  }

  /**
   * Render an error state with a retry button.
   * @param {string} [message]
   */
  function _renderError(message) {
    if (!_viewEl) return;
    var title = _mode === "edit" ? "Edit Group" : "New Group";
    var msg = message || "Could not load group data.";
    _viewEl.innerHTML =
      '<div class="ge-root">' +
        '<hgroup>' +
          '<h2>' + _esc(title) + '</h2>' +
        '</hgroup>' +
        '<p class="error-text" role="alert">' + _esc(msg) + '</p>' +
        '<button id="ge-retry-btn">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("ge-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        _fetchGroup();
      });
    }
  }

  /**
   * Render the form pre-populated with given values.
   *
   * @param {object} values — { name, description, tier }
   * @param {string} [nameError] — inline validation error for the name field
   * @param {string} [submitError] — general submit-level error message
   */
  function _renderForm(values, nameError, submitError) {
    if (!_viewEl) return;

    var title = _mode === "edit" ? "Edit Group" : "New Group";
    var nameVal = values.name || "";
    var descVal = values.description || "";
    var tierVal = (values.tier !== null && values.tier !== undefined) ? values.tier : 1;

    var nameErrorHtml = nameError
      ? '<small class="ge-field-error" role="alert">' + _esc(nameError) + '</small>'
      : "";

    var submitErrorHtml = submitError
      ? '<p class="ge-submit-error error-text" role="alert">' + _esc(submitError) + '</p>'
      : "";

    // Tier field: editable in create mode, read-only in edit mode
    var tierFieldHtml;
    if (_mode === "create") {
      var tierOptions = "";
      for (var i = 1; i <= 5; i++) {
        tierOptions +=
          '<option value="' + i + '"' + (tierVal === i ? ' selected' : '') + '>' +
            i +
          '</option>';
      }
      tierFieldHtml =
        '<label for="ge-tier">Tier</label>' +
        '<select id="ge-tier" name="tier">' +
          tierOptions +
        '</select>';
    } else {
      // Edit mode: tier is read-only (changes require GM actions)
      tierFieldHtml =
        '<label>Tier</label>' +
        '<p class="ge-tier-readonly">' + _esc(tierVal) + ' <small>(use GM Actions to change tier)</small></p>';
    }

    // Archive button (edit mode only)
    var archiveHtml = (_mode === "edit")
      ? '<button id="ge-archive-btn" type="button" class="ge-archive-btn contrast outline">' +
          'Archive Group' +
        '</button>'
      : "";

    // Cancel destination
    var cancelHref = (_mode === "edit")
      ? "#/gm/world/groups/" + encodeURIComponent(_groupId)
      : "#/gm/world";

    _viewEl.innerHTML =
      '<div class="ge-root">' +
        '<hgroup>' +
          '<h2>' + _esc(title) + '</h2>' +
        '</hgroup>' +
        submitErrorHtml +
        '<form id="ge-form" novalidate>' +
          '<label for="ge-name">' +
            'Name <span aria-hidden="true">*</span>' +
          '</label>' +
          '<input' +
          '  id="ge-name"' +
          '  name="name"' +
          '  type="text"' +
          '  value="' + _esc(nameVal) + '"' +
          '  required' +
          '  autocomplete="off"' +
          '  aria-required="true"' +
          (nameError ? '  aria-invalid="true"' : '') +
          ' />' +
          nameErrorHtml +

          '<label for="ge-description">Description</label>' +
          '<textarea' +
          '  id="ge-description"' +
          '  name="description"' +
          '  rows="4"' +
          '>' + _esc(descVal) + '</textarea>' +

          tierFieldHtml +

          '<div class="ge-actions">' +
            '<button id="ge-save-btn" type="submit">Save</button>' +
            '<a href="' + _esc(cancelHref) + '" class="ge-cancel-link outline secondary">Cancel</a>' +
          '</div>' +
        '</form>' +

        archiveHtml +

        (_showArchiveDialog ? _renderArchiveDialog(values.name) : "") +
      '</div>';

    _wireForm();
    _wireArchive(values.name);
  }

  /**
   * Build the archive confirmation dialog HTML.
   * @param {string} name — group name for the confirmation message
   * @returns {string} HTML
   */
  function _renderArchiveDialog(name) {
    return (
      '<dialog id="ge-archive-dialog" open aria-modal="true"' +
              ' role="alertdialog"' +
              ' aria-label="Confirm archive">' +
        '<article>' +
          '<header><h3>Archive Group?</h3></header>' +
          '<p>Are you sure you want to archive <strong>' + _esc(name || "this group") + '</strong>?</p>' +
          '<p class="ge-archive-warning">' +
            'The group will be hidden from lists. This action can be undone by the GM.' +
          '</p>' +
          '<div class="ge-dialog-actions">' +
            '<button id="ge-archive-confirm" class="contrast">Archive</button>' +
            '<button id="ge-archive-cancel" class="secondary outline">Cancel</button>' +
          '</div>' +
        '</article>' +
      '</dialog>'
    );
  }

  /**
   * Render the save button in a submitting state.
   */
  function _renderSubmitting() {
    var saveBtn = document.getElementById("ge-save-btn");
    if (saveBtn) {
      saveBtn.setAttribute("aria-busy", "true");
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";
    }
  }

  // ---------------------------------------------------------------------------
  // Form wiring
  // ---------------------------------------------------------------------------

  /**
   * Attach submit handler to the form after rendering.
   */
  function _wireForm() {
    var form = document.getElementById("ge-form");
    if (!form) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      _handleSubmit(form);
    });
  }

  /**
   * Wire archive button and dialog controls after rendering.
   * @param {string} groupName — current group name for confirmation text
   */
  function _wireArchive(groupName) {
    var archiveBtn = document.getElementById("ge-archive-btn");
    if (archiveBtn) {
      archiveBtn.addEventListener("click", function () {
        _showArchiveDialog = true;
        _renderCurrentState(groupName);
      });
    }

    var confirmBtn = document.getElementById("ge-archive-confirm");
    if (confirmBtn) {
      confirmBtn.addEventListener("click", function () {
        _handleArchive();
      });
    }

    var cancelBtn = document.getElementById("ge-archive-cancel");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        _showArchiveDialog = false;
        _renderCurrentState(groupName);
      });
    }
  }

  /**
   * Re-render with the current form input values preserved (used by archive
   * dialog toggle without losing user's edits).
   * @param {string} groupName
   */
  function _renderCurrentState(groupName) {
    var nameInput = document.getElementById("ge-name");
    var descInput = document.getElementById("ge-description");
    var tierInput = document.getElementById("ge-tier");

    var currentValues = {
      name: nameInput ? nameInput.value : (groupName || ""),
      description: descInput ? descInput.value : "",
      tier: tierInput ? parseInt(tierInput.value, 10) : ((_original && _original.tier) || 1),
    };

    _renderForm(currentValues, null, null);
  }

  // ---------------------------------------------------------------------------
  // Submit handler
  // ---------------------------------------------------------------------------

  /**
   * Handle form submission for both create and edit modes.
   * @param {HTMLFormElement} form
   */
  function _handleSubmit(form) {
    if (!_mounted) return;

    var nameInput = form.querySelector("#ge-name");
    var descInput = form.querySelector("#ge-description");
    var tierInput = form.querySelector("#ge-tier");

    var name = nameInput ? nameInput.value.trim() : "";
    var description = descInput ? descInput.value : "";
    var tier = tierInput ? parseInt(tierInput.value, 10) : 1;

    // Client-side validation: name is required.
    if (!name) {
      _renderForm(
        {
          name: nameInput ? nameInput.value : "",
          description: description,
          tier: _original ? _original.tier : tier,
        },
        "Name is required."
      );
      return;
    }

    _renderSubmitting();

    if (_mode === "create") {
      _doCreate(name, description, isNaN(tier) ? 1 : tier);
    } else {
      _doEdit(name, description);
    }
  }

  /**
   * POST to create a new group.
   * @param {string} name
   * @param {string} description
   * @param {number} tier
   */
  function _doCreate(name, description, tier) {
    var body = {
      name: name,
      tier: tier,
    };
    if (description) {
      body.description = description;
    }

    api
      .post("/api/v1/groups", body)
      .then(function (created) {
        if (!_mounted) return;
        window.location.hash = "#/gm/world/groups/" + encodeURIComponent(created.id);
      })
      .catch(function (err) {
        if (!_mounted) return;
        var errMsg = (err && err.status === 422)
          ? "Invalid values — please check your input."
          : undefined;
        _renderForm(
          { name: name, description: description, tier: tier },
          null,
          errMsg
        );
      });
  }

  /**
   * PATCH to update an existing group.
   * Only sends fields that have changed.
   * @param {string} name
   * @param {string} description
   */
  function _doEdit(name, description) {
    if (!_groupId || !_original) return;

    // Build a diff: only send changed fields.
    var patch = {};
    if (name !== (_original.name || "")) {
      patch.name = name;
    }
    var origDesc = _original.description || "";
    if (description !== origDesc) {
      patch.description = description || null;
    }

    // Nothing changed — navigate back without calling the API.
    if (Object.keys(patch).length === 0) {
      window.location.hash = "#/gm/world/groups/" + encodeURIComponent(_groupId);
      return;
    }

    api
      .patch("/api/v1/groups/" + encodeURIComponent(_groupId), patch)
      .then(function () {
        if (!_mounted) return;
        window.location.hash = "#/gm/world/groups/" + encodeURIComponent(_groupId);
      })
      .catch(function (err) {
        if (!_mounted) return;
        var errMsg = (err && err.status === 422)
          ? "Invalid values — please check your input."
          : undefined;
        _renderForm(
          { name: name, description: description, tier: _original.tier },
          null,
          errMsg
        );
      });
  }

  /**
   * Handle soft-delete (archive) confirmation.
   */
  function _handleArchive() {
    if (!_mounted || !_groupId) return;

    var confirmBtn = document.getElementById("ge-archive-confirm");
    if (confirmBtn) {
      confirmBtn.setAttribute("aria-busy", "true");
      confirmBtn.disabled = true;
      confirmBtn.textContent = "Archiving...";
    }

    api
      .del("/api/v1/groups/" + encodeURIComponent(_groupId))
      .then(function () {
        if (!_mounted) return;
        window.location.hash = "#/gm/world";
      })
      .catch(function () {
        if (!_mounted) return;
        _showArchiveDialog = false;
        _renderForm(
          {
            name: (_original && _original.name) || "",
            description: (_original && _original.description) || "",
            tier: (_original && _original.tier) || 1,
          },
          null,
          "Archive failed — please try again."
        );
      });
  }

  // ---------------------------------------------------------------------------
  // Data fetching (edit mode only)
  // ---------------------------------------------------------------------------

  /**
   * Fetch the group from the API and render the form (edit mode).
   */
  function _fetchGroup() {
    if (!_mounted || !_groupId) return;

    _renderLoading();

    api
      .get("/api/v1/groups/" + encodeURIComponent(_groupId))
      .then(function (data) {
        if (!_mounted) return;
        _original = data;
        _showArchiveDialog = false;
        _renderForm(data);
      })
      .catch(function (err) {
        if (!_mounted) return;
        _renderError((err && err.message) || undefined);
      });
  }

  // ---------------------------------------------------------------------------
  // Teardown
  // ---------------------------------------------------------------------------

  /**
   * Called when navigating away. Clears the mounted flag to prevent stale
   * promise callbacks from writing to the (now unmounted) DOM.
   */
  function _teardown() {
    _mounted = false;
  }

  /**
   * One-time hashchange listener — calls _teardown when leaving this route.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    var isOurRoute = (
      path === "/gm/world/groups/new" ||
      (path.indexOf("/gm/world/groups/") === 0 && path.indexOf("/edit") !== -1)
    );
    if (!isOurRoute) {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the Group Edit/Create view.
   *
   * Called by router.js:
   *   - For create mode: views.groupEdit() — no arguments
   *   - For edit mode:   views.groupEdit(id) — group ULID
   *
   * @param {string} [id] — group ULID (omitted in create mode)
   */
  return function render(id) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // GM-only access check.
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      if (!Alpine.store("app").isGm()) {
        window.location.replace("#/");
        return;
      }
    }

    // Determine mode from the presence of an id argument.
    _mode = id ? "edit" : "create";
    _groupId = id || null;
    _original = null;
    _showArchiveDialog = false;
    _mounted = true;

    // Teardown on navigation away.
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);

    if (_mode === "edit") {
      // Fetch existing group data and render the pre-populated form.
      _fetchGroup();
    } else {
      // Create mode: render an empty form immediately.
      _renderForm({ name: "", description: "", tier: 1 });
    }
  };
})();
