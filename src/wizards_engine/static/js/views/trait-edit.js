/* Wizards Engine — Trait Edit form view (GM only)
 *
 * Route: #/gm/traits/{id}/edit
 *
 * Allows the GM to edit a single trait slot: Name, Description, and Charges.
 * Loads current values by searching all characters for the matching slot ID.
 *
 * Flow
 * ----
 * 1. On mount, verify GM role — redirect to #/ if not GM.
 * 2. Fetch GET /api/v1/characters?limit=100 to find the slot's owner.
 * 3. Fetch GET /api/v1/characters/{owner_id} for full slot data.
 * 4. Pre-populate form fields with current values.
 * 5. Validate on submit — charges must be 0–5.
 * 6. POST /api/v1/gm/actions with action_type "modify_trait".
 * 7. On success: dispatch api:success toast, navigate to world/characters/{owner_id}.
 * 8. Cancel navigates back without saving.
 *
 * Registers as: window.views.traitEdit
 * Called by:    router.js parameterized route "/gm/traits/:id/edit"
 */

window.views = window.views || {};

window.views.traitEdit = (function () {
  // ---------------------------------------------------------------------------
  // Module-level state
  // ---------------------------------------------------------------------------

  /** The #view DOM element — set at render time. */
  var _viewEl = null;

  /** Whether this view is currently mounted. */
  var _mounted = false;

  /** The slot (trait) ID from the URL. */
  var _slotId = null;

  /** The character ID that owns this trait slot. */
  var _characterId = null;

  /** Original trait data fetched from the API. */
  var _original = null;

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
    _viewEl.innerHTML =
      '<div class="te-root">' +
        '<hgroup>' +
          '<h2>Edit Trait</h2>' +
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
    var msg = message || "Could not load trait data.";
    _viewEl.innerHTML =
      '<div class="te-root">' +
        '<hgroup>' +
          '<h2>Edit Trait</h2>' +
        '</hgroup>' +
        '<p class="error-text" role="alert">' + _esc(msg) + '</p>' +
        '<button id="te-retry-btn">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("te-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        _fetchSlot();
      });
    }
  }

  /**
   * Render the edit form pre-populated with the given trait data.
   * @param {object} trait — CharacterTraitResponse
   * @param {string} [chargesError] — inline validation error for the charges field
   */
  function _renderForm(trait, chargesError) {
    if (!_viewEl) return;

    var nameVal      = trait.name        || "";
    var descVal      = trait.description || "";
    var chargesVal   = (trait.charge !== undefined && trait.charge !== null) ? trait.charge : 0;

    var chargesErrorHtml = chargesError
      ? '<small class="te-field-error" role="alert">' + _esc(chargesError) + '</small>'
      : "";

    // Build the cancel href — navigate to the character detail page if we know
    // the owner, otherwise fall back to the world browser.
    var cancelHref = _characterId
      ? "#/world/characters/" + _esc(_characterId)
      : "#/world";

    _viewEl.innerHTML =
      '<div class="te-root">' +
        '<hgroup>' +
          '<h2>Edit Trait</h2>' +
          '<p>' + _esc(nameVal) + '</p>' +
        '</hgroup>' +
        '<form id="te-form" novalidate>' +

          '<label for="te-name">Name</label>' +
          '<input' +
          '  id="te-name"' +
          '  name="name"' +
          '  type="text"' +
          '  value="' + _esc(nameVal) + '"' +
          '  autocomplete="off"' +
          ' />' +

          '<label for="te-description">Description</label>' +
          '<textarea' +
          '  id="te-description"' +
          '  name="description"' +
          '  rows="5"' +
          '>' + _esc(descVal) + '</textarea>' +

          '<label for="te-charges">Charges (0–5)</label>' +
          '<input' +
          '  id="te-charges"' +
          '  name="charges"' +
          '  type="number"' +
          '  min="0"' +
          '  max="5"' +
          '  step="1"' +
          '  value="' + _esc(chargesVal) + '"' +
          (chargesError ? '  aria-invalid="true"' : '') +
          ' />' +
          chargesErrorHtml +

          '<div class="te-actions">' +
            '<button id="te-save-btn" type="submit">Save</button>' +
            '<a href="' + cancelHref + '" class="te-cancel-link outline secondary">Cancel</a>' +
          '</div>' +
        '</form>' +
      '</div>';

    _wireForm();
  }

  /**
   * Render a submitting state: disable the save button and show busy indicator.
   */
  function _renderSubmitting() {
    var saveBtn = document.getElementById("te-save-btn");
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
    var form = document.getElementById("te-form");
    if (!form) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      _handleSubmit(form);
    });
  }

  /**
   * Handle form submission.
   * Validates input and dispatches modify_trait GM action.
   * @param {HTMLFormElement} form
   */
  function _handleSubmit(form) {
    if (!_mounted || !_slotId || !_original) return;

    var nameInput    = form.querySelector("#te-name");
    var descInput    = form.querySelector("#te-description");
    var chargesInput = form.querySelector("#te-charges");

    var name        = nameInput    ? nameInput.value.trim()  : "";
    var description = descInput    ? descInput.value          : "";
    var chargesRaw  = chargesInput ? chargesInput.value       : "0";
    var charges     = parseInt(chargesRaw, 10);

    // Client-side validation: charges must be 0–5.
    if (isNaN(charges) || charges < 0 || charges > 5) {
      _renderForm(
        { name: name, description: description, charge: chargesRaw },
        "Charges must be a number between 0 and 5."
      );
      return;
    }

    // Build the changes object — only include what actually changed.
    var changes = {};
    if (name !== (_original.name || "")) {
      changes.name = name || null;
    }
    var origDesc = _original.description || "";
    if (description !== origDesc) {
      changes.description = description || null;
    }
    var origCharge = (_original.charge !== undefined && _original.charge !== null) ? _original.charge : 0;
    if (charges !== origCharge) {
      changes.charge = { op: "set", value: charges };
    }

    // Nothing changed — navigate back without calling the API.
    if (Object.keys(changes).length === 0) {
      _navigateBack();
      return;
    }

    _renderSubmitting();

    api
      .post("/api/v1/gm/actions", {
        action_type: "modify_trait",
        trait_id:    _slotId,
        changes:     changes,
      })
      .then(function () {
        if (!_mounted) return;
        document.dispatchEvent(new CustomEvent("api:success", {
          detail:  { message: "Trait updated." },
          bubbles: true,
        }));
        _navigateBack();
      })
      .catch(function (err) {
        if (!_mounted) return;
        var errMsg = (err && err.status === 422) ? "Invalid values — please check your input." : undefined;
        _renderForm(
          { name: name, description: description, charge: charges },
          errMsg
        );
      });
  }

  /**
   * Navigate back to the character detail page (or world browser as fallback).
   */
  function _navigateBack() {
    if (_characterId) {
      window.location.hash = "#/world/characters/" + _characterId;
    } else {
      window.location.hash = "#/world";
    }
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Find the owning character and load the trait slot data.
   * Strategy: fetch the character list, search each active character's traits
   * for a slot with ID matching _slotId.
   */
  function _fetchSlot() {
    if (!_mounted || !_slotId) return;

    _renderLoading();

    // Fetch all characters (limit=100 covers any realistic campaign size).
    api
      .get("/api/v1/characters?limit=100")
      .then(function (data) {
        if (!_mounted) return;
        var items = (data && data.items) || [];
        // We only have summary-level data here; we need the character IDs so
        // we can then fetch each full detail record to find the slot.
        // Search through character IDs — fetch detail for each until we find
        // the slot.  In practice the list is very small (4-6 PCs + a few NPCs).
        return _searchCharactersForSlot(items, 0);
      })
      .catch(function (err) {
        if (!_mounted) return;
        _renderError((err && err.message) || undefined);
      });
  }

  /**
   * Recursively search characters by index until the slot is found.
   * @param {Array} characters — list of character summary objects
   * @param {number} index — current search index
   * @returns {Promise}
   */
  function _searchCharactersForSlot(characters, index) {
    if (!_mounted) return Promise.resolve();
    if (index >= characters.length) {
      _renderError("Trait not found. It may have been retired or deleted.");
      return Promise.resolve();
    }

    var char = characters[index];
    return api
      .get("/api/v1/characters/" + char.id)
      .then(function (detail) {
        if (!_mounted) return;
        // Search active traits for matching slot ID.
        var traits = (detail && detail.traits && detail.traits.active) || [];
        for (var i = 0; i < traits.length; i++) {
          if (traits[i].id === _slotId) {
            _characterId = detail.id;
            _original    = traits[i];
            _renderForm(traits[i]);
            return;
          }
        }
        // Not in this character — try the next one.
        return _searchCharactersForSlot(characters, index + 1);
      })
      .catch(function () {
        if (!_mounted) return;
        // Skip characters we can't fetch and continue searching.
        return _searchCharactersForSlot(characters, index + 1);
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
    _mounted     = false;
    _viewEl      = null;
    _slotId      = null;
    _characterId = null;
    _original    = null;
  }

  /**
   * One-time hashchange listener — calls _teardown when leaving this route.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (!path.match(/^\/gm\/traits\/[^/]+\/edit$/)) {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the Trait Edit view.
   * Called by router.js for the "/gm/traits/:id/edit" route.
   * @param {string} slotId — the trait slot ULID from the URL
   */
  return function render(slotId) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // GM-only: redirect non-GM users.
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      var store = Alpine.store("app");
      if (!store.isGm()) {
        window.location.replace("#/");
        return;
      }
    }

    if (!slotId) {
      _viewEl.innerHTML =
        '<div class="te-root">' +
          '<p class="error-text" role="alert">No trait ID specified.</p>' +
        '</div>';
      return;
    }

    // Reset state for a fresh mount.
    _mounted     = true;
    _slotId      = slotId;
    _characterId = null;
    _original    = null;

    // Fetch and render.
    _fetchSlot();

    // Teardown on navigation away.
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
