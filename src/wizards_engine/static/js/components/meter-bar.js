/* Wizards Engine — MeterBar component
 *
 * Renders a horizontal progress bar with label, current/max values,
 * and a fill colour driven by a CSS custom property.
 *
 * Props:
 *   label        (string)  — display label, e.g. "Stress", "Free Time"
 *   current      (number)  — current value
 *   max          (number)  — maximum value
 *   color        (string)  — CSS value, e.g. "var(--we-stress-red)"
 *   effectiveMax (number, optional) — if set and < max, shows a marker
 *                            at that position (used for degraded bonds)
 *
 * Usage:
 *   components.meterBar.render({ label: 'Stress', current: 3, max: 5,
 *                                color: 'var(--we-stress-red)' })
 *
 * Returns an HTML string; insert with el.innerHTML or similar.
 * No interactive state — purely presentational.
 */

window.components = window.components || {};

window.components.meterBar = (function () {
  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  /**
   * Delegate to shared utils (window.utils — loaded via utils.js).
   */
  var _esc = function (str) { return window.utils.esc(str); };

  /**
   * Clamp a value to [0, max], guarding against null / undefined.
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
   * Build the inline style for the fill bar using CSS gradient so the filled
   * and unfilled track portions sit in a single element.
   * @param {number} current
   * @param {number} max
   * @param {string} color — CSS colour value
   * @returns {string} inline style value
   */
  function _fillStyle(current, max, color) {
    if (max === 0) {
      return "background: var(--pico-muted-border-color, #333);";
    }
    var pct = Math.round((current / max) * 100);
    // Guard against CSS injection — only pass colour values we control
    var safeColor = String(color).replace(/[<>"]/g, "");
    return (
      "background: linear-gradient(to right, " +
      safeColor + " " + pct + "%, " +
      "var(--pico-muted-border-color, #444) " + pct + "%);"
    );
  }

  /**
   * Build a style attribute for the effectiveMax marker line.
   * Positioned as a left-percentage within the track.
   * @param {number} effectiveMax
   * @param {number} max
   * @returns {string} inline style value
   */
  function _markerStyle(effectiveMax, max) {
    if (!max) return "";
    var pct = Math.round((effectiveMax / max) * 100);
    return (
      "position: absolute; top: 0; bottom: 0; " +
      "left: " + pct + "%; " +
      "width: 2px; " +
      "background: var(--pico-contrast, #fff); " +
      "opacity: 0.5;"
    );
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  return {
    /**
     * Render the MeterBar to an HTML string.
     * @param {object} props
     * @param {string} props.label
     * @param {number} props.current
     * @param {number} props.max
     * @param {string} props.color
     * @param {number} [props.effectiveMax]
     * @returns {string}
     */
    render: function (props) {
      var label = String(props.label || "");
      var max = Number(props.max) || 0;
      var current = _clamp(props.current, max);
      var color = String(props.color || "var(--pico-primary)");

      var hasMarker = (
        props.effectiveMax !== undefined &&
        props.effectiveMax !== null &&
        Number(props.effectiveMax) < max
      );
      var effectiveMax = hasMarker ? _clamp(props.effectiveMax, max) : 0;

      var markerHtml = hasMarker
        ? '<div aria-hidden="true" style="' + _markerStyle(effectiveMax, max) + '"></div>'
        : "";

      return (
        '<div class="meter-bar">' +
          '<div class="meter-bar__header">' +
            '<span class="meter-bar__label">' + _esc(label) + '</span>' +
            '<span class="meter-bar__value">' + current + '/' + max + '</span>' +
          '</div>' +
          '<div class="meter-bar__track"' +
               ' role="progressbar"' +
               ' aria-valuenow="' + current + '"' +
               ' aria-valuemin="0"' +
               ' aria-valuemax="' + max + '"' +
               ' aria-label="' + _esc(label) + ' ' + current + ' of ' + max + '">' +
            '<div class="meter-bar__fill" style="' + _fillStyle(current, max, color) + '">' +
              markerHtml +
            '</div>' +
          '</div>' +
        '</div>'
      );
    },
  };
})();
