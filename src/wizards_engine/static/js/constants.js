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
 *   window.constants.SKILL_NAMES        — ordered list of skill identifiers
 *   window.constants.METER_COLORS       — CSS variable map for meter colors
 */

window.constants = (function () {
  // ---------------------------------------------------------------------------
  // Numeric caps
  // ---------------------------------------------------------------------------

  /** Maximum Stress value before a Trauma resolve_trauma proposal is generated. */
  var STRESS_MAX = 9;

  /** Maximum Free Time a character can accumulate. */
  var FT_MAX = 20;

  /** Maximum Plot points a character can hold. */
  var PLOT_MAX = 5;

  /**
   * Display cap for the Gnosis meter bar. The actual Gnosis value can exceed
   * this (there is no hard maximum), but the bar treats this as 100%.
   */
  var GNOSIS_DISPLAY_MAX = 23;

  // ---------------------------------------------------------------------------
  // Skill names
  // ---------------------------------------------------------------------------

  /**
   * Ordered list of the six core skill identifiers as they appear in the API
   * and character data. Use these for iteration and lookup.
   */
  var SKILL_NAMES = [
    "force",
    "finesse",
    "focus",
    "presence",
    "insight",
    "magic",
  ];

  // ---------------------------------------------------------------------------
  // Meter colors
  // ---------------------------------------------------------------------------

  /**
   * CSS variable (or fallback value) for each resource meter.
   * These reference PicoCSS theme variables with hex fallbacks for
   * environments where the variables are not defined.
   */
  var METER_COLORS = {
    stress:    "var(--pico-del-color, #c0392b)",
    free_time: "var(--pico-ins-color, #27ae60)",
    plot:      "var(--pico-primary, #1095c1)",
    gnosis:    "var(--pico-secondary, #805ad5)",
  };

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------

  return {
    STRESS_MAX:         STRESS_MAX,
    FT_MAX:             FT_MAX,
    PLOT_MAX:           PLOT_MAX,
    GNOSIS_DISPLAY_MAX: GNOSIS_DISPLAY_MAX,
    SKILL_NAMES:        SKILL_NAMES,
    METER_COLORS:       METER_COLORS,
  };
})();
