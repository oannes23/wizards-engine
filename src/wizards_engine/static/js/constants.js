/* Wizards Engine — shared UI constants
 *
 * Exposed as window.constants so all view and component scripts can consume
 * these values without duplicating magic strings.
 *
 * Available immediately — load this script after utils.js.
 *
 * API:
 *   window.constants.METER_COLORS   — CSS color values for the four resource meters
 */

window.constants = (function () {
  /**
   * CSS color values for the four resource meter bars.
   * Use these instead of hardcoding color strings in view files.
   *
   *   stress    — red   (Stress meter)
   *   free_time — green (Free Time meter)
   *   plot      — blue  (Plot meter)
   *   gnosis    — purple (Gnosis meter)
   */
  var METER_COLORS = {
    stress:    "var(--pico-del-color, #c0392b)",
    free_time: "var(--pico-ins-color, #27ae60)",
    plot:      "var(--pico-primary, #1095c1)",
    gnosis:    "var(--pico-secondary, #805ad5)",
  };

  return {
    METER_COLORS: METER_COLORS,
  };
})();
