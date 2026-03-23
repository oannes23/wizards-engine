/* Wizards Engine — game constants
 *
 * Exposed as window.constants so all view and component scripts can reference
 * canonical game values without magic numbers.
 *
 * Load order: after utils.js, before all view/component scripts.
 *
 * API:
 *   window.constants.STRESS_MAX          — 9  (maximum Stress before Trauma)
 *   window.constants.FT_MAX              — 20 (maximum Free Time)
 *   window.constants.PLOT_MAX            — 5  (maximum Plot points)
 *   window.constants.GNOSIS_DISPLAY_MAX  — 23 (display cap for Gnosis meter)
 *   window.constants.SKILL_NAMES         — ordered list of skill identifiers
 *   window.constants.METER_COLORS        — CSS variable map for meter colors
 */

window.constants = (function () {
  var STRESS_MAX = 9;
  var FT_MAX = 20;
  var PLOT_MAX = 5;
  var GNOSIS_DISPLAY_MAX = 23;

  var SKILL_NAMES = [
    "awareness",
    "composure",
    "influence",
    "finesse",
    "speed",
    "power",
    "knowledge",
    "technology",
  ];

  var METER_COLORS = {
    stress:    "var(--we-stress-red, #c0392b)",
    free_time: "var(--we-ft-green, #27ae60)",
    plot:      "var(--we-plot-amber, #d4a017)",
    gnosis:    "var(--we-gnosis-blue, #805ad5)",
  };

  return {
    STRESS_MAX:         STRESS_MAX,
    FT_MAX:             FT_MAX,
    PLOT_MAX:           PLOT_MAX,
    GNOSIS_DISPLAY_MAX: GNOSIS_DISPLAY_MAX,
    SKILL_NAMES:        SKILL_NAMES,
    METER_COLORS:       METER_COLORS,
  };
})();
