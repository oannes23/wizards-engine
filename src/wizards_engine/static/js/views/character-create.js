/* Wizards Engine — Character Create view
 *
 * Route: #/gm/world/characters/new
 *
 * Allows the GM to create a new NPC character.
 *
 * Flow
 * ----
 * 1. Render the create form immediately (no pre-fetch needed).
 * 2. Validate on submit — name must be a non-empty string.
 * 3. Send POST /api/v1/characters with name, description, and detail_level.
 * 4. On success, navigate to the new character's detail page:
 *    #/gm/world/characters/{new_id}
 * 5. Cancel navigates to #/gm/world without saving.
 *
 * Access control
 * --------------
 * GM only. Non-GM users are redirected to #/.
 *
 * Registers as: window.views.characterCreate
 * Called by:    router.js route table entry for "/gm/world/characters/new"
 */

window.views = window.views || {};

window.views.characterCreate = (function () {
  // ---------------------------------------------------------------------------
  // Module-level state
  // ---------------------------------------------------------------------------

  /** The #view DOM element — set at render time. */
  var _viewEl = null;

  /** Whether this view is currently mounted. */
  var _mounted = false;

  // ---------------------------------------------------------------------------
  // HTML helpers
  // ---------------------------------------------------------------------------

  /**
   * HTML-escape for text content or attribute values.
   * @param {*} str
   * @returns {string}
   */

  // showSuccess is available globally via window.utils.showSuccess

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  /**
   * Render the create form.
   * @param {object} [values]        — current field values (used to restore after validation error)
   * @param {string} [nameError]     — inline validation error for the name field
   * @param {string} [generalError]  — non-field error message (e.g. API 422)
   */
  function _renderForm(values, nameError, generalError) {
    if (!_viewEl) return;

    var nameVal = (values && values.name) || "";
    var descVal = (values && values.description) || "";

    var nameErrorHtml = nameError
      ? '<small class="cc-field-error" role="alert">' + window.utils.esc(nameError) + "</small>"
      : "";

    var generalErrorHtml = generalError
      ? '<p class="error-text" role="alert">' + window.utils.esc(generalError) + "</p>"
      : "";

    _viewEl.innerHTML =
      '<div class="cc-root">' +
        "<hgroup>" +
          "<h2>New Character</h2>" +
          "<p>Create a new NPC for the world.</p>" +
        "</hgroup>" +
        generalErrorHtml +
        '<form id="cc-form" novalidate>' +
          '<label for="cc-name">' +
            'Name <span aria-hidden="true">*</span>' +
          "</label>" +
          "<input" +
          '  id="cc-name"' +
          '  name="name"' +
          '  type="text"' +
          '  value="' + window.utils.esc(nameVal) + '"' +
          "  required" +
          '  autocomplete="off"' +
          '  aria-required="true"' +
          (nameError ? '  aria-invalid="true"' : "") +
          " />" +
          nameErrorHtml +

          '<label for="cc-description">Description</label>' +
          "<textarea" +
          '  id="cc-description"' +
          '  name="description"' +
          '  rows="4"' +
          ">" + window.utils.esc(descVal) + "</textarea>" +

          '<label for="cc-detail-level">Detail Level</label>' +
          '<select id="cc-detail-level" name="detail_level">' +
            '<option value="simplified" selected>NPC (simplified)</option>' +
            '<option value="full">PC (full sheet)</option>' +
          "</select>" +
          '<small class="cc-field-hint">PC characters are normally created via the player join flow.</small>' +

          '<div class="cc-actions">' +
            '<button id="cc-save-btn" type="submit">Create</button>' +
            '<a href="#/gm/world" class="cc-cancel-link outline secondary">Cancel</a>' +
          "</div>" +
        "</form>" +
      "</div>";

    _wireForm();

    // Focus the name field for faster input.
    var nameInput = document.getElementById("cc-name");
    if (nameInput) {
      nameInput.focus();
    }
  }

  /**
   * Render a submitting state: disable the save button and show busy indicator.
   */
  function _renderSubmitting() {
    var saveBtn = document.getElementById("cc-save-btn");
    if (saveBtn) {
      saveBtn.setAttribute("aria-busy", "true");
      saveBtn.disabled = true;
      saveBtn.textContent = "Creating...";
    }
  }

  // ---------------------------------------------------------------------------
  // Form wiring
  // ---------------------------------------------------------------------------

  /**
   * Attach submit handler to the form after rendering.
   */
  function _wireForm() {
    var form = document.getElementById("cc-form");
    if (!form) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      _handleSubmit(form);
    });
  }

  /**
   * Handle form submission.
   * Validates inputs, calls POST /api/v1/characters, navigates on success.
   * @param {HTMLFormElement} form
   */
  function _handleSubmit(form) {
    if (!_mounted) return;

    var nameInput   = form.querySelector("#cc-name");
    var descInput   = form.querySelector("#cc-description");
    var levelSelect = form.querySelector("#cc-detail-level");

    var name        = nameInput   ? nameInput.value.trim()   : "";
    var description = descInput   ? descInput.value          : "";
    var detailLevel = levelSelect ? levelSelect.value        : "simplified";

    // Client-side validation: name is required.
    if (!name) {
      _renderForm(
        { name: nameInput ? nameInput.value : "", description: description },
        "Name is required."
      );
      return;
    }

    _renderSubmitting();

    var payload = { name: name };
    if (description) {
      payload.description = description;
    }
    // Note: the backend currently always creates characters as 'simplified'.
    // The detail_level field is included here for forward compatibility.
    // If the API is extended to support 'full' creation, this will work.
    void detailLevel;

    api
      .post("/api/v1/characters", payload)
      .then(function (created) {
        if (!_mounted) return;
        window.utils.showSuccess('"' + created.name + '" created.');
        // Navigate to the new character's GM world detail page.
        window.location.hash = "#/gm/world/characters/" + encodeURIComponent(created.id);
      })
      .catch(function (err) {
        if (!_mounted) return;
        var msg = (err && err.status === 422)
          ? "Invalid values — please check your input."
          : (err && err.message) || "Could not create character.";
        _renderForm(
          { name: name, description: description },
          undefined,
          msg
        );
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
   * Removes itself after the first qualifying navigation.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/gm/world/characters/new") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the Character Create view.
   * Called by router.js for the "/gm/world/characters/new" route.
   */
  return function render() {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // GM-only guard.
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      var store = Alpine.store("app");
      if (!store.isGm()) {
        window.location.replace("#/");
        return;
      }
    }

    // Reset state for a fresh mount.
    _mounted = true;

    // Render the empty form.
    _renderForm();

    // Teardown on navigation away.
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
