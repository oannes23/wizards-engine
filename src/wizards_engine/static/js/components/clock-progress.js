/* Wizards Engine — ClockProgress component
 *
 * Renders a clock's progress as filled/empty segments.
 *
 * Props:
 *   current (number) — filled segment count
 *   total   (number) — total segment count (any positive integer)
 *   mode    (string) — "compact" or "detail"
 *
 * Compact:  ●●●○○○ 3/6
 * Detail:   [■][■][■][□][□][□] 3/6 segments
 *           Completed clocks add a "Completed" badge.
 *
 * Usage:
 *   components.clockProgress.render({ current: 3, total: 6, mode: 'compact' })
 *
 * Returns an HTML string. No interactive state — purely presentational.
 */

window.components = window.components || {};

window.components.clockProgress = (function () {
  // --------------------------------------------------------------------------
  // Constants
  // --------------------------------------------------------------------------

  // Compact mode uses unicode circles (same visual language as ChargeDots).
  var COMPACT_FILLED = "\u25CF";   // ●
  var COMPACT_EMPTY  = "\u25CB";   // ○

  // Detail mode uses square-bracket boxes for a distinct "clock" feel.
  var DETAIL_FILLED = "\u25A0";    // ■ BLACK SQUARE
  var DETAIL_EMPTY  = "\u25A1";    // □ WHITE SQUARE

  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  /**
   * Clamp a value to [0, max]. Delegates to window.utils.clamp.
   */
  function _clamp(value, max) {
    return window.utils.clamp(value, 0, max);
  }

  /**
   * Build the compact representation: ●●●○○○ 3/6
   * @param {number} current
   * @param {number} total
   * @param {boolean} completed
   * @returns {string} HTML string
   */
  function _renderCompact(current, total, completed) {
    var dots = [];
    for (var i = 0; i < total; i++) {
      var ch = i < current ? COMPACT_FILLED : COMPACT_EMPTY;
      var cls = "clock-progress__dot" + (i < current ? " clock-progress__dot--filled" : "");
      dots.push('<span class="' + cls + '" aria-hidden="true">' + ch + '</span>');
    }

    var badge = completed
      ? ' <span class="clock-progress__badge clock-progress__badge--complete">Completed</span>'
      : "";

    return (
      '<span class="clock-progress clock-progress--compact"' +
            ' role="img"' +
            ' aria-label="' + current + ' of ' + total + ' segments' + (completed ? ', completed' : '') + '">' +
        dots.join("") +
        ' <span class="clock-progress__count" aria-hidden="true">' + current + '/' + total + '</span>' +
        badge +
      '</span>'
    );
  }

  /**
   * Build the detail representation: [■][■][■][□][□][□] 3/6 segments
   * @param {number} current
   * @param {number} total
   * @param {boolean} completed
   * @returns {string} HTML string
   */
  function _renderDetail(current, total, completed) {
    var segments = [];
    for (var i = 0; i < total; i++) {
      var isFilled = i < current;
      var ch = isFilled ? DETAIL_FILLED : DETAIL_EMPTY;
      var cls = "clock-progress__segment" + (isFilled ? " clock-progress__segment--filled" : "");
      // Wrap each segment in brackets for the "clock" aesthetic
      segments.push(
        '<span class="clock-progress__segment-wrap" aria-hidden="true">' +
          '[<span class="' + cls + '">' + ch + '</span>]' +
        '</span>'
      );
    }

    var badge = completed
      ? ' <span class="clock-progress__badge clock-progress__badge--complete">Completed</span>'
      : "";

    return (
      '<div class="clock-progress clock-progress--detail"' +
           ' role="img"' +
           ' aria-label="' + current + ' of ' + total + ' segments' + (completed ? ', completed' : '') + '">' +
        '<div class="clock-progress__segments" aria-hidden="true">' +
          segments.join("") +
        '</div>' +
        '<div class="clock-progress__detail-footer">' +
          '<span class="clock-progress__count">' + current + '/' + total + ' segments</span>' +
          badge +
        '</div>' +
      '</div>'
    );
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  return {
    /**
     * Render ClockProgress to an HTML string.
     * @param {object} props
     * @param {number} props.current
     * @param {number} props.total
     * @param {string} props.mode — "compact" | "detail"
     * @returns {string}
     */
    render: function (props) {
      var total = Math.max(Number(props.total) || 1, 1);
      var current = _clamp(props.current, total);
      var mode = props.mode === "detail" ? "detail" : "compact";
      var completed = current >= total;

      if (mode === "detail") {
        return _renderDetail(current, total, completed);
      }
      return _renderCompact(current, total, completed);
    },
  };
})();
