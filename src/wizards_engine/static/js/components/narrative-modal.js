/* Wizards Engine — Narrative Modal component
 *
 * Provides a reusable overlay dialog for collecting narrative text before
 * submitting a player direct action.
 *
 * Usage:
 *   window.components.narrativeModal.show({
 *     title:    "Recharge: Relentless",  // heading text
 *     required: true,                    // submit disabled when textarea empty
 *     onSubmit: function(narrative) { ... },
 *     onCancel: function() { ... },      // optional
 *   });
 *
 * The component injects its markup into a singleton container
 * (#narrative-modal-root) and removes it on close.  The container is
 * created automatically on first use if it does not exist.
 *
 * Registered as: window.components.narrativeModal
 */

window.components = window.components || {};

window.components.narrativeModal = (function () {
  var CONTAINER_ID = "narrative-modal-root";
  var TEXTAREA_ID  = "narrative-modal-textarea";
  var SUBMIT_ID    = "narrative-modal-submit";
  var CANCEL_ID    = "narrative-modal-cancel";
  var OVERLAY_ID   = "narrative-modal-overlay";

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  /**
   * Return (creating if necessary) the singleton root element into which the
   * modal markup is injected.
   * @returns {HTMLElement}
   */
  function _getRoot() {
    var el = document.getElementById(CONTAINER_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = CONTAINER_ID;
      document.body.appendChild(el);
    }
    return el;
  }

  /**
   * Remove all modal markup and event listeners.
   * @param {object} listeners — {overlay, cancel, submit, keydown}
   */
  function _teardown(listeners) {
    if (listeners.keydown) {
      document.removeEventListener("keydown", listeners.keydown);
    }
    var root = document.getElementById(CONTAINER_ID);
    if (root) {
      root.innerHTML = "";
    }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Show the narrative modal.
   *
   * @param {object} options
   * @param {string}   options.title    — modal heading
   * @param {boolean}  options.required — when true, submit is disabled until
   *                                      the textarea has non-empty text
   * @param {function} options.onSubmit — called with the narrative string on submit
   * @param {function} [options.onCancel] — called with no args on cancel/close
   * @returns {function} cleanup — call to dismiss the modal programmatically
   */
  function show(options) {
    var title    = (options && options.title)    ? String(options.title) : "Narrative";
    var required = !!(options && options.required);
    var onSubmit = (options && typeof options.onSubmit === "function") ? options.onSubmit : function () {};
    var onCancel = (options && typeof options.onCancel === "function") ? options.onCancel : function () {};

    var root = _getRoot();
    var listeners = {};

    // Build modal HTML
    root.innerHTML =
      '<div id="' + OVERLAY_ID + '" class="nm-overlay" role="presentation">' +
        '<dialog id="narrative-modal-dialog"' +
        '        class="nm-dialog"' +
        '        open' +
        '        aria-modal="true"' +
        '        aria-labelledby="narrative-modal-title">' +
          '<h3 id="narrative-modal-title" class="nm-title">' +
            window.utils.esc(title) +
          '</h3>' +
          '<label for="' + TEXTAREA_ID + '" class="nm-label">' +
            (required ? 'Narrative (required)' : 'Narrative (optional)') +
          '</label>' +
          '<textarea id="' + TEXTAREA_ID + '"' +
          '          class="nm-textarea"' +
          '          rows="4"' +
          '          placeholder="Describe what happens..."' +
          '          aria-required="' + (required ? 'true' : 'false') + '"' +
          '></textarea>' +
          '<div class="nm-footer">' +
            '<button id="' + CANCEL_ID + '"' +
            '        class="nm-btn nm-btn--cancel secondary outline">' +
              'Cancel' +
            '</button>' +
            '<button id="' + SUBMIT_ID + '"' +
            '        class="nm-btn nm-btn--submit"' +
            '        ' + (required ? 'disabled' : '') + '>' +
              'Submit' +
            '</button>' +
          '</div>' +
        '</dialog>' +
      '</div>';

    // Focus the textarea immediately
    var textarea = document.getElementById(TEXTAREA_ID);
    if (textarea) {
      // Short timeout lets the DOM settle before focusing
      setTimeout(function () {
        if (textarea) textarea.focus();
      }, 50);
    }

    // ---------------------------------------------------------------------------
    // Close / submit helpers
    // ---------------------------------------------------------------------------

    function _close() {
      _teardown(listeners);
    }

    function _cancel() {
      _close();
      onCancel();
    }

    function _submit() {
      var text = textarea ? textarea.value : "";
      if (required && !text.trim()) return;
      _close();
      onSubmit(text.trim());
    }

    // ---------------------------------------------------------------------------
    // Enable/disable submit based on textarea content
    // ---------------------------------------------------------------------------

    if (required && textarea) {
      listeners.input = function () {
        var submitBtn = document.getElementById(SUBMIT_ID);
        if (submitBtn) {
          submitBtn.disabled = !textarea.value.trim();
        }
      };
      textarea.addEventListener("input", listeners.input);
    }

    // ---------------------------------------------------------------------------
    // Wire button clicks
    // ---------------------------------------------------------------------------

    var cancelBtn = document.getElementById(CANCEL_ID);
    if (cancelBtn) {
      listeners.cancelClick = function () { _cancel(); };
      cancelBtn.addEventListener("click", listeners.cancelClick);
    }

    var submitBtn = document.getElementById(SUBMIT_ID);
    if (submitBtn) {
      listeners.submitClick = function () { _submit(); };
      submitBtn.addEventListener("click", listeners.submitClick);
    }

    // ---------------------------------------------------------------------------
    // Overlay click dismisses (cancel)
    // ---------------------------------------------------------------------------

    var overlay = document.getElementById(OVERLAY_ID);
    if (overlay) {
      listeners.overlayClick = function (e) {
        // Only dismiss when clicking the overlay background itself, not the dialog
        if (e.target === overlay) {
          _cancel();
        }
      };
      overlay.addEventListener("click", listeners.overlayClick);
    }

    // ---------------------------------------------------------------------------
    // Keyboard: Escape to cancel, Enter to submit (when not in textarea)
    // ---------------------------------------------------------------------------

    listeners.keydown = function (e) {
      if (e.key === "Escape") {
        _cancel();
      }
    };
    document.addEventListener("keydown", listeners.keydown);

    // Return a cleanup function for programmatic dismissal
    return _close;
  }

  return { show: show };
})();
