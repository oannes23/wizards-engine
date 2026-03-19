/* Wizards Engine — Join view (invite redemption)
 *
 * Route:  #/join
 * Reached from:  login.js when POST /auth/login returns type:"invite"
 *
 * Flow:
 *   1. Retrieve the invite code stored by login.js
 *      (sessionStorage key "we_invite_code", fallback window._weInviteCode).
 *   2. If no code is found, redirect to #/login (stale/direct navigation).
 *   3. Render a form with character name and display name inputs.
 *   4. On submit, call POST /api/v1/game/join {code, character_name, display_name}.
 *   5. On success: setUser(response), redirect to #/ (player home).
 *   6. Errors: api.js toast + inline message.
 *
 * Registers as:  window.views.join
 * Called by:     router.js route table entry for "/join"
 */

window.views = window.views || {};

window.views.join = (function () {
  // -------------------------------------------------------------------------
  // Code retrieval — written by login.js before redirecting here
  // -------------------------------------------------------------------------

  /**
   * Retrieve the invite code that login.js stored before navigating here.
   * Returns null if no code is available.
   * @returns {string|null}
   */
  function _retrieveInviteCode() {
    try {
      var code = sessionStorage.getItem("we_invite_code");
      if (code) return code;
    } catch (_) {
      // sessionStorage unavailable
    }
    // Fallback to window global set by login.js when sessionStorage is blocked
    return window._weInviteCode || null;
  }

  /**
   * Clear the stored invite code after a successful or abandoned join attempt.
   */
  function _clearInviteCode() {
    try {
      sessionStorage.removeItem("we_invite_code");
    } catch (_) {
      // ignore
    }
    window._weInviteCode = null;
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return function render() {
    var el = document.getElementById("view");
    if (!el) return;

    var inviteCode = _retrieveInviteCode();

    // Guard: no code means the user navigated here directly or the session
    // expired. Send them back to login.
    if (!inviteCode) {
      window.location.replace("#/login");
      return;
    }

    el.innerHTML = [
      '<section class="auth-card">',
      '  <hgroup>',
      '    <h1>Join the Game</h1>',
      '    <p>Choose a name for yourself and your character.</p>',
      '  </hgroup>',
      '  <form id="join-form" novalidate>',
      '    <label for="join-display-name">Your display name</label>',
      '    <input',
      '      id="join-display-name"',
      '      type="text"',
      '      name="display_name"',
      '      autocomplete="nickname"',
      '      placeholder="e.g. Alex"',
      '      maxlength="50"',
      '      required',
      '    />',
      '    <small>1–50 characters. Shown to other players.</small>',
      '    <label for="join-character-name">Character name</label>',
      '    <input',
      '      id="join-character-name"',
      '      type="text"',
      '      name="character_name"',
      '      autocomplete="off"',
      '      placeholder="e.g. Sera Valdris"',
      '      maxlength="100"',
      '      required',
      '    />',
      '    <small>The name of your player character.</small>',
      '    <p id="join-error" role="alert" class="error-text" hidden></p>',
      '    <button type="submit" id="join-submit">Join</button>',
      '  </form>',
      '</section>',
    ].join("\n");

    var form = document.getElementById("join-form");
    var displayNameInput = document.getElementById("join-display-name");
    var charNameInput = document.getElementById("join-character-name");
    var errorEl = document.getElementById("join-error");
    var submitBtn = document.getElementById("join-submit");

    displayNameInput.focus();

    form.addEventListener("submit", function (evt) {
      evt.preventDefault();

      var displayName = displayNameInput.value.trim();
      var characterName = charNameInput.value.trim();

      if (!displayName || !characterName) {
        errorEl.textContent = "Both your display name and character name are required.";
        errorEl.hidden = false;
        return;
      }

      submitBtn.disabled = true;
      submitBtn.setAttribute("aria-busy", "true");
      errorEl.hidden = true;

      api
        .post("/api/v1/game/join", {
          code: inviteCode,
          display_name: displayName,
          character_name: characterName,
        })
        .then(function (data) {
          // Server sets the auth cookie; clean up the stored code
          _clearInviteCode();
          if (typeof Alpine !== "undefined" && Alpine.store("app")) {
            Alpine.store("app").setUser(data);
          }
          window.location.replace("#/");
        })
        .catch(function (err) {
          submitBtn.disabled = false;
          submitBtn.removeAttribute("aria-busy");

          var msg =
            (err && err.message) ||
            "Could not join. Your invite link may have already been used.";
          errorEl.textContent = msg;
          errorEl.hidden = false;
        });
    });
  };
})();
