/* Wizards Engine — shared UI utilities
 *
 * Exposed as window.utils so all component and view scripts can consume
 * these helpers without duplicating them.
 *
 * Available immediately (no defer required — load this script first).
 *
 * API:
 *   window.utils.esc(str)                    — HTML-escape a value
 *   window.utils.escAttr(str)                — HTML-escape + single-quote escape (for Alpine attrs)
 *   window.utils.snippet(text, maxLen)       — truncate with ellipsis
 *   window.utils.relativeTime(isoString)     — e.g. "just now", "2m ago"
 *   window.utils.clamp(value, min, max)      — numeric clamp
 *   window.utils.showSuccess(message)        — dispatch api:success toast event
 *   window.utils.requireGm(viewEl)           — render access-denied and return false if not GM
 */

window.utils = (function () {
  /**
   * Escape a value for safe insertion into HTML text content or double-quoted attributes.
   * Handles null / undefined gracefully (returns empty string).
   * @param {*} str
   * @returns {string}
   */
  function esc(str) {
    return String(str === undefined || str === null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /**
   * Escape a value for safe use inside Alpine attribute strings (also escapes single quotes).
   * Use this wherever the escaped value appears inside a single-quoted Alpine expression,
   * e.g. @click="doSomething('VALUE')" or :class="{ 'foo': x === 'VALUE' }".
   * @param {*} str
   * @returns {string}
   */
  function escAttr(str) {
    return esc(str).replace(/'/g, "&#39;");
  }

  /**
   * Truncate a string to at most maxLen characters, appending a Unicode ellipsis.
   * Returns an empty string for falsy input.
   * @param {string} text
   * @param {number} maxLen
   * @returns {string}
   */
  function snippet(text, maxLen) {
    if (!text) return "";
    var s = String(text);
    if (s.length <= maxLen) return s;
    return s.slice(0, maxLen).trimEnd() + "\u2026";
  }

  /**
   * Convert an ISO 8601 timestamp string to a human-friendly relative label.
   * Covers: seconds → minutes → hours → days. Beyond 7 days shows locale date.
   * @param {string} isoString
   * @returns {string}
   */
  function relativeTime(isoString) {
    if (!isoString) return "";
    var then;
    try {
      then = new Date(isoString).getTime();
    } catch (_) {
      return String(isoString);
    }
    if (isNaN(then)) return String(isoString);

    var now = Date.now();
    var diffSec = Math.floor((now - then) / 1000);

    if (diffSec < 60)   return "just now";
    if (diffSec < 3600) return Math.floor(diffSec / 60) + "m ago";
    if (diffSec < 86400) return Math.floor(diffSec / 3600) + "h ago";
    if (diffSec < 604800) return Math.floor(diffSec / 86400) + "d ago";

    try {
      return new Date(isoString).toLocaleDateString();
    } catch (_) {
      return String(isoString);
    }
  }

  /**
   * Clamp a numeric value to the range [min, max].
   * @param {number} value
   * @param {number} min
   * @param {number} max
   * @returns {number}
   */
  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  /**
   * Dispatch an api:success custom event so the success toast is shown.
   * Equivalent to the _showSuccess pattern used in many view files.
   * @param {string} message
   */
  function showSuccess(message) {
    document.dispatchEvent(
      new CustomEvent("api:success", {
        detail: { message: message },
        bubbles: true,
      })
    );
  }

  /**
   * GM access guard. If the current user is not a GM, renders an
   * "Access denied — GM only." message into viewEl and returns false.
   * Returns true when the user is a GM (view should proceed normally).
   *
   * Usage:
   *   if (!window.utils.requireGm(viewEl)) return;
   *
   * @param {HTMLElement} viewEl — the #view element (or any container)
   * @returns {boolean}
   */
  function requireGm(viewEl) {
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      if (!Alpine.store("app").isGm()) {
        viewEl.innerHTML =
          '<div class="access-denied">' +
            '<p class="error-text" role="alert">Access denied — GM only.</p>' +
          '</div>';
        return false;
      }
    }
    return true;
  }

  return {
    esc: esc,
    escAttr: escAttr,
    snippet: snippet,
    relativeTime: relativeTime,
    clamp: clamp,
    showSuccess: showSuccess,
    requireGm: requireGm,
  };
})();
