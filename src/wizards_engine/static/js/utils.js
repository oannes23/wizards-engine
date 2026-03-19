/* Wizards Engine — shared UI utilities
 *
 * Exposed as window.utils so all component and view scripts can consume
 * these helpers without duplicating them.
 *
 * Available immediately (no defer required — load this script first).
 *
 * API:
 *   window.utils.esc(str)                    — HTML-escape a value
 *   window.utils.relativeTime(isoString)     — e.g. "just now", "2m ago"
 *   window.utils.clamp(value, min, max)      — numeric clamp
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

  return { esc: esc, relativeTime: relativeTime, clamp: clamp };
})();
