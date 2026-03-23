/* Wizards Engine — Location Create/Edit view
 *
 * Routes:
 *   #/gm/world/locations/new       — create a new location
 *   #/gm/world/locations/{id}/edit — edit an existing location
 *
 * Both modes use this single view. The mode is determined by whether a
 * location ID is passed in via the `id` argument to the exported render
 * function.
 *
 * Create flow
 * -----------
 * 1. Fetch all locations via GET /api/v1/locations (for parent dropdown).
 * 2. Render form with Name, Description, Parent Location fields.
 * 3. On submit: POST /api/v1/locations with {name, description, parent_id}.
 * 4. On success: navigate to #/gm/world/locations/{new_id}.
 *
 * Edit flow
 * ---------
 * 1. Fetch GET /api/v1/locations/{id} to pre-populate fields.
 * 2. Fetch all locations for the parent dropdown (exclude current + children).
 * 3. On submit: PATCH /api/v1/locations/{id} with changed fields only.
 * 4. On success: navigate to #/gm/world/locations/{id}.
 *
 * Archive (edit mode only)
 * ------------------------
 * - DELETE /api/v1/locations/{id} with confirmation dialog.
 * - On success: navigate to #/gm/world (Game Objects browser).
 *
 * Access control
 * --------------
 * GM-only. Non-GM users are redirected to #/ immediately.
 *
 * Registers as: window.views.locationEdit
 * Called by:    router.js route table entries for the two routes above.
 */

window.views = window.views || {};

window.views.locationEdit = (function () {
  // ---------------------------------------------------------------------------
  // Module-level state
  // ---------------------------------------------------------------------------

  /** The #view DOM element — set at render time. */
  var _viewEl = null;

  /** Whether this view is currently mounted. */
  var _mounted = false;

  /** The location ID being edited (null in create mode). */
  var _locationId = null;

  /** Original values fetched from the API — used to compute the changed diff. */
  var _original = null;

  /** All locations fetched for the parent dropdown (array of LocationResponse). */
  var _allLocations = [];

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
  // Child-location discovery
  // ---------------------------------------------------------------------------

  /**
   * Collect the IDs of a location and all its descendants in _allLocations.
   * Used to exclude the current location and its children from the parent
   * dropdown (preventing circular references).
   *
   * @param {string} rootId — the location ID to start from
   * @returns {Set<string>} set of IDs to exclude
   */
  function _collectDescendants(rootId) {
    var excluded = new Set();
    excluded.add(rootId);

    // BFS over _allLocations using parent_id links
    var queue = [rootId];
    while (queue.length > 0) {
      var current = queue.shift();
      for (var i = 0; i < _allLocations.length; i++) {
        var loc = _allLocations[i];
        if (loc.parent_id === current && !excluded.has(loc.id)) {
          excluded.add(loc.id);
          queue.push(loc.id);
        }
      }
    }

    return excluded;
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  /**
   * Render the loading state.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    var title = _locationId ? "Edit Location" : "New Location";
    _viewEl.innerHTML =
      '<div class="le-root">' +
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
    var msg = message || "Could not load location data.";
    var title = _locationId ? "Edit Location" : "New Location";
    _viewEl.innerHTML =
      '<div class="le-root">' +
        '<hgroup>' +
          '<h2>' + _esc(title) + '</h2>' +
        '</hgroup>' +
        '<p class="error-text" role="alert">' + _esc(msg) + '</p>' +
        '<button id="le-retry-btn">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("le-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        _loadData();
      });
    }
  }

  /**
   * Build the <option> list for the parent location dropdown.
   * In edit mode, excludes the current location and all its descendants.
   *
   * @param {string|null} selectedParentId — current parent_id value
   * @returns {string} HTML string of <option> elements
   */
  function _buildParentOptions(selectedParentId) {
    // Determine which IDs to exclude (only relevant in edit mode).
    var excluded = new Set();
    if (_locationId) {
      excluded = _collectDescendants(_locationId);
    }

    var html = '<option value=""' + (!selectedParentId ? ' selected' : '') + '>' +
               'None (top-level)' +
               '</option>';

    for (var i = 0; i < _allLocations.length; i++) {
      var loc = _allLocations[i];
      if (excluded.has(loc.id)) continue;
      var isSelected = selectedParentId && loc.id === selectedParentId;
      html +=
        '<option value="' + _esc(loc.id) + '"' + (isSelected ? ' selected' : '') + '>' +
        _esc(loc.name) +
        '</option>';
    }

    return html;
  }

  /**
   * Render the create/edit form.
   *
   * @param {object} values — {name, description, parent_id} to pre-populate
   * @param {string} [nameError] — inline validation error for the name field
   * @param {string} [submitError] — general submit-level error message
   */
  function _renderForm(values, nameError, submitError) {
    if (!_viewEl) return;

    var isEdit   = !!_locationId;
    var title    = isEdit ? "Edit Location" : "New Location";
    var nameVal  = values.name || "";
    var descVal  = values.description || "";
    var parentId = values.parent_id || null;

    var nameErrorHtml = nameError
      ? '<small class="le-field-error" role="alert">' + _esc(nameError) + '</small>'
      : "";

    var submitErrorHtml = submitError
      ? '<p class="error-text le-submit-error" role="alert">' + _esc(submitError) + '</p>'
      : "";

    var archiveHtml = isEdit
      ? '<button id="le-archive-btn" type="button" class="le-archive-btn outline">' +
          'Archive Location' +
        '</button>'
      : "";

    var cancelHref = isEdit
      ? "#/gm/world/locations/" + _locationId
      : "#/gm/world";

    _viewEl.innerHTML =
      '<div class="le-root">' +
        '<hgroup>' +
          '<h2>' + _esc(title) + '</h2>' +
        '</hgroup>' +

        submitErrorHtml +

        '<form id="le-form" novalidate>' +
          '<label for="le-name">' +
            'Name <span aria-hidden="true">*</span>' +
          '</label>' +
          '<input' +
          '  id="le-name"' +
          '  name="name"' +
          '  type="text"' +
          '  value="' + _esc(nameVal) + '"' +
          '  required' +
          '  autocomplete="off"' +
          '  aria-required="true"' +
          (nameError ? '  aria-invalid="true"' : '') +
          ' />' +
          nameErrorHtml +

          '<label for="le-description">Description</label>' +
          '<textarea' +
          '  id="le-description"' +
          '  name="description"' +
          '  rows="4"' +
          '>' + _esc(descVal) + '</textarea>' +

          '<label for="le-parent">Parent Location</label>' +
          '<select id="le-parent" name="parent_id">' +
            _buildParentOptions(parentId) +
          '</select>' +

          '<div class="le-actions">' +
            '<button id="le-save-btn" type="submit">Save</button>' +
            '<a href="' + cancelHref + '" class="le-cancel-link outline secondary">Cancel</a>' +
          '</div>' +
        '</form>' +

        (isEdit
          ? '<div class="le-danger-zone">' +
              '<hr />' +
              '<h3>Danger Zone</h3>' +
              archiveHtml +
            '</div>'
          : '') +
      '</div>';

    _wireForm();
  }

  /**
   * Render a submitting state: disable the save button and show busy indicator.
   */
  function _renderSubmitting() {
    var saveBtn = document.getElementById("le-save-btn");
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
   * Attach submit and archive handlers to the form after rendering.
   */
  function _wireForm() {
    var form = document.getElementById("le-form");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        _handleSubmit(form);
      });
    }

    var archiveBtn = document.getElementById("le-archive-btn");
    if (archiveBtn) {
      archiveBtn.addEventListener("click", function () {
        _handleArchive();
      });
    }
  }

  /**
   * Handle form submission (create or edit).
   * @param {HTMLFormElement} form
   */
  function _handleSubmit(form) {
    if (!_mounted) return;

    var nameInput   = form.querySelector("#le-name");
    var descInput   = form.querySelector("#le-description");
    var parentInput = form.querySelector("#le-parent");

    var name        = nameInput   ? nameInput.value.trim()   : "";
    var description = descInput   ? descInput.value           : "";
    var parentId    = parentInput ? parentInput.value || null : null;

    // Client-side validation: name is required.
    if (!name) {
      _renderForm(
        {
          name:        nameInput   ? nameInput.value   : "",
          description: description,
          parent_id:   parentId,
        },
        "Name is required."
      );
      return;
    }

    _renderSubmitting();

    if (_locationId) {
      _submitEdit(name, description, parentId);
    } else {
      _submitCreate(name, description, parentId);
    }
  }

  /**
   * Send POST /api/v1/locations to create a new location.
   */
  function _submitCreate(name, description, parentId) {
    var body = { name: name };
    if (description) body.description = description;
    if (parentId)    body.parent_id   = parentId;

    api
      .post("/api/v1/locations", body)
      .then(function (data) {
        if (!_mounted) return;
        window.location.hash = "#/gm/world/locations/" + data.id;
      })
      .catch(function (err) {
        if (!_mounted) return;
        var msg = (err && err.status === 422)
          ? "Invalid values — please check your input."
          : (err && err.message) || "An error occurred.";
        _renderForm(
          { name: name, description: description, parent_id: parentId },
          undefined,
          msg
        );
      });
  }

  /**
   * Send PATCH /api/v1/locations/{id} with changed fields only.
   */
  function _submitEdit(name, description, parentId) {
    if (!_original) return;

    // Build a diff — only send fields that actually changed.
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
      window.location.hash = "#/gm/world/locations/" + _locationId;
      return;
    }

    api
      .patch("/api/v1/locations/" + _locationId, patch)
      .then(function () {
        if (!_mounted) return;
        window.location.hash = "#/gm/world/locations/" + _locationId;
      })
      .catch(function (err) {
        if (!_mounted) return;
        var msg = (err && err.status === 422)
          ? "Invalid values — please check your input."
          : (err && err.message) || "An error occurred.";
        _renderForm(
          { name: name, description: description, parent_id: parentId },
          undefined,
          msg
        );
      });
  }

  /**
   * Handle the archive button click.
   * Shows a native confirmation dialog and DELETEs on confirmation.
   */
  function _handleArchive() {
    if (!_mounted || !_locationId) return;

    var locationName = _original ? _original.name : "this location";
    var confirmed = window.confirm(
      "Are you sure you want to archive " + locationName + "? " +
      "It will be hidden from lists but can still be accessed via direct link."
    );
    if (!confirmed) return;

    var archiveBtn = document.getElementById("le-archive-btn");
    if (archiveBtn) {
      archiveBtn.setAttribute("aria-busy", "true");
      archiveBtn.disabled = true;
      archiveBtn.textContent = "Archiving...";
    }

    api
      .del("/api/v1/locations/" + _locationId)
      .then(function () {
        if (!_mounted) return;
        window.location.hash = "#/gm/world";
      })
      .catch(function (err) {
        if (!_mounted) return;
        // Re-render form with original values so the user can retry.
        _renderForm(
          {
            name:        _original ? _original.name        : "",
            description: _original ? _original.description : "",
            parent_id:   _original ? _original.parent_id   : null,
          },
          undefined,
          (err && err.message) || "Archive failed."
        );
      });
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Fetch all data needed to render the form, then render.
   * In create mode: only fetch all locations (for parent dropdown).
   * In edit mode: fetch the target location + all locations in parallel.
   */
  function _loadData() {
    if (!_mounted) return;

    _renderLoading();

    var locationsPromise = _fetchAllLocations();

    if (!_locationId) {
      // Create mode — just need the locations list.
      locationsPromise
        .then(function () {
          if (!_mounted) return;
          _renderForm({ name: "", description: "", parent_id: null });
        })
        .catch(function (err) {
          if (!_mounted) return;
          _renderError((err && err.message) || undefined);
        });
    } else {
      // Edit mode — fetch both in parallel.
      var locationPromise = api.get("/api/v1/locations/" + _locationId);

      Promise.all([locationPromise, locationsPromise])
        .then(function (results) {
          if (!_mounted) return;
          var locationData = results[0];
          _original = locationData;
          _renderForm({
            name:        locationData.name,
            description: locationData.description,
            parent_id:   locationData.parent_id,
          });
        })
        .catch(function (err) {
          if (!_mounted) return;
          _renderError((err && err.message) || undefined);
        });
    }
  }

  /**
   * Fetch all active locations and store them in _allLocations.
   * Uses a simple loop to page through all results (limit=200 is generous
   * for a small campaign; if more are needed the loop handles it).
   *
   * @returns {Promise<void>}
   */
  function _fetchAllLocations() {
    _allLocations = [];

    function _fetchPage(after) {
      var url = "/api/v1/locations?limit=200";
      if (after) url += "&after=" + encodeURIComponent(after);

      return api.get(url).then(function (data) {
        if (!_mounted) return;
        _allLocations = _allLocations.concat(data.items || []);
        if (data.has_more && data.next_cursor) {
          return _fetchPage(data.next_cursor);
        }
      });
    }

    return _fetchPage(null);
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
   * Build the expected path string for the current route so the hashchange
   * listener knows when to tear down.
   */
  function _currentPath() {
    if (_locationId) {
      return "/gm/world/locations/" + _locationId + "/edit";
    }
    return "/gm/world/locations/new";
  }

  /**
   * One-time hashchange listener — calls _teardown when leaving this route.
   * Removes itself after the first qualifying navigation.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== _currentPath()) {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the Location Create/Edit view.
   * Called by router.js for both the /new and /{id}/edit routes.
   *
   * @param {string|null} [locationId] — ULID of the location to edit, or null
   *   for create mode.
   */
  return function render(locationId) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // GM-only access check.
    var isGm = false;
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      isGm = Alpine.store("app").isGm();
    }
    if (!isGm) {
      window.location.replace("#/");
      return;
    }

    // Reset state for a fresh mount.
    _mounted      = true;
    _locationId   = locationId || null;
    _original     = null;
    _allLocations = [];

    // Fetch data and render.
    _loadData();

    // Teardown on navigation away.
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
