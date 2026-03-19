/* Wizards Engine — Login view
 *
 * Handles three related flows:
 *
 *   1. Manual login (#/login):
 *      - Renders a form with a login code text input.
 *      - On submit, calls POST /api/v1/auth/login {code}.
 *      - type:"user"  → setUser + redirect to role home (#/ or #/gm).
 *      - type:"invite" → store code in sessionStorage, redirect to #/join.
 *
 *   2. Deep-link magic link (/login/<code> path):
 *      - On init, checks window.location.pathname for /login/<code>.
 *      - Extracts code and auto-submits the login form.
 *      - Same success handling as manual login.
 *
 *   3. Renders inline error on failure (api.js also shows the toast).
 *
 * Registers as:  window.views.login
 * Called by:     router.js route table entry for "/login"
 */

window.views = window.views || {};

window.views.login = (function () {
  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  /**
   * Derive the role-appropriate home hash after a successful login.
   * @param {string} role — 'gm' | 'player'
   * @returns {string} hash, e.g. '#/gm' or '#/'
   */
  function _homeHash(role) {
    return role === "gm" ? "#/gm" : "#/";
  }

  /**
   * Extract /login/<code> from the current pathname, or return null.
   * Only matches if the pathname starts with '/login/' and has something after.
   * @returns {string|null}
   */
  function _deepLinkCode() {
    var pathname = window.location.pathname;
    var match = pathname.match(/^\/login\/(.+)$/);
    return match ? match[1] : null;
  }

  /**
   * Submit a login code to the API and handle the response.
   * @param {string} code
   * @param {HTMLElement} errorEl — element to display inline error messages
   * @param {HTMLButtonElement} submitBtn
   */
  function _submitCode(code, errorEl, submitBtn) {
    if (!code || !code.trim()) {
      errorEl.textContent = "Please enter your login code.";
      errorEl.hidden = false;
      return;
    }

    // Disable button during flight
    submitBtn.disabled = true;
    submitBtn.setAttribute("aria-busy", "true");
    errorEl.hidden = true;

    api
      .post("/api/v1/auth/login", { code: code.trim() })
      .then(function (data) {
        if (data && data.type === "invite") {
          // Store the invite code so the join view can retrieve it
          try {
            sessionStorage.setItem("we_invite_code", code.trim());
          } catch (_) {
            // sessionStorage unavailable — fall back to a global
            window._weInviteCode = code.trim();
          }
          window.location.hash = "#/join";
          return;
        }

        // data.type === "user" — cookie is set by the server
        if (typeof Alpine !== "undefined" && Alpine.store("app")) {
          Alpine.store("app").setUser(data);
        }
        window.location.replace(_homeHash(data.role));
      })
      .catch(function (err) {
        // api.js already displayed a toast for non-401 errors.
        // Show an inline message as well for immediate context.
        var msg = (err && err.message) || "Login failed. Check your code and try again.";
        errorEl.textContent = msg;
        errorEl.hidden = false;
        submitBtn.disabled = false;
        submitBtn.removeAttribute("aria-busy");
      });
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return function render() {
    var el = document.getElementById("view");
    if (!el) return;

    // Build the form
    el.innerHTML = [
      '<section class="auth-card">',
      '  <hgroup>',
      '    <h1>Wizards Engine</h1>',
      '    <p>Enter your login code to continue.</p>',
      '  </hgroup>',
      '  <form id="login-form" novalidate>',
      '    <label for="login-code">Login code</label>',
      '    <input',
      '      id="login-code"',
      '      type="text"',
      '      name="code"',
      '      autocomplete="off"',
      '      autocorrect="off"',
      '      autocapitalize="off"',
      '      spellcheck="false"',
      '      placeholder="Paste your code here"',
      '      required',
      '    />',
      '    <p id="login-error" role="alert" class="error-text" hidden></p>',
      '    <button type="submit" id="login-submit">Sign in</button>',
      '  </form>',
      '</section>',
    ].join("\n");

    var form = document.getElementById("login-form");
    var codeInput = document.getElementById("login-code");
    var errorEl = document.getElementById("login-error");
    var submitBtn = document.getElementById("login-submit");

    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      _submitCode(codeInput.value, errorEl, submitBtn);
    });

    // Deep-link auto-submit: if the pathname is /login/<code>, extract and
    // auto-submit without waiting for user interaction.
    var deepCode = _deepLinkCode();
    if (deepCode) {
      codeInput.value = deepCode;
      // Brief timeout lets the DOM paint before the network call
      setTimeout(function () {
        _submitCode(deepCode, errorEl, submitBtn);
      }, 0);
    } else {
      // Focus the input for manual entry
      codeInput.focus();
    }
  };
})();
