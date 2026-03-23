/* Wizards Engine — Character Edit view
 *
 * Routes
 * ------
 * #/character/edit                     — player (or GM) edits the current character
 * #/gm/world/characters/{id}/edit      — GM edits any character by ID
 *
 * Allows a player (owner) or GM to edit the player-editable fields on a
 * character sheet: name, description, and notes.
 * GM users additionally see an Archive button (soft-delete).
 *
 * Flow
 * ----
 * 1. On mount, fetch GET /api/v1/characters/{id} to populate form fields.
 * 2. Validate on submit — name must be a non-empty string.
 * 3. Send PATCH /api/v1/characters/{id} with only the changed fields.
 * 4. On success, navigate back:
 *    - Player route (#/character/edit) → #/character
 *    - GM world route (#/gm/world/characters/{id}/edit) → #/gm/world/characters/{id}
 * 5. Cancel navigates back without saving (same destination as success).
 * 6. Archive (GM only): confirms, calls DELETE /api/v1/characters/{id},
 *    then navigates to #/gm/world.
 *
 * Access control
 * --------------
 * Only accessible when store.isOwner(characterId) || store.isGm().
 * If neither, redirects to #/character immediately.
 *
 * Registers as: window.views.characterEdit
 * Called by:    router.js route table entry for "/character/edit"
 *               router.js parameterized route for "/gm/world/characters/:id/edit"
 */

window.views = window.views || {};

window.views.characterEdit = (function () {
  // ---------------------------------------------------------------------------
  // Module-level state
  // ---------------------------------------------------------------------------

  /** The #view DOM element — set at render time. */
  var _viewEl = null;

  /** Whether this view is currently mounted. */
  var _mounted = false;

  /** The character ID being edited. */
  var _characterId = null;

  /** Original values fetched from the API — used to compute the changed-only diff. */
  var _original = null;

  /**
   * Context for navigation:
   *   "player" — the /character/edit route; navigates to #/character on save/cancel.
   *   "gm"     — the /gm/world/characters/:id/edit route; navigates to the detail page.
   */
  var _context = "player";

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
   * Return the "back" hash for the current context.
   * Player route → #/character
   * GM route → #/gm/world/characters/{id}
   * @returns {string}
   */
  function _backHash() {
    if (_context === "gm" && _characterId) {
      return "#/gm/world/characters/" + encodeURIComponent(_characterId);
    }
    return "#/character";
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  /**
   * Render the loading state.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="ce-root">' +
        "<hgroup>" +
          "<h2>Edit Character</h2>" +
          '<p aria-busy="true">Loading...</p>' +
        "</hgroup>" +
      "</div>";
  }

  /**
   * Render an error state with a retry button.
   * @param {string} [message]
   */
  function _renderError(message) {
    if (!_viewEl) return;
    var msg = message || "Could not load character data.";
    _viewEl.innerHTML =
      '<div class="ce-root">' +
        "<hgroup>" +
          "<h2>Edit Character</h2>" +
        "</hgroup>" +
        '<p class="error-text" role="alert">' + _esc(msg) + "</p>" +
        '<button id="ce-retry-btn">Retry</button>' +
      "</div>";

    var retryBtn = document.getElementById("ce-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        _fetchCharacter();
      });
    }
  }

  /**
   * Render the edit form pre-populated with the given character data.
   * @param {object} c — CharacterDetailResponse (or CharacterResponse)
   * @param {string} [nameError] — inline validation error for the name field
   */
  function _renderForm(c, nameError) {
    if (!_viewEl) return;

    var nameVal  = c.name        || "";
    var descVal  = c.description || "";
    var notesVal = c.notes       || "";
    var isGm     = _context === "gm";
    var back     = _backHash();

    var nameErrorHtml = nameError
      ? '<small class="ce-field-error" role="alert">' + _esc(nameError) + "</small>"
      : "";

    // Archive button — GM only, styled as destructive.
    var archiveHtml = isGm
      ? '<button id="ce-archive-btn" type="button" class="ce-archive-btn outline contrast">' +
          "Archive" +
        "</button>"
      : "";

    _viewEl.innerHTML =
      '<div class="ce-root">' +
        "<hgroup>" +
          "<h2>Edit Character</h2>" +
        "</hgroup>" +
        '<form id="ce-form" novalidate>' +
          '<label for="ce-name">' +
            'Name <span aria-hidden="true">*</span>' +
          "</label>" +
          "<input" +
          '  id="ce-name"' +
          '  name="name"' +
          '  type="text"' +
          '  value="' + _esc(nameVal) + '"' +
          "  required" +
          '  autocomplete="off"' +
          '  aria-required="true"' +
          (nameError ? '  aria-invalid="true"' : "") +
          " />" +
          nameErrorHtml +

          '<label for="ce-description">Description</label>' +
          "<textarea" +
          '  id="ce-description"' +
          '  name="description"' +
          '  rows="4"' +
          ">" + _esc(descVal) + "</textarea>" +

          '<label for="ce-notes">Notes</label>' +
          "<textarea" +
          '  id="ce-notes"' +
          '  name="notes"' +
          '  rows="4"' +
          ">" + _esc(notesVal) + "</textarea>" +

          '<div class="ce-actions">' +
            '<button id="ce-save-btn" type="submit">Save</button>' +
            '<a href="' + _esc(back) + '" class="ce-cancel-link outline secondary">Cancel</a>' +
            archiveHtml +
          "</div>" +
        "</form>" +
      "</div>";

    _wireForm();
  }

  /**
   * Render a submitting state: disable the save button and show busy indicator.
   */
  function _renderSubmitting() {
    var saveBtn = document.getElementById("ce-save-btn");
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
   * Attach submit handler and archive handler to the form after rendering.
   */
  function _wireForm() {
    var form = document.getElementById("ce-form");
    if (!form) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      _handleSubmit(form);
    });

    var archiveBtn = document.getElementById("ce-archive-btn");
    if (archiveBtn) {
      archiveBtn.addEventListener("click", function () {
        _handleArchive();
      });
    }
  }

  /**
   * Handle form submission.
   * Validates, computes the changed-fields diff, and calls PATCH.
   * @param {HTMLFormElement} form
   */
  function _handleSubmit(form) {
    if (!_mounted || !_characterId || !_original) return;

    var nameInput  = form.querySelector("#ce-name");
    var descInput  = form.querySelector("#ce-description");
    var notesInput = form.querySelector("#ce-notes");

    var name        = nameInput  ? nameInput.value.trim() : "";
    var description = descInput  ? descInput.value        : "";
    var notes       = notesInput ? notesInput.value       : "";

    // Client-side validation: name is required.
    if (!name) {
      _renderForm(
        { name: nameInput ? nameInput.value : "", description: description, notes: notes },
        "Name is required."
      );
      return;
    }

    // Build a diff containing only changed fields.
    var patch = {};
    if (name !== (_original.name || "")) {
      patch.name = name;
    }
    // Compare description — treat null/undefined as empty string for equality.
    var origDesc = _original.description || "";
    if (description !== origDesc) {
      patch.description = description || null;
    }
    // Compare notes — treat null/undefined as empty string for equality.
    var origNotes = _original.notes || "";
    if (notes !== origNotes) {
      patch.notes = notes || null;
    }

    // Nothing changed — navigate back without calling the API.
    if (Object.keys(patch).length === 0) {
      window.location.hash = _backHash();
      return;
    }

    _renderSubmitting();

    api
      .patch("/api/v1/characters/" + _characterId, patch)
      .then(function () {
        if (!_mounted) return;
        window.location.hash = _backHash();
      })
      .catch(function (err) {
        if (!_mounted) return;
        // Re-render the form with the current input values so the user can correct.
        _renderForm(
          { name: name, description: description, notes: notes },
          (err && err.status === 422) ? "Invalid values — please check your input." : undefined
        );
      });
  }

  /**
   * Handle the archive (soft-delete) button click.
   * Shows a native confirm dialog; on confirmation, calls DELETE.
   */
  function _handleArchive() {
    if (!_mounted || !_characterId || !_original) return;

    var name = (_original && _original.name) ? _original.name : "this character";
    var confirmed = window.confirm(
      'Are you sure you want to archive "' + name + '"? ' +
      "This will hide them from the world browser but they can still be viewed directly."
    );
    if (!confirmed) return;

    // Disable the archive button to prevent double-submit.
    var archiveBtn = document.getElementById("ce-archive-btn");
    if (archiveBtn) {
      archiveBtn.disabled = true;
      archiveBtn.textContent = "Archiving...";
    }

    api
      .del("/api/v1/characters/" + _characterId)
      .then(function () {
        if (!_mounted) return;
        // After archive, navigate back to the GM world browser.
        window.location.hash = "#/gm/world";
      })
      .catch(function () {
        if (!_mounted) return;
        // Re-enable the button on failure.
        if (archiveBtn) {
          archiveBtn.disabled = false;
          archiveBtn.textContent = "Archive";
        }
      });
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Fetch the character from the API and render the form.
   */
  function _fetchCharacter() {
    if (!_mounted || !_characterId) return;

    _renderLoading();

    api
      .get("/api/v1/characters/" + _characterId)
      .then(function (data) {
        if (!_mounted) return;
        _original = data;
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
   * Removes itself after the first qualifying navigation away from edit routes.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    // Stay mounted on any character edit route.
    if (path !== "/character/edit" && path.indexOf("/gm/world/characters/") === -1) {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    } else if (path.indexOf("/gm/world/characters/") !== -1 && path.indexOf("/edit") === -1) {
      // Navigated to a detail page — tear down.
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the Character Edit view.
   *
   * Called by router.js for:
   *   - The "/character/edit" route (player/GM editing own character): no arguments.
   *   - The "/gm/world/characters/:id/edit" parameterized route: id argument passed.
   *
   * @param {string} [id] — character ULID for the GM world route; omit for player route.
   */
  return function render(id) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    var store = null;
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      store = Alpine.store("app");
    }

    var characterId = null;
    var canEdit = false;

    if (id) {
      // GM world route: id passed directly from the router.
      _context = "gm";
      characterId = id;
      canEdit = store && store.isGm();
    } else {
      // Player route: resolve from the store.
      _context = "player";
      if (store) {
        characterId = store.character_id;
        canEdit = store.isGm() || store.isOwner(characterId);
      }
    }

    // Redirect if the user has no edit access.
    if (!canEdit) {
      window.location.replace(id ? "#/" : "#/character");
      return;
    }

    if (!characterId) {
      _viewEl.innerHTML =
        '<div class="ce-root">' +
          '<p class="error-text" role="alert">No character linked to this account.</p>' +
        "</div>";
      return;
    }

    // Reset state for a fresh mount.
    _mounted     = true;
    _characterId = characterId;
    _original    = null;

    // Fetch and render.
    _fetchCharacter();

    // Teardown on navigation away.
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
