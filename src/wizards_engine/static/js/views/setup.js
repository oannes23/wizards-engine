/* Wizards Engine — Setup view (first-run GM account creation)
 *
 * Route:  #/setup
 * Server: GET /setup returns index.html (SPA shell handles rendering)
 *
 * Flow:
 *   1. Render a form with a display name input.
 *   2. On submit, call POST /api/v1/setup {display_name}.
 *   3. On success: setUser(response), redirect to #/gm.
 *   4. On 409 (already set up): show informational message.
 *   5. Other errors: shown via api.js toast + inline message.
 *
 * Registers as:  window.views.setup
 * Called by:     router.js route table entry for "/setup"
 */

window.views = window.views || {};

window.views.setup = (function () {
  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return function render() {
    var el = document.getElementById("view");
    if (!el) return;

    el.innerHTML = [
      '<section class="auth-card">',
      '  <hgroup>',
      '    <h1>First-run Setup</h1>',
      '    <p>Create the GM account to get started.</p>',
      '  </hgroup>',
      '  <form id="setup-form" novalidate>',
      '    <label for="setup-display-name">Your display name</label>',
      '    <input',
      '      id="setup-display-name"',
      '      type="text"',
      '      name="display_name"',
      '      autocomplete="nickname"',
      '      placeholder="e.g. Morgan"',
      '      maxlength="50"',
      '      required',
      '    />',
      '    <small>1–50 characters. Shown to all players as "GM [name]".</small>',
      '    <p id="setup-error" role="alert" class="error-text" hidden></p>',
      '    <button type="submit" id="setup-submit">Create GM account</button>',
      '  </form>',
      '</section>',
    ].join("\n");

    var form = document.getElementById("setup-form");
    var nameInput = document.getElementById("setup-display-name");
    var errorEl = document.getElementById("setup-error");
    var submitBtn = document.getElementById("setup-submit");

    nameInput.focus();

    form.addEventListener("submit", function (evt) {
      evt.preventDefault();

      var displayName = nameInput.value.trim();
      if (!displayName) {
        errorEl.textContent = "Please enter a display name.";
        errorEl.hidden = false;
        return;
      }

      submitBtn.disabled = true;
      submitBtn.setAttribute("aria-busy", "true");
      errorEl.hidden = true;

      api
        .post("/api/v1/setup", { display_name: displayName })
        .then(function (data) {
          // Server sets the auth cookie; populate the store and redirect
          if (typeof Alpine !== "undefined" && Alpine.store("app")) {
            Alpine.store("app").setUser(data);
          }
          window.location.replace("#/gm");
        })
        .catch(function (err) {
          submitBtn.disabled = false;
          submitBtn.removeAttribute("aria-busy");

          if (err && err.status === 409) {
            // Setup already completed — show a distinct helpful message
            errorEl.textContent =
              "Setup already completed. Use your magic link to log in.";
          } else {
            var msg =
              (err && err.message) || "Setup failed. Please try again.";
            errorEl.textContent = msg;
          }
          errorEl.hidden = false;
        });
    });
  };
})();
