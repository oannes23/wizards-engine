/* Wizards Engine — GM Players & Invites view
 *
 * Routes: #/gm/players  and  #/gm/invites
 * Access: GM only
 *
 * Two sections on the same page, toggled by a tab bar:
 *   Players — roster of all player accounts with character names, role badges,
 *             and magic login links. Each row supports "Regenerate login link".
 *   Invites — pending (unconsumed) invites with copyable login URLs.
 *             "Create Invite" button calls POST /game/invites.
 *             "Delete" button on unconsumed invites with confirmation.
 *
 * Registers as:  window.views.gmPlayers
 * Called by:     router.js for "/gm/players" and "/gm/invites"
 */

window.views = window.views || {};

window.views.gmPlayers = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var PLAYERS_URL = "/api/v1/players";
  var INVITES_URL = "/api/v1/game/invites";
  var CHARACTERS_SUMMARY_URL = "/api/v1/characters/summary";

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** Currently rendered players list. */
  var _players = [];

  /** Currently rendered invites list (unconsumed only). */
  var _invites = [];

  /** id -> character name map, built from /characters/summary. */
  var _charNameMap = {};

  /** Active tab: 'players' or 'invites'. */
  var _activeTab = "players";

  /** The #view element — stored at render time. */
  var _viewEl = null;

  /** Whether we are the currently mounted view. */
  var _mounted = false;

  /** Set of player IDs with an in-flight regenerate request. */
  var _inflightRegen = {};

  /** Whether an invite creation request is in flight. */
  var _inflightCreateInvite = false;

  /** Set of invite IDs with an in-flight delete request. */
  var _inflightDeleteInvite = {};

  // ---------------------------------------------------------------------------
  // Clipboard helper
  // ---------------------------------------------------------------------------

  /**
   * Copy text to clipboard. Uses navigator.clipboard when available,
   * falls back to execCommand for older browsers.
   *
   * @param {string} text
   * @param {HTMLElement} [feedbackEl] — element to show brief "Copied!" text on
   */
  function _copyToClipboard(text, feedbackEl) {
    function _showFeedback() {
      if (!feedbackEl) return;
      var original = feedbackEl.textContent;
      feedbackEl.textContent = "Copied!";
      setTimeout(function () {
        if (feedbackEl) {
          feedbackEl.textContent = original;
        }
      }, 1500);
    }

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(_showFeedback).catch(function () {
        _fallbackCopy(text, _showFeedback);
      });
    } else {
      _fallbackCopy(text, _showFeedback);
    }
  }

  /**
   * execCommand fallback for non-HTTPS or older browsers.
   * @param {string} text
   * @param {function} callback
   */
  function _fallbackCopy(text, callback) {
    var textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.top = "-9999px";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      document.execCommand("copy");
      if (callback) callback();
    } catch (_) {
      // Silently fail — the URL is visible on screen
    }
    document.body.removeChild(textarea);
  }

  /**
   * Build a full login URL from a path returned by the API.
   * The API returns paths like "/login/<code>".
   * @param {string} path
   * @returns {string}
   */
  function _fullLoginUrl(path) {
    return window.location.origin + path;
  }

  // ---------------------------------------------------------------------------
  // Toast helpers
  // ---------------------------------------------------------------------------


  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  /**
   * Render the tab bar HTML.
   */
  function _renderTabBar() {
    var playersActive = _activeTab === "players" ? " gm-players__tab--active" : "";
    var invitesActive = _activeTab === "invites" ? " gm-players__tab--active" : "";
    return (
      '<div class="gm-players__tabs" role="tablist">' +
        '<button class="gm-players__tab' + playersActive + '" ' +
          'role="tab" aria-selected="' + (_activeTab === "players") + '" ' +
          'id="gm-players-tab-players" data-tab="players">Players</button>' +
        '<button class="gm-players__tab' + invitesActive + '" ' +
          'role="tab" aria-selected="' + (_activeTab === "invites") + '" ' +
          'id="gm-players-tab-invites" data-tab="invites">Invites</button>' +
      '</div>'
    );
  }

  /**
   * Render a single player row.
   * @param {object} player
   */
  function _renderPlayerRow(player) {
    var charName = (player.character_id && _charNameMap[player.character_id])
      ? _charNameMap[player.character_id]
      : null;

    var roleBadgeClass = player.role === "gm"
      ? "gm-players__role-badge gm-players__role-badge--gm"
      : "gm-players__role-badge gm-players__role-badge--player";

    var activeText = player.is_active ? "Active" : "Inactive";
    var activeClass = player.is_active
      ? "gm-players__status gm-players__status--active"
      : "gm-players__status gm-players__status--inactive";

    var charHtml = "";
    if (player.character_id) {
      var charLabel = charName || player.character_id;
      charHtml =
        '<a class="gm-players__char-link" ' +
          'href="#/gm/world/characters/' + player.character_id + '">' +
          window.utils.esc(charLabel) +
        '</a>';
    } else {
      charHtml = '<span class="gm-players__no-char">No character</span>';
    }

    var loginLinkHtml = "";
    if (player.login_url) {
      var fullUrl = _fullLoginUrl(player.login_url);
      loginLinkHtml =
        '<button class="gm-players__copy-btn" ' +
          'data-copy-url="' + window.utils.escAttr(fullUrl) + '" ' +
          'title="Click to copy login link" ' +
          'aria-label="Copy login link for ' + window.utils.escAttr(player.display_name) + '">' +
          'Copy link' +
        '</button>';
    }

    var regenDisabled = _inflightRegen[player.id] ? " disabled" : "";
    var regenHtml =
      '<button class="gm-players__regen-btn" ' +
        'data-player-id="' + player.id + '"' + regenDisabled + ' ' +
        'title="Regenerate magic login link" ' +
        'aria-label="Regenerate login link for ' + window.utils.escAttr(player.display_name) + '">' +
        (_inflightRegen[player.id] ? "Regenerating..." : "Regen link") +
      '</button>';

    return (
      '<tr class="gm-players__row" data-player-id="' + player.id + '">' +
        '<td class="gm-players__col-name">' +
          '<span class="gm-players__display-name">' + window.utils.esc(player.display_name) + '</span>' +
        '</td>' +
        '<td class="gm-players__col-role">' +
          '<span class="' + roleBadgeClass + '">' + window.utils.esc(player.role) + '</span>' +
        '</td>' +
        '<td class="gm-players__col-char">' + charHtml + '</td>' +
        '<td class="gm-players__col-status">' +
          '<span class="' + activeClass + '">' + activeText + '</span>' +
        '</td>' +
        '<td class="gm-players__col-link">' + loginLinkHtml + '</td>' +
        '<td class="gm-players__col-actions">' + regenHtml + '</td>' +
      '</tr>'
    );
  }

  /**
   * Render the Players section content.
   */
  function _renderPlayersSection() {
    if (_players.length === 0) {
      return (
        '<div class="gm-players__empty" role="status">' +
          '<p>No players registered yet.</p>' +
        '</div>'
      );
    }

    var rows = "";
    for (var i = 0; i < _players.length; i++) {
      rows += _renderPlayerRow(_players[i]);
    }

    return (
      '<div class="gm-players__table-wrap">' +
        '<table class="gm-players__table">' +
          '<thead>' +
            '<tr>' +
              '<th scope="col">Name</th>' +
              '<th scope="col">Role</th>' +
              '<th scope="col">Character</th>' +
              '<th scope="col">Status</th>' +
              '<th scope="col">Login Link</th>' +
              '<th scope="col">Actions</th>' +
            '</tr>' +
          '</thead>' +
          '<tbody>' + rows + '</tbody>' +
        '</table>' +
      '</div>'
    );
  }

  /**
   * Render a single invite row.
   * @param {object} invite
   */
  function _renderInviteRow(invite) {
    if (invite.is_consumed) return "";

    var fullUrl = _fullLoginUrl(invite.login_url);
    var deleteDisabled = _inflightDeleteInvite[invite.id] ? " disabled" : "";

    return (
      '<li class="gm-players__invite-item" data-invite-id="' + invite.id + '">' +
        '<div class="gm-players__invite-url">' +
          '<button class="gm-players__invite-copy-btn" ' +
            'data-copy-url="' + window.utils.escAttr(fullUrl) + '" ' +
            'title="Click to copy invite link" ' +
            'aria-label="Copy invite link">' +
            window.utils.esc(fullUrl) +
          '</button>' +
        '</div>' +
        '<div class="gm-players__invite-actions">' +
          '<button class="gm-players__invite-delete-btn" ' +
            'data-invite-id="' + invite.id + '"' + deleteDisabled + ' ' +
            'aria-label="Delete invite">' +
            (_inflightDeleteInvite[invite.id] ? "Deleting..." : "Delete") +
          '</button>' +
        '</div>' +
      '</li>'
    );
  }

  /**
   * Render the Invites section content.
   */
  function _renderInvitesSection() {
    var createDisabled = _inflightCreateInvite ? " disabled" : "";
    var createLabel = _inflightCreateInvite ? "Creating..." : "Create Invite";

    var pending = _invites.filter(function (inv) { return !inv.is_consumed; });

    var inviteListHtml = "";
    if (pending.length === 0) {
      inviteListHtml =
        '<p class="gm-players__invites-empty">No pending invites.</p>';
    } else {
      var rows = "";
      for (var i = 0; i < pending.length; i++) {
        rows += _renderInviteRow(pending[i]);
      }
      inviteListHtml = '<ul class="gm-players__invite-list">' + rows + '</ul>';
    }

    return (
      '<div class="gm-players__invites-header">' +
        '<p class="gm-players__invites-hint">' +
          'Each invite link can be used once. Share the link with a new player to let them join.' +
        '</p>' +
        '<button class="gm-players__create-invite-btn" id="gm-players-create-invite"' +
          createDisabled + '>' +
          createLabel +
        '</button>' +
      '</div>' +
      inviteListHtml
    );
  }

  /**
   * Re-render the full view into _viewEl.
   */
  function _renderList() {
    if (!_viewEl || !_mounted) return;

    var sectionHtml = _activeTab === "players"
      ? _renderPlayersSection()
      : _renderInvitesSection();

    _viewEl.innerHTML =
      '<div class="gm-players">' +
        '<hgroup>' +
          '<h2>Player Roster</h2>' +
          '<p class="gm-players__subtitle">Manage players and invite links</p>' +
        '</hgroup>' +
        _renderTabBar() +
        '<div class="gm-players__panel" role="tabpanel" ' +
          'aria-labelledby="gm-players-tab-' + _activeTab + '">' +
          sectionHtml +
        '</div>' +
      '</div>';

    _attachListeners();
  }

  /**
   * Render the loading state.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-players">' +
        '<hgroup>' +
          '<h2>Player Roster</h2>' +
          '<p aria-busy="true">Loading...</p>' +
        '</hgroup>' +
      '</div>';
  }

  /**
   * Render an error state with retry.
   */
  function _renderError() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-players">' +
        '<hgroup><h2>Player Roster</h2></hgroup>' +
        '<p class="error-text" role="alert">Failed to load data.</p>' +
        '<button id="gm-players-retry">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("gm-players-retry");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () { _fetchAll(true); });
    }
  }

  // ---------------------------------------------------------------------------
  // Event listener attachment
  // ---------------------------------------------------------------------------

  /**
   * Attach all event listeners to the rendered DOM.
   * Called after every _renderList().
   */
  function _attachListeners() {
    if (!_viewEl || !_mounted) return;

    // Tab switching
    var tabs = _viewEl.querySelectorAll(".gm-players__tab");
    for (var t = 0; t < tabs.length; t++) {
      (function (tab) {
        tab.addEventListener("click", function () {
          var tabKey = tab.getAttribute("data-tab");
          if (tabKey && tabKey !== _activeTab) {
            _activeTab = tabKey;
            _renderList();
          }
        });
      })(tabs[t]);
    }

    if (_activeTab === "players") {
      _attachPlayerListeners();
    } else {
      _attachInviteListeners();
    }
  }

  function _attachPlayerListeners() {
    if (!_viewEl) return;

    // Copy login link buttons
    var copyBtns = _viewEl.querySelectorAll(".gm-players__copy-btn");
    for (var c = 0; c < copyBtns.length; c++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var url = btn.getAttribute("data-copy-url");
          if (url) {
            _copyToClipboard(url, btn);
          }
        });
      })(copyBtns[c]);
    }

    // Regenerate link buttons
    var regenBtns = _viewEl.querySelectorAll(".gm-players__regen-btn");
    for (var r = 0; r < regenBtns.length; r++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var playerId = btn.getAttribute("data-player-id");
          if (playerId) {
            _handleRegenToken(playerId);
          }
        });
      })(regenBtns[r]);
    }
  }

  function _attachInviteListeners() {
    if (!_viewEl) return;

    // Create invite button
    var createBtn = document.getElementById("gm-players-create-invite");
    if (createBtn) {
      createBtn.addEventListener("click", _handleCreateInvite);
    }

    // Copy invite URL buttons
    var copyBtns = _viewEl.querySelectorAll(".gm-players__invite-copy-btn");
    for (var c = 0; c < copyBtns.length; c++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var url = btn.getAttribute("data-copy-url");
          if (url) {
            _copyToClipboard(url, btn);
          }
        });
      })(copyBtns[c]);
    }

    // Delete invite buttons
    var deleteBtns = _viewEl.querySelectorAll(".gm-players__invite-delete-btn");
    for (var d = 0; d < deleteBtns.length; d++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var inviteId = btn.getAttribute("data-invite-id");
          if (inviteId) {
            _handleDeleteInvite(inviteId);
          }
        });
      })(deleteBtns[d]);
    }
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Fetch character summary and populate _charNameMap.
   * Best-effort — failures are silently ignored.
   * @returns {Promise}
   */
  function _fetchCharacterNames() {
    return api
      .get(CHARACTERS_SUMMARY_URL, { silent: true })
      .then(function (data) {
        _charNameMap = {};
        var items = (data && data.items) ? data.items : [];
        for (var i = 0; i < items.length; i++) {
          _charNameMap[items[i].id] = items[i].name;
        }
      })
      .catch(function () {
        _charNameMap = {};
      });
  }

  /**
   * Fetch players list and store in _players.
   * @returns {Promise}
   */
  function _fetchPlayers() {
    return api
      .get(PLAYERS_URL)
      .then(function (data) {
        _players = Array.isArray(data) ? data : [];
      });
  }

  /**
   * Fetch invites list and store unconsumed ones in _invites.
   * @returns {Promise}
   */
  function _fetchInvites() {
    return api
      .get(INVITES_URL)
      .then(function (data) {
        var items = (data && data.items) ? data.items : [];
        _invites = items.filter(function (inv) { return !inv.is_consumed; });
      });
  }

  /**
   * Fetch all data needed for the view and re-render.
   * @param {boolean} [isInitial] — if true, show loading state first
   */
  function _fetchAll(isInitial) {
    if (!_mounted) return;

    if (isInitial) {
      _renderLoading();
    }

    // Fetch character names and both lists in parallel
    Promise.all([_fetchCharacterNames(), _fetchPlayers(), _fetchInvites()])
      .then(function () {
        if (!_mounted) return;
        _renderList();
      })
      .catch(function () {
        if (!_mounted) return;
        _renderError();
      });
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  /**
   * Regenerate a player's magic login token.
   * Shows a confirmation dialog first.
   * @param {string} playerId
   */
  function _handleRegenToken(playerId) {
    if (_inflightRegen[playerId]) return;

    var player = null;
    for (var i = 0; i < _players.length; i++) {
      if (_players[i].id === playerId) {
        player = _players[i];
        break;
      }
    }

    var name = player ? player.display_name : "this player";
    var confirmed = window.confirm(
      "Regenerate the magic login link for " + name + "?\n\n" +
      "This will invalidate their current link. They will need the new link to log in."
    );
    if (!confirmed) return;

    _inflightRegen[playerId] = true;
    _renderList();

    api
      .post("/api/v1/players/" + playerId + "/regenerate-token", {})
      .then(function (data) {
        delete _inflightRegen[playerId];
        if (!_mounted) return;

        // Update the player's login_url in our local state
        if (data && data.login_url) {
          for (var i = 0; i < _players.length; i++) {
            if (_players[i].id === playerId) {
              _players[i].login_url = data.login_url;
              break;
            }
          }
        }
        window.utils.showSuccess("Login link regenerated for " + name + ".");
        _renderList();
      })
      .catch(function () {
        delete _inflightRegen[playerId];
        if (!_mounted) return;
        _renderList();
      });
  }

  /**
   * Create a new invite via POST /game/invites.
   * On success, prepend the new invite to the list and switch to invites tab.
   */
  function _handleCreateInvite() {
    if (_inflightCreateInvite) return;
    _inflightCreateInvite = true;
    _renderList();

    api
      .post(INVITES_URL, {})
      .then(function (data) {
        _inflightCreateInvite = false;
        if (!_mounted) return;

        if (data) {
          _invites.unshift(data);
        }
        _activeTab = "invites";
        _renderList();
        window.utils.showSuccess("Invite created. Share the link with your new player.");
      })
      .catch(function () {
        _inflightCreateInvite = false;
        if (!_mounted) return;
        _renderList();
      });
  }

  /**
   * Delete an unconsumed invite.
   * Shows a confirmation dialog first.
   * @param {string} inviteId
   */
  function _handleDeleteInvite(inviteId) {
    if (_inflightDeleteInvite[inviteId]) return;

    var confirmed = window.confirm("Delete this invite link? It will no longer be usable.");
    if (!confirmed) return;

    _inflightDeleteInvite[inviteId] = true;
    _renderList();

    api
      .del(INVITES_URL + "/" + inviteId)
      .then(function () {
        delete _inflightDeleteInvite[inviteId];
        if (!_mounted) return;
        // Remove from list
        _invites = _invites.filter(function (inv) { return inv.id !== inviteId; });
        _renderList();
        window.utils.showSuccess("Invite deleted.");
      })
      .catch(function () {
        delete _inflightDeleteInvite[inviteId];
        if (!_mounted) return;
        _renderList();
      });
  }


  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  /**
   * Called when navigating away from this view.
   */
  function _teardown() {
    _mounted = false;
    _players = [];
    _invites = [];
    _charNameMap = {};
    _inflightRegen = {};
    _inflightCreateInvite = false;
    _inflightDeleteInvite = {};
  }

  /**
   * One-time hashchange listener that calls _teardown when leaving this view.
   * Removes itself after first navigation away.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/gm/players" && path !== "/gm/invites") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the GM Players view.
   * Called by router.js for "/gm/players" and "/gm/invites".
   *
   * @param {object} [opts]
   * @param {string} [opts.tab] — 'players' (default) or 'invites'
   */
  return function render(opts) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // Guard: only GMs should see this view
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      var store = Alpine.store("app");
      if (!store.isGm()) {
        _viewEl.innerHTML =
          '<div class="gm-players">' +
            '<p class="error-text" role="alert">Access denied — GM only.</p>' +
          '</div>';
        return;
      }
    }

    // Set initial tab from opts (used by /gm/invites route)
    _activeTab = (opts && opts.tab === "invites") ? "invites" : "players";

    // Reset state for a fresh mount
    _mounted = true;
    _players = [];
    _invites = [];
    _charNameMap = {};
    _inflightRegen = {};
    _inflightCreateInvite = false;
    _inflightDeleteInvite = {};

    // Initial data fetch
    _fetchAll(true);

    // Teardown when navigating away
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
