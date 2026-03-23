/* Wizards Engine — Sacrifice Builder component
 *
 * An interactive list builder for magic sacrifice entries used by
 * use_magic and charge_magic proposal forms.
 *
 * Each sacrifice entry has a type (gnosis, stress, free_time, bond, trait,
 * other) with type-specific inputs. A running Gnosis-equivalent total is
 * displayed and updated live.
 *
 * Gnosis equivalences:
 *   gnosis      — 1:1
 *   stress      — 2 per point
 *   free_time   — (3 + lowest_magic_stat_level) per point (backend computes
 *                 this; frontend shows a fixed 3+ estimate)
 *   bond        — 10 (destroys the bond)
 *   trait       — 10 (destroys the trait)
 *   other       — GM-assigned (shown as "?" in running total)
 *
 * Alpine.js-driven: the component registers an Alpine data factory that
 * produces a plain object compatible with x-data. The host view is responsible
 * for mounting it.
 *
 * Public interface
 * ----------------
 *   window.components.sacrificeBuilder.makeData(character)
 *     Returns a data object for Alpine x-data use.
 *     - character: the full character object from GET /api/v1/characters/:id
 *
 *   window.components.sacrificeBuilder.buildHtml(idPrefix)
 *     Returns an HTML string for the sacrifice builder UI.
 *     - idPrefix: string prepended to element IDs to avoid collisions
 *                 when multiple instances are on the page.
 *
 * The data object exposes:
 *   sacrifices          — array of sacrifice entry objects
 *   addSacrificeType    — string, the currently-selected type in the add dropdown
 *   totalGnosisEquiv()  — computed: sum of gnosis equivalents (excludes "other")
 *   hasOther()          — computed: true if any "other" entry exists
 *   addSacrifice()      — adds a new entry of the selected type
 *   removeSacrifice(i)  — removes entry at index i
 *   toApiList()         — serialises sacrifice entries to the API shape
 *
 * Registers as: window.components.sacrificeBuilder
 */

window.components = window.components || {};

window.components.sacrificeBuilder = (function () {

  // -------------------------------------------------------------------------
  // Gnosis-equivalent helpers
  // -------------------------------------------------------------------------

  /**
   * Return the Gnosis equivalent for a single sacrifice entry.
   * "other" entries return 0 (GM assigns value); the UI flags this separately.
   *
   * @param {object} entry
   * @returns {number}
   */
  function _gnosisEquiv(entry) {
    switch (entry.type) {
      case "gnosis":
        return Math.max(0, parseInt(entry.amount, 10) || 0);
      case "stress":
        return Math.max(0, parseInt(entry.amount, 10) || 0) * 2;
      case "free_time":
        // Backend uses (3 + lowest_magic_stat_level); frontend uses 3 as a
        // conservative estimate. The preview note clarifies this.
        return Math.max(0, parseInt(entry.amount, 10) || 0) * 3;
      case "bond":
      case "trait":
        return entry.target_id ? 10 : 0;
      case "other":
      default:
        return 0;
    }
  }

  // -------------------------------------------------------------------------
  // makeData — returns an Alpine-compatible data object
  // -------------------------------------------------------------------------

  /**
   * Build the reactive data object for the sacrifice builder.
   *
   * @param {object} character — character detail from GET /api/v1/characters/:id
   * @returns {object}
   */
  function makeData(character) {
    return {
      // The list of sacrifice entries being built.
      sacrifices: [],

      // The type selected in the "add sacrifice" dropdown.
      addSacrificeType: "gnosis",

      // Character reference for bond/trait pickers.
      _character: character,

      /**
       * List of active bonds available to sacrifice.
       * @returns {Array}
       */
      activeBonds: function () {
        var active = (this._character && this._character.bonds && this._character.bonds.active) || [];
        return active.filter(function (b) {
          return b.slot_type && b.slot_type.indexOf("bond") !== -1 && b.charges > 0;
        });
      },

      /**
       * List of active traits available to sacrifice.
       * @returns {Array}
       */
      activeTraits: function () {
        var active = (this._character && this._character.traits && this._character.traits.active) || [];
        return active.filter(function (t) {
          return (t.slot_type === "core_trait" || t.slot_type === "role_trait") && t.charge > 0;
        });
      },

      /**
       * Running Gnosis-equivalent total, excluding "other" entries.
       * @returns {number}
       */
      totalGnosisEquiv: function () {
        var total = 0;
        for (var i = 0; i < this.sacrifices.length; i++) {
          total += _gnosisEquiv(this.sacrifices[i]);
        }
        return total;
      },

      /**
       * True if any sacrifice entry is of type "other" (GM-assigned value).
       * @returns {boolean}
       */
      hasOther: function () {
        for (var i = 0; i < this.sacrifices.length; i++) {
          if (this.sacrifices[i].type === "other") return true;
        }
        return false;
      },

      /**
       * Add a new sacrifice entry of the currently-selected type.
       */
      addSacrifice: function () {
        var type = this.addSacrificeType;
        var entry = { type: type };

        switch (type) {
          case "gnosis":
          case "stress":
          case "free_time":
            entry.amount = 1;
            break;
          case "bond":
            entry.target_id = "";
            break;
          case "trait":
            entry.target_id = "";
            break;
          case "other":
            entry.description = "";
            entry.amount = 1;
            break;
        }

        this.sacrifices.push(entry);
      },

      /**
       * Remove the sacrifice entry at the given index.
       * @param {number} index
       */
      removeSacrifice: function (index) {
        this.sacrifices.splice(index, 1);
      },

      /**
       * Serialise the sacrifice list to the shape expected by the backend API.
       * Bond and trait entries need target_id. Amount entries need amount.
       * Other entries need description and amount.
       *
       * @returns {Array}
       */
      toApiList: function () {
        return this.sacrifices.map(function (entry) {
          switch (entry.type) {
            case "gnosis":
            case "stress":
            case "free_time":
              return { type: entry.type, amount: parseInt(entry.amount, 10) || 0 };
            case "bond":
            case "trait":
              return { type: entry.type, target_id: entry.target_id };
            case "other":
              return {
                type: "other",
                description: entry.description || "",
                amount: parseInt(entry.amount, 10) || 0,
              };
            default:
              return entry;
          }
        });
      },
    };
  }

  // -------------------------------------------------------------------------
  // buildHtml — returns the HTML string for the sacrifice builder UI
  // -------------------------------------------------------------------------

  var SACRIFICE_TYPE_OPTIONS = [
    { value: "gnosis",     label: "Gnosis"     },
    { value: "stress",     label: "Stress"     },
    { value: "free_time",  label: "Free Time"  },
    { value: "bond",       label: "Bond (destroys)"  },
    { value: "trait",      label: "Trait (destroys)" },
    { value: "other",      label: "Other (GM assigns value)" },
  ];

  /**
   * Build the HTML string for the sacrifice builder component.
   * Uses Alpine x-for / x-show / x-model directives. The data is expected
   * to be provided by a parent x-data scope that includes the makeData()
   * properties (sacrifices, addSacrificeType, etc.).
   *
   * @param {string} idPrefix — prefix for element IDs (e.g. "use-magic")
   * @returns {string}
   */
  function buildHtml(idPrefix) {
    var typeOptions = SACRIFICE_TYPE_OPTIONS.map(function (opt) {
      return '<option value="' + window.utils.escAttr(opt.value) + '">' + window.utils.escAttr(opt.label) + '</option>';
    }).join("");

    return [
      '<fieldset class="sacrifice-builder">',
      '  <legend>Sacrifices</legend>',

      // Running total
      '  <div class="sacrifice-total" aria-live="polite">',
      '    <strong>Gnosis equivalent: </strong>',
      '    <span x-text="totalGnosisEquiv()"></span>',
      '    <template x-if="hasOther()">',
      '      <span> + <abbr title="GM assigns value for Other entries">?</abbr></span>',
      '    </template>',
      '    <small> (converted to sacrifice dice on submit)</small>',
      '  </div>',

      // Sacrifice entry list
      '  <ul class="sacrifice-list" aria-label="Sacrifice entries">',
      '    <template x-for="(entry, index) in sacrifices" :key="index">',
      '      <li class="sacrifice-entry">',

      // Type badge
      '        <span class="sacrifice-entry__type" x-text="entry.type.replace(\'_\', \' \')"></span>',

      // Gnosis amount input
      '        <template x-if="entry.type === \'gnosis\'">',
      '          <label>',
      '            Amount',
      '            <input type="number"',
      '                   :id="\'sac-gnosis-\' + index"',
      '                   x-model.number="entry.amount"',
      '                   min="0"',
      '                   inputmode="numeric"',
      '                   aria-label="Gnosis sacrifice amount" />',
      '          </label>',
      '        </template>',

      // Stress amount input (with trauma warning)
      '        <template x-if="entry.type === \'stress\'">',
      '          <div>',
      '            <label>',
      '              Amount',
      '              <input type="number"',
      '                     :id="\'sac-stress-\' + index"',
      '                     x-model.number="entry.amount"',
      '                     min="0"',
      '                     inputmode="numeric"',
      '                     aria-label="Stress sacrifice amount" />',
      '            </label>',
      '            <small class="sacrifice-stress-warn">Warning: taking Stress may trigger Trauma if at or near maximum.</small>',
      '          </div>',
      '        </template>',

      // Free Time amount input
      '        <template x-if="entry.type === \'free_time\'">',
      '          <label>',
      '            Amount',
      '            <input type="number"',
      '                   :id="\'sac-ft-\' + index"',
      '                   x-model.number="entry.amount"',
      '                   min="0"',
      '                   inputmode="numeric"',
      '                   aria-label="Free Time sacrifice amount" />',
      '          </label>',
      '        </template>',

      // Bond picker
      '        <template x-if="entry.type === \'bond\'">',
      '          <label>',
      '            Bond',
      '            <select :id="\'sac-bond-\' + index"',
      '                    x-model="entry.target_id"',
      '                    aria-label="Select bond to sacrifice">',
      '              <option value="">Select a bond...</option>',
      '              <template x-for="b in activeBonds()" :key="b.id">',
      '                <option :value="b.id"',
      '                        x-text="b.label + (b.target_name ? \' (with \' + b.target_name + \')\' : \'\') + \' — value: 10 Gnosis\'"></option>',
      '              </template>',
      '            </select>',
      '            <small>Destroys the bond permanently. Value: 10 Gnosis equivalent.</small>',
      '          </label>',
      '        </template>',

      // Trait picker
      '        <template x-if="entry.type === \'trait\'">',
      '          <label>',
      '            Trait',
      '            <select :id="\'sac-trait-\' + index"',
      '                    x-model="entry.target_id"',
      '                    aria-label="Select trait to sacrifice">',
      '              <option value="">Select a trait...</option>',
      '              <template x-for="t in activeTraits()" :key="t.id">',
      '                <option :value="t.id"',
      '                        x-text="t.name + \' (\' + t.slot_type.replace(\'_\', \' \') + \', charge: \' + t.charge + \') — value: 10 Gnosis\'"></option>',
      '              </template>',
      '            </select>',
      '            <small>Destroys the trait permanently. Value: 10 Gnosis equivalent.</small>',
      '          </label>',
      '        </template>',

      // Other: description + GM-assigned amount
      '        <template x-if="entry.type === \'other\'">',
      '          <div class="sacrifice-other-fields">',
      '            <label>',
      '              Description',
      '              <input type="text"',
      '                     :id="\'sac-other-desc-\' + index"',
      '                     x-model="entry.description"',
      '                     placeholder="Describe what you are sacrificing..."',
      '                     aria-label="Other sacrifice description" />',
      '            </label>',
      '            <label>',
      '              Estimated amount <small>(GM assigns final value)</small>',
      '              <input type="number"',
      '                     :id="\'sac-other-amt-\' + index"',
      '                     x-model.number="entry.amount"',
      '                     min="0"',
      '                     inputmode="numeric"',
      '                     aria-label="Other sacrifice estimated amount" />',
      '            </label>',
      '          </div>',
      '        </template>',

      // Remove button
      '        <button type="button"',
      '                class="sacrifice-entry__remove"',
      '                @click="removeSacrifice(index)"',
      '                :aria-label="\'Remove \' + entry.type.replace(\'_\', \' \') + \' sacrifice\'">',
      '          Remove',
      '        </button>',

      '      </li>',
      '    </template>',

      '    <template x-if="sacrifices.length === 0">',
      '      <li class="sacrifice-list__empty"><em>No sacrifices added yet.</em></li>',
      '    </template>',
      '  </ul>',

      // Add sacrifice controls
      '  <div class="sacrifice-add">',
      '    <label for="' + window.utils.escAttr(idPrefix) + '-add-type">Add sacrifice</label>',
      '    <select id="' + window.utils.escAttr(idPrefix) + '-add-type"',
      '            x-model="addSacrificeType">',
      typeOptions,
      '    </select>',
      '    <button type="button"',
      '            class="sacrifice-add__btn"',
      '            @click="addSacrifice()">',
      '      Add',
      '    </button>',
      '  </div>',

      '</fieldset>',
    ].join("\n");
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  return {
    makeData: makeData,
    buildHtml: buildHtml,
  };
})();
