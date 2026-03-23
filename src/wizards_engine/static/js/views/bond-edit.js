/* Wizards Engine — Bond Edit form view (GM only)
 *
 * Route: #/gm/bonds/{id}/edit
 *
 * Allows the GM to edit a single bond slot: Description and Charges.
 * Loads current values by searching all characters for the matching slot ID.
 *
 * Flow
 * ----
 * 1. On mount, verify GM role — redirect to #/ if not GM.
 * 2. Fetch GET /api/v1/characters?limit=100 to find the slot's owner.
 * 3. Fetch GET /api/v1/characters/{owner_id} for full slot data.
 * 4. Pre-populate form fields with current values.
 * 5. Validate on submit — charges must be 0–5.
 * 6. POST /api/v1/gm/actions with action_type "modify_bond".
 * 7. On success: dispatch api:success toast, navigate to world/characters/{owner_id}.
 * 8. Cancel navigates back without saving.
 *
 * Registers as: window.views.bondEdit
 * Called by:    router.js parameterized route "/gm/bonds/:id/edit"
 */

window.views = window.views || {};

window.views.bondEdit = (function () {
  // ---------------------------------------------------------------------------
  // Module-level state
  // ---------------------------------------------------------------------------

  /** The #view DOM element — set at render time. */
  var _viewEl = null;

  /** Whether this view is currently mounted. */
  var _mounted = false;

  /** The slot (bond) ID from the URL. */
  var _slotId = null;

  /** The character ID that owns this bond slot. */
  var _characterId = null;

  /** Original bond data fetched from the API. */
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
      '<div class="be-root">' +
        '<hgroup>' +
          '<h2>Edit Bond</h2>' +
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
    var msg = message || "Could not load bond data.";
    _viewEl.innerHTML =
      '<div class="be-root">' +
        '<hgroup>' +
          '<h2>Edit Bond</h2>' +
        '</hgroup>' +
        '<p class="error-text" role="alert">' + _esc(msg) + '</p>' +
        '<button id="be-retry-btn">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("be-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        _fetchSlot();
      });
    }
  }

  /**
   * Render the edit form pre-populated with the given bond data.
   * @param {object} bond — BondDisplayResponse
   * @param {string} [chargesError] — inline validation error for the charges field
   */
  function _renderForm(bond, chargesError) {
    if (!_viewEl) return;

    var partnerName  = bond.target_name  || "Unknown";
    var descVal      = bond.description  || "";
    var chargesVal   = (bond.charges !== undefined && bond.charges !== null) ? bond.charges : 0;

    var chargesErrorHtml = chargesError
      ? '<small class="be-field-error" role="alert">' + _esc(chargesError) + '</small>'
      : "";

    // Build the cancel href — navigate to the character detail page if we know
    // the owner, otherwise fall back to the world browser.
    var cancelHref = _characterId
      ? "#/world/characters/" + _esc(_characterId)
      : "#/world";

    _viewEl.innerHTML =
      '<div class="be-root">' +
        '<hgroup>' +
          '<h2>Edit Bond</h2>' +
          '<p>Bond with ' + _esc(partnerName) + '</p>' +
        '</hgroup>' +
        '<form id="be-form" novalidate>' +

          '<label for="be-description">Description</label>' +
          '<textarea' +
          '  id="be-description"' +
          '  name="description"' +
          '  rows="5"' +
          '>' + _esc(descVal) + '</textarea>' +

          '<label for="be-charges">Charges (0–5)</label>' +
          '<input' +
          '  id="be-charges"' +
          '  name="charges"' +
          '  type="number"' +
          '  min="0"' +
          '  max="5"' +
          '  step="1"' +
          '  value="' + _esc(chargesVal) + '"' +
          (chargesError ? '  aria-invalid="true"' : '') +
          ' />' +
          chargesErrorHtml +

          '<div class="be-actions">' +
            '<button id="be-save-btn" type="submit">Save</button>' +
            '<a href="' + cancelHref + '" class="be-cancel-link outline secondary">Cancel</a>' +
          '</div>' +
        '</form>' +
      '</div>';

    _wireForm();
  }

  /**
   * Render a submitting state: disable the save button and show busy indicator.
   */
  function _renderSubmitting() {
    var saveBtn = document.getElementById("be-save-btn");
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
    var form = document.getElementById("be-form");
    if (!form) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      _handleSubmit(form);
    });
  }

  /**
   * Handle form submission.
   * Validates input and dispatches modify_bond GM action.
   * @param {HTMLFormElement} form
   */
  function _handleSubmit(form) {
    if (!_mounted || !_slotId || !_original) return;

    var descInput    = form.querySelector("#be-description");
    var chargesInput = form.querySelector("#be-charges");

    var description = descInput    ? descInput.value    : "";
    var chargesRaw  = chargesInput ? chargesInput.value : "0";
    var charges     = parseInt(chargesRaw, 10);

    // Client-side validation: charges must be 0–5.
    if (isNaN(charges) || charges < 0 || charges > 5) {
      _renderForm(
        { target_name: _original.target_name, description: description, charges: chargesRaw },
        "Charges must be a number between 0 and 5."
      );
      return;
    }

    // Build the changes object — only include what actually changed.
    var changes = {};
    var origDesc = _original.description || "";
    if (description !== origDesc) {
      changes.description = description || null;
    }
    var origCharges = (_original.charges !== undefined && _original.charges !== null) ? _original.charges : 0;
    if (charges !== origCharges) {
      changes.charges = { op: "set", value: charges };
    }

    // Nothing changed — navigate back without calling the API.
    if (Object.keys(changes).length === 0) {
      _navigateBack();
      return;
    }

    _renderSubmitting();

    api
      .post("/api/v1/gm/actions", {
        action_type: "modify_bond",
        bond_id:     _slotId,
        changes:     changes,
      })
      .then(function () {
        if (!_mounted) return;
        document.dispatchEvent(new CustomEvent("api:success", {
          detail:  { message: "Bond updated." },
          bubbles: true,
        }));
        _navigateBack();
      })
      .catch(function (err) {
        if (!_mounted) return;
        var errMsg = (err && err.status === 422) ? "Invalid values — please check your input." : undefined;
        _renderForm(
          { target_name: _original.target_name, description: description, charges: charges },
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
   * Find the owning character and load the bond slot data.
   * Strategy: fetch the character list, then search each character's bonds
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
      _renderError("Bond not found. It may have been retired or deleted.");
      return Promise.resolve();
    }

    var char = characters[index];
    return api
      .get("/api/v1/characters/" + char.id)
      .then(function (detail) {
        if (!_mounted) return;
        // Search active bonds for matching slot ID.
        var bonds = (detail && detail.bonds && detail.bonds.active) || [];
        for (var i = 0; i < bonds.length; i++) {
          if (bonds[i].id === _slotId) {
            _characterId = detail.id;
            _original    = bonds[i];
            _renderForm(bonds[i]);
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
    if (!path.match(/^\/gm\/bonds\/[^/]+\/edit$/)) {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the Bond Edit view.
   * Called by router.js for the "/gm/bonds/:id/edit" route.
   * @param {string} slotId — the bond slot ULID from the URL
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
        '<div class="be-root">' +
          '<p class="error-text" role="alert">No bond ID specified.</p>' +
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
