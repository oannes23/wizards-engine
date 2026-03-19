/* Wizards Engine — Profile view
 *
 * Route: #/profile
 *
 * Shows the current user's profile with:
 *   - Display name (editable inline via PATCH /api/v1/me)
 *   - Role badge (GM or Player)
 *   - Character link (if character_id exists)
 *   - Self-refresh login link button (POST /api/v1/me/refresh-link)
 *   - Starred objects list (GET /api/v1/me/starred) with unstar buttons
 *
 * Registers as: window.views.profile
 * Called by:    router.js route table entry for "/profile"
 */

window.views = window.views || {};

window.views.profile = (function () {
  // ---------------------------------------------------------------------------
  // Module-level state
  // ---------------------------------------------------------------------------

  /** The #view DOM element — set at render time. */
  var _viewEl = null;

  /** Whether this view is currently mounted. */
  var _mounted = false;

  /** Starred objects from GET /api/v1/me/starred */
  var _starred = [];

  /** Whether the name save request is in flight. */
  var _inflightSave = false;

  /** Whether the refresh-link request is in flight. */
  var _inflightRefresh = false;

  /** Set of starred IDs with an in-flight unstar request. */
  var _inflightUnstar = {};

  /** The login_url returned by refresh-link, shown in a confirmation message. */
  var _refreshedUrl = null;

  /** Inline error for the display name field. */
  var _nameError = null;

  /** Error message for the refresh-link section, or null. */
  var _refreshError = null;

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
      '<div class="profile-root">' +
        '<hgroup>' +
          '<h2>Profile</h2>' +
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
    var msg = message || "Could not load profile data.";
    _viewEl.innerHTML =
      '<div class="profile-root">' +
        '<hgroup><h2>Profile</h2></hgroup>' +
        '<p class="error-text" role="alert">' + _esc(msg) + '</p>' +
        '<button id="profile-retry-btn">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("profile-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        _fetchStarred();
      });
    }
  }

  /**
   * Build the profile header section (name, role, character link).
   * @param {object} user
   * @returns {string} HTML
   */
  function _renderProfileSection(user) {
    var displayName = user.display_name || "";
    var role = user.role || "player";
    var characterId = user.character_id || null;

    var roleBadgeClass = role === "gm"
      ? "profile__role-badge profile__role-badge--gm"
      : "profile__role-badge profile__role-badge--player";
    var roleLabel = role === "gm" ? "GM" : "Player";

    var nameErrorHtml = _nameError
      ? '<small class="profile__field-error" role="alert">' + _esc(_nameError) + '</small>'
      : "";

    var saveDisabled = _inflightSave ? " disabled" : "";
    var saveLabel = _inflightSave ? "Saving..." : "Save";

    var charHtml = "";
    if (characterId) {
      var charHash = role === "gm" ? "#/gm/character" : "#/character";
      charHtml =
        '<p class="profile__char-link-row">' +
          'Character: <a href="' + _esc(charHash) + '">View character sheet</a>' +
        '</p>';
    }

    return (
      '<section class="profile__section">' +
        '<hgroup>' +
          '<h2>Profile</h2>' +
          '<p><span class="' + _esc(roleBadgeClass) + '">' + _esc(roleLabel) + '</span></p>' +
        '</hgroup>' +
        charHtml +
        '<form id="profile-name-form" novalidate>' +
          '<label for="profile-name">Display name</label>' +
          '<input' +
          '  id="profile-name"' +
          '  name="display_name"' +
          '  type="text"' +
          '  value="' + _esc(displayName) + '"' +
          '  required' +
          '  autocomplete="off"' +
          '  aria-required="true"' +
          (_nameError ? '  aria-invalid="true"' : '') +
          ' />' +
          nameErrorHtml +
          '<button id="profile-save-btn" type="submit"' + saveDisabled + '>' +
            saveLabel +
          '</button>' +
        '</form>' +
      '</section>'
    );
  }

  /**
   * Build the refresh-link section.
   * @returns {string} HTML
   */
  function _renderRefreshSection() {
    var refreshDisabled = _inflightRefresh ? " disabled" : "";
    var refreshLabel = _inflightRefresh ? "Generating..." : "Generate new login link";

    var confirmHtml = "";
    if (_refreshedUrl) {
      confirmHtml =
        '<div class="profile__refresh-confirm" role="status">' +
          '<p class="profile__refresh-success">New login link generated.</p>' +
          '<p class="profile__refresh-url">' +
            '<code>' + _esc(_refreshedUrl) + '</code>' +
          '</p>' +
          '<p class="profile__refresh-hint">Save this link. Your old link no longer works.</p>' +
        '</div>';
    } else if (_refreshError) {
      confirmHtml =
        '<p class="profile__refresh-error error-text" role="alert">' +
          _esc(_refreshError) +
        '</p>';
    }

    return (
      '<section class="profile__section">' +
        '<h3>Login link</h3>' +
        '<p class="profile__refresh-warning">' +
          '<strong>Warning:</strong> Generating a new link will invalidate your current login link. ' +
          'Anyone using the old link will no longer be able to log in.' +
        '</p>' +
        '<button id="profile-refresh-btn" class="secondary"' + refreshDisabled + '>' +
          refreshLabel +
        '</button>' +
        confirmHtml +
      '</section>'
    );
  }

  /**
   * Build a single starred item row.
   * @param {object} item
   * @returns {string} HTML
   */
  function _renderStarredItem(item) {
    var isInflight = _inflightUnstar[item.type + "/" + item.id];
    var unstarDisabled = isInflight ? " disabled" : "";
    var unstarLabel = isInflight ? "Removing..." : "Unstar";

    var typeBadgeClass = "profile__type-badge profile__type-badge--" + _esc(item.type || "unknown");

    return (
      '<li class="profile__starred-item" ' +
          'data-object-type="' + _esc(item.type) + '" ' +
          'data-object-id="' + _esc(item.id) + '">' +
        '<span class="' + typeBadgeClass + '">' + _esc(item.type || "") + '</span>' +
        '<span class="profile__starred-name">' + _esc(item.name || "") + '</span>' +
        '<button class="profile__unstar-btn secondary outline"' + unstarDisabled + ' ' +
            'data-object-type="' + _esc(item.type) + '" ' +
            'data-object-id="' + _esc(item.id) + '" ' +
            'aria-label="Unstar ' + _esc(item.name || "") + '">' +
          unstarLabel +
        '</button>' +
      '</li>'
    );
  }

  /**
   * Build the starred objects section.
   * @returns {string} HTML
   */
  function _renderStarredSection() {
    var listHtml = "";
    if (_starred.length === 0) {
      listHtml = '<p class="profile__starred-empty">No starred objects yet.</p>';
    } else {
      var items = "";
      for (var i = 0; i < _starred.length; i++) {
        items += _renderStarredItem(_starred[i]);
      }
      listHtml = '<ul class="profile__starred-list">' + items + '</ul>';
    }

    return (
      '<section class="profile__section">' +
        '<h3>Starred objects</h3>' +
        listHtml +
      '</section>'
    );
  }

  /**
   * Re-render the full profile view into _viewEl.
   */
  function _render() {
    if (!_viewEl || !_mounted) return;

    var user = null;
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      user = Alpine.store("app").user;
    }

    if (!user) {
      _viewEl.innerHTML =
        '<div class="profile-root">' +
          '<p class="error-text" role="alert">Not logged in.</p>' +
        '</div>';
      return;
    }

    _viewEl.innerHTML =
      '<div class="profile-root">' +
        _renderProfileSection(user) +
        _renderRefreshSection() +
        _renderStarredSection() +
      '</div>';

    _attachListeners();
  }

  // ---------------------------------------------------------------------------
  // Event listener attachment
  // ---------------------------------------------------------------------------

  /**
   * Attach all event listeners after rendering.
   */
  function _attachListeners() {
    if (!_viewEl || !_mounted) return;

    // Display name save form
    var nameForm = document.getElementById("profile-name-form");
    if (nameForm) {
      nameForm.addEventListener("submit", function (e) {
        e.preventDefault();
        _handleSaveName(nameForm);
      });
    }

    // Refresh login link button
    var refreshBtn = document.getElementById("profile-refresh-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", _handleRefreshLink);
    }

    // Unstar buttons
    var unstarBtns = _viewEl.querySelectorAll(".profile__unstar-btn");
    for (var i = 0; i < unstarBtns.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var type = btn.getAttribute("data-object-type");
          var id = btn.getAttribute("data-object-id");
          if (type && id) {
            _handleUnstar(type, id);
          }
        });
      })(unstarBtns[i]);
    }
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  /**
   * Handle display name save form submission.
   * @param {HTMLFormElement} form
   */
  function _handleSaveName(form) {
    if (!_mounted || _inflightSave) return;

    var nameInput = form.querySelector("#profile-name");
    var name = nameInput ? nameInput.value.trim() : "";

    if (!name) {
      _nameError = "Display name is required.";
      _render();
      return;
    }

    _nameError = null;
    _inflightSave = true;
    _render();

    api
      .patch("/api/v1/me", { display_name: name })
      .then(function (data) {
        _inflightSave = false;
        if (!_mounted) return;
        // Update the store with the fresh user data
        if (typeof Alpine !== "undefined" && Alpine.store("app") && data) {
          Alpine.store("app").setUser(data);
        }
        _render();
      })
      .catch(function (err) {
        _inflightSave = false;
        if (!_mounted) return;
        _nameError = (err && err.status === 422)
          ? "Invalid display name."
          : "Could not save — please try again.";
        _render();
      });
  }

  /**
   * Handle refresh login link button click.
   */
  function _handleRefreshLink() {
    if (!_mounted || _inflightRefresh) return;

    var confirmed = window.confirm(
      "Generate a new login link?\n\n" +
      "Your current login link will stop working immediately. " +
      "You will need to save the new link to log in again."
    );
    if (!confirmed) return;

    _inflightRefresh = true;
    _refreshedUrl = null;
    _refreshError = null;
    _render();

    api
      .post("/api/v1/me/refresh-link", {})
      .then(function (data) {
        _inflightRefresh = false;
        if (!_mounted) return;
        if (data && data.login_url) {
          _refreshedUrl = window.location.origin + data.login_url;
        }
        _render();
      })
      .catch(function () {
        _inflightRefresh = false;
        if (!_mounted) return;
        _refreshError = "Failed to generate new link. Please try again.";
        _render();
      });
  }

  /**
   * Handle unstar button click.
   * @param {string} type — object_type (e.g. "character")
   * @param {string} id   — object_id
   */
  function _handleUnstar(type, id) {
    var key = type + "/" + id;
    if (_inflightUnstar[key]) return;

    _inflightUnstar[key] = true;
    _render();

    api
      .del("/api/v1/me/starred/" + encodeURIComponent(type) + "/" + encodeURIComponent(id))
      .then(function () {
        delete _inflightUnstar[key];
        if (!_mounted) return;
        // Remove from local list
        _starred = _starred.filter(function (item) {
          return !(item.type === type && item.id === id);
        });
        _render();
      })
      .catch(function () {
        delete _inflightUnstar[key];
        if (!_mounted) return;
        _render();
      });
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Fetch starred objects from the API.
   */
  function _fetchStarred() {
    if (!_mounted) return;

    api
      .get("/api/v1/me/starred")
      .then(function (data) {
        if (!_mounted) return;
        _starred = Array.isArray(data) ? data : [];
        _render();
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
    _starred = [];
    _inflightSave = false;
    _inflightRefresh = false;
    _inflightUnstar = {};
    _refreshedUrl = null;
    _refreshError = null;
    _nameError = null;
  }

  /**
   * One-time hashchange listener — calls _teardown when leaving this route.
   * Removes itself after the first qualifying navigation.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/profile") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the Profile view.
   * Called by router.js for the "/profile" route.
   */
  return function render() {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // Reset state for a fresh mount.
    _mounted = true;
    _starred = [];
    _inflightSave = false;
    _inflightRefresh = false;
    _inflightUnstar = {};
    _refreshedUrl = null;
    _refreshError = null;
    _nameError = null;

    // Render the shell immediately from the store (no API call needed for
    // the profile header — user data is already in the Alpine store).
    _renderLoading();

    // Fetch starred objects, then re-render the full view.
    _fetchStarred();

    // Teardown on navigation away.
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
