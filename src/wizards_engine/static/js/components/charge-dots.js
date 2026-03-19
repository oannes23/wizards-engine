/* Wizards Engine — ChargeDots component
 *
 * Renders a row of filled / empty dots representing charges on a trait or bond.
 *
 * Props:
 *   current      (number)  — number of filled dots
 *   max          (number)  — total number of dots (5 for traits, variable for bonds)
 *   variant      (string)  — "trait" or "bond" — controls accent colour
 *   effectiveMax (number, optional) — for degraded bonds: dots beyond
 *                            effectiveMax are shown as unavailable (crossed)
 *
 * Renders: ●●●○○  (filled / empty / unavailable dots)
 *
 * Usage:
 *   components.chargeDots.render({ current: 3, max: 5, variant: 'trait' })
 *
 * Returns an HTML string. No interactive state — purely presentational.
 */

window.components = window.components || {};

window.components.chargeDots = (function () {
  // --------------------------------------------------------------------------
  // Constants
  // --------------------------------------------------------------------------

  // Unicode dot characters for accessibility — aria-label carries the
  // numeric meaning so screen readers do not read individual symbols.
  var DOT_FILLED = "\u25CF";      // ● LARGE CIRCLE (filled)
  var DOT_EMPTY  = "\u25CB";      // ○ LARGE CIRCLE (empty)
  var DOT_UNAVAIL = "\u2715";     // ✕ MULTIPLICATION X (unavailable/degraded)

  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  /**
   * Clamp a value to [0, max].
   * @param {number} value
   * @param {number} max
   * @returns {number}
   */
  function _clamp(value, max) {
    var v = Number(value) || 0;
    var m = Number(max) || 0;
    return Math.min(Math.max(v, 0), m);
  }

  /**
   * Delegate to shared utils (window.utils — loaded via utils.js).
   */
  var _esc = function (str) { return window.utils.esc(str); };

  /**
   * Determine the BEM modifier class for this dot based on its position.
   * @param {number} index       — 0-based dot position
   * @param {number} current     — filled dot count
   * @param {number} effectiveMax — cap for "available" dots (undefined = max)
   * @param {string} variant     — "trait" | "bond"
   * @returns {string} CSS class string
   */
  function _dotClass(index, current, effectiveMax, variant) {
    var base = "charge-dots__dot charge-dots__dot--" + variant;
    if (index >= effectiveMax) {
      return base + " charge-dots__dot--unavailable";
    }
    if (index < current) {
      return base + " charge-dots__dot--filled";
    }
    return base + " charge-dots__dot--empty";
  }

  /**
   * Choose the display character for this dot.
   * @param {number} index
   * @param {number} current
   * @param {number} effectiveMax
   * @returns {string}
   */
  function _dotChar(index, current, effectiveMax) {
    if (index >= effectiveMax) return DOT_UNAVAIL;
    if (index < current)      return DOT_FILLED;
    return DOT_EMPTY;
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  return {
    /**
     * Render ChargeDots to an HTML string.
     * @param {object} props
     * @param {number} props.current
     * @param {number} props.max
     * @param {string} props.variant — "trait" | "bond"
     * @param {number} [props.effectiveMax]
     * @returns {string}
     */
    render: function (props) {
      var max = Math.max(Number(props.max) || 0, 0);
      var current = _clamp(props.current, max);
      var variant = props.variant === "bond" ? "bond" : "trait";

      var hasEffectiveMax = (
        props.effectiveMax !== undefined &&
        props.effectiveMax !== null &&
        Number(props.effectiveMax) < max
      );
      var effectiveMax = hasEffectiveMax
        ? _clamp(props.effectiveMax, max)
        : max;

      var dots = [];
      for (var i = 0; i < max; i++) {
        var cls = _dotClass(i, current, effectiveMax, variant);
        var ch  = _dotChar(i, current, effectiveMax);
        dots.push('<span class="' + _esc(cls) + '" aria-hidden="true">' + ch + '</span>');
      }

      var ariaLabel = current + " of " + max + " charges";
      if (hasEffectiveMax) {
        ariaLabel += " (" + (max - effectiveMax) + " degraded)";
      }

      return (
        '<span class="charge-dots charge-dots--' + variant + '"' +
              ' role="img"' +
              ' aria-label="' + _esc(ariaLabel) + '">' +
          dots.join("") +
        '</span>'
      );
    },
  };
})();
