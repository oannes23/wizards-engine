/* Wizards Engine — shared UI utilities
 *
 * Exposed as window.utils so all component and view scripts can consume
 * these helpers without duplicating them.
 *
 * Available immediately (no defer required — load this script first).
 *
 * API:
 *   window.utils.esc(str)                    — HTML-escape a value (text / attr)
 *   window.utils.escAttr(str)                — HTML-escape including single quotes
 *   window.utils.relativeTime(isoString)     — e.g. "just now", "2m ago"
 *   window.utils.clamp(value, min, max)      — numeric clamp
 *   window.utils.snippet(text, maxLen)       — truncate with ellipsis
 *   window.utils.showSuccess(message)        — dispatch api:success toast event
 *   window.utils.isGm()                      — true if current Alpine store user is GM
 *   window.utils.requireGm(viewEl)           — render access-denied and return false if not GM
 */

window.utils = (function () {
  /**
   * Escape a value for safe insertion into HTML attribute or text content.
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
   * Escape a value for use inside HTML attribute strings delimited by single
   * quotes (e.g. Alpine x-data or onclick strings).  Extends esc() by also
   * escaping single-quote characters.
   * @param {*} str
   * @returns {string}
   */
  function escAttr(str) {
    return esc(str).replace(/'/g, "&#39;");
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
   * Truncate a string to at most maxLen characters, appending an ellipsis
   * if the string was longer.
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
   * Dispatch an api:success toast event so the global notification layer can
   * display a success message. No-op when the document is unavailable.
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
   * Return true if the current Alpine store user is a GM.
   * Safe to call even before Alpine is initialised — returns false in that case.
   * @returns {boolean}
   */
  function isGm() {
    try {
      return !!(typeof Alpine !== "undefined" && Alpine.store("app") && Alpine.store("app").isGm());
    } catch (_) {
      return false;
    }
  }

  /**
   * Guard helper for GM-only views.
   * If the current user is not a GM, renders an access-denied message into
   * viewEl and returns false. Otherwise returns true.
   *
   * Usage:
   *   if (!window.utils.requireGm(viewEl)) return;
   *
   * @param {HTMLElement} viewEl
   * @returns {boolean}
   */
  function requireGm(viewEl) {
    if (isGm()) return true;
    if (viewEl) {
      viewEl.innerHTML =
        '<div class="access-denied">' +
          '<p class="error-text" role="alert">Access denied — GM only.</p>' +
        '</div>';
    }
    return false;
  }

  return {
    esc: esc,
    escAttr: escAttr,
    relativeTime: relativeTime,
    clamp: clamp,
    snippet: snippet,
    showSuccess: showSuccess,
    isGm: isGm,
    requireGm: requireGm,
  };
})();
