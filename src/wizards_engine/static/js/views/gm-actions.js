/* Wizards Engine — GM Direct Actions view
 *
 * Route:  #/gm/actions
 * Access: GM only
 *
 * Provides a single-page form for all 14 GM action types:
 *   Character: modify_character, award_xp
 *   Bond:      create_bond, modify_bond, retire_bond
 *   Trait:     create_trait, modify_trait, retire_trait
 *   Effect:    create_effect, modify_effect, retire_effect
 *   World:     modify_group, modify_location, modify_clock
 *
 * Form architecture:
 *   1. Action type dropdown (grouped)
 *   2. Target picker section (adapts per type)
 *   3. Changes section (adapts per type)
 *   4. Narrative + visibility + submit
 *
 * Batch mode: toggle at top queues multiple actions, then submits via
 *   POST /api/v1/gm/actions/batch (1-50 actions).
 * Single mode: submits via POST /api/v1/gm/actions immediately.
 *
 * Registers as:  window.views.gmActions
 * Called by:     router.js route table entry for "/gm/actions"
 */

window.views = window.views || {};

window.views.gmActions = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var MAGIC_STATS = [
    { value: "being",      label: "Being"      },
    { value: "wyrding",    label: "Wyrding"    },
    { value: "summoning",  label: "Summoning"  },
    { value: "enchanting", label: "Enchanting" },
    { value: "dreaming",   label: "Dreaming"   },
  ];

  var VISIBILITY_OPTIONS = [
    { value: "",         label: "(default for action type)" },
    { value: "global",   label: "Global — everyone"        },
    { value: "public",   label: "Public — players"         },
    { value: "familiar", label: "Familiar — bonded"        },
    { value: "bonded",   label: "Bonded — direct bonds"    },
    { value: "private",  label: "Private — owner only"     },
    { value: "gm_only",  label: "GM Only"                  },
    { value: "silent",   label: "Silent — no event"        },
  ];

  var SLOT_TYPES = [
    { value: "core_trait",   label: "Core Trait"   },
    { value: "role_trait",   label: "Role Trait"   },
    { value: "group_trait",  label: "Group Trait"  },
    { value: "feature_trait",label: "Feature Trait"},
  ];

  var EFFECT_TYPES = [
    { value: "charged",   label: "Charged"   },
    { value: "permanent", label: "Permanent" },
  ];

  // Action type groups for the dropdown
  var ACTION_GROUPS = [
    {
      label: "Character",
      actions: [
        { type: "modify_character", label: "Modify Character" },
        { type: "award_xp",        label: "Award XP"         },
      ],
    },
    {
      label: "Bond",
      actions: [
        { type: "create_bond", label: "Create Bond" },
        { type: "modify_bond", label: "Modify Bond" },
        { type: "retire_bond", label: "Retire Bond" },
      ],
    },
    {
      label: "Trait",
      actions: [
        { type: "create_trait", label: "Create Trait" },
        { type: "modify_trait", label: "Modify Trait" },
        { type: "retire_trait", label: "Retire Trait" },
      ],
    },
    {
      label: "Effect",
      actions: [
        { type: "create_effect", label: "Create Effect" },
        { type: "modify_effect", label: "Modify Effect" },
        { type: "retire_effect", label: "Retire Effect" },
      ],
    },
    {
      label: "World",
      actions: [
        { type: "modify_group",    label: "Modify Group"    },
        { type: "modify_location", label: "Modify Location" },
        { type: "modify_clock",    label: "Modify Clock"    },
      ],
    },
  ];

  // Which action types need a character target (for the top-level picker)
  var CHARACTER_TARGET_TYPES = {
    modify_character: true,
    award_xp:         true,
    create_effect:    true,
  };

  // Which action types need a character picked first, then a slot from that character
  var CHARACTER_SLOT_TYPES = {
    modify_bond:  true,
    retire_bond:  true,
    create_bond:  true,   // owner
    create_trait: true,   // owner
    modify_trait: true,
    retire_trait: true,
    modify_effect: true,
    retire_effect: true,
  };

  // ---------------------------------------------------------------------------
  // Alpine data factory
  // ---------------------------------------------------------------------------

  function _makeData() {
    return {
      // -----------------------------------------------------------------------
      // Action type selection
      // -----------------------------------------------------------------------
      selectedType: "",

      // -----------------------------------------------------------------------
      // Target picker state
      // -----------------------------------------------------------------------
      // Lists loaded for pickers
      characters:      [],
      groups:          [],
      locations:       [],
      clocks:          [],
      traitTemplates:  [],

      // Loading/error flags for list fetches
      listsLoading: false,
      listsError:   null,

      // Selected top-level target IDs
      selectedCharacterId:  "",
      selectedGroupId:      "",
      selectedLocationId:   "",
      selectedClockId:      "",

      // For slot-level pickers (bond, trait, effect): first pick a character,
      // then we load that character's detail to show their slots
      slotCharacterId: "",
      slotCharacter:   null,   // full character detail response
      slotLoading:     false,
      slotError:       null,

      // Selected slot IDs (bond slot, trait slot, effect id)
      selectedBondSlotId:   "",
      selectedTraitSlotId:  "",
      selectedEffectId:     "",

      // Bond owner fields (for create_bond)
      bondOwnerType:  "",   // "character", "group", "location"
      bondOwnerId:    "",
      bondTargetType: "",   // "character", "group", "location"
      bondTargetId:   "",

      // -----------------------------------------------------------------------
      // Changes fields — shared across types
      // -----------------------------------------------------------------------

      // modify_character meter changes (each: {op: "delta"|"set", value: int})
      mc_stress_op:      "delta",
      mc_stress_value:   0,
      mc_free_time_op:   "delta",
      mc_free_time_value: 0,
      mc_plot_op:        "delta",
      mc_plot_value:     0,
      mc_gnosis_op:      "delta",
      mc_gnosis_value:   0,
      mc_last_session_time_now: false,
      // Skills: array of {name, level} pairs (added dynamically)
      mc_skill_changes:  [],
      // Magic stats: array of {stat, xp, level} (added dynamically)
      mc_magic_changes:  [],
      // Attributes: raw JSON string
      mc_attributes_json: "",

      // award_xp
      xp_magic_stat: "",
      xp_amount: 1,

      // create_bond / modify_bond
      bond_source_label:  "",
      bond_target_label:  "",
      bond_description:   "",
      bond_bidirectional: false,
      bond_stress_op:         "delta",
      bond_stress_value:      0,
      bond_degradations_op:   "delta",
      bond_degradations_value: 0,

      // create_trait
      trait_slot_type:  "",
      trait_template_id: "",
      trait_name:        "",
      trait_description: "",

      // modify_trait
      trait_charge_op:    "delta",
      trait_charge_value: 0,
      trait_new_name:        "",
      trait_new_description: "",

      // create_effect
      effect_name:           "",
      effect_description:    "",
      effect_type:           "charged",
      effect_power_level:    1,
      effect_charges_current: 0,
      effect_charges_max:    5,

      // modify_effect
      meff_power_level:       0,
      meff_charges_current_op:    "delta",
      meff_charges_current_value: 0,
      meff_charges_max_op:        "delta",
      meff_charges_max_value:     0,
      meff_new_name:        "",
      meff_new_description: "",

      // modify_group
      group_tier: 1,

      // modify_location
      location_parent_id: "",   // "" means null (no parent)

      // modify_clock
      clock_progress_op:    "delta",
      clock_progress_value: 1,
      clock_notes:          "",
      clock_related_events: "",   // comma-separated list
      clock_related_objects: "",  // comma-separated list

      // -----------------------------------------------------------------------
      // Shared fields
      // -----------------------------------------------------------------------
      narrative:  "",
      visibility: "",

      // -----------------------------------------------------------------------
      // Batch mode
      // -----------------------------------------------------------------------
      batchMode:    false,
      batchQueue:   [],    // array of action payloads
      batchError:   null,

      // -----------------------------------------------------------------------
      // Submission state
      // -----------------------------------------------------------------------
      submitting: false,

      // -----------------------------------------------------------------------
      // Validation errors
      // -----------------------------------------------------------------------
      errors: {},

      // -----------------------------------------------------------------------
      // Computed helpers
      // -----------------------------------------------------------------------

      /**
       * Active bonds on slotCharacter.
       */
      characterBonds: function () {
        if (!this.slotCharacter) return [];
        var active = (this.slotCharacter.bonds && this.slotCharacter.bonds.active) || [];
        return active;
      },

      /**
       * Active traits on slotCharacter.
       */
      characterTraits: function () {
        if (!this.slotCharacter) return [];
        var active = (this.slotCharacter.traits && this.slotCharacter.traits.active) || [];
        return active;
      },

      /**
       * Active effects on slotCharacter.
       */
      characterEffects: function () {
        if (!this.slotCharacter) return [];
        var active = (this.slotCharacter.magic_effects && this.slotCharacter.magic_effects.active) || [];
        return active;
      },

      /**
       * Label for the selected action type.
       */
      actionTypeLabel: function () {
        for (var g = 0; g < ACTION_GROUPS.length; g++) {
          var group = ACTION_GROUPS[g];
          for (var a = 0; a < group.actions.length; a++) {
            if (group.actions[a].type === this.selectedType) {
              return group.actions[a].label;
            }
          }
        }
        return this.selectedType;
      },

      /**
       * True if the selected type uses a character slot picker.
       */
      needsSlotCharacter: function () {
        return !!CHARACTER_SLOT_TYPES[this.selectedType];
      },

      /**
       * True if the selected type uses a direct character target (not a slot).
       */
      needsDirectCharacter: function () {
        return !!CHARACTER_TARGET_TYPES[this.selectedType];
      },

      // -----------------------------------------------------------------------
      // Slot changes tracking helpers (for dynamic skill / magic stat rows)
      // -----------------------------------------------------------------------

      addSkillChange: function () {
        this.mc_skill_changes.push({ name: "", level: 1 });
      },

      removeSkillChange: function (index) {
        this.mc_skill_changes.splice(index, 1);
      },

      addMagicChange: function () {
        this.mc_magic_changes.push({ stat: "", xp: 0, level: null });
      },

      removeMagicChange: function (index) {
        this.mc_magic_changes.splice(index, 1);
      },

      // -----------------------------------------------------------------------
      // Data fetching
      // -----------------------------------------------------------------------

      /**
       * Load all reference lists needed for pickers.
       * Called once when the view mounts (or on retry).
       */
      _loadLists: function () {
        var self = this;
        self.listsLoading = true;
        self.listsError = null;

        Promise.all([
          api.get("/api/v1/characters?limit=100"),
          api.get("/api/v1/groups?limit=100"),
          api.get("/api/v1/locations?limit=100"),
          api.get("/api/v1/clocks?limit=100"),
          api.get("/api/v1/trait-templates?limit=100"),
        ])
          .then(function (results) {
            self.characters     = (results[0] && results[0].items) || [];
            self.groups         = (results[1] && results[1].items) || [];
            self.locations      = (results[2] && results[2].items) || [];
            self.clocks         = (results[3] && results[3].items) || [];
            self.traitTemplates = (results[4] && results[4].items) || [];
          })
          .catch(function (err) {
            self.listsError = (err && err.message) || "Could not load reference data.";
          })
          .finally(function () {
            self.listsLoading = false;
          });
      },

      /**
       * Fetch a character's full detail to populate slot pickers.
       * Called when slotCharacterId changes.
       */
      _loadSlotCharacter: function () {
        var self = this;
        if (!self.slotCharacterId) {
          self.slotCharacter = null;
          self.selectedBondSlotId  = "";
          self.selectedTraitSlotId = "";
          self.selectedEffectId    = "";
          return;
        }

        self.slotLoading = true;
        self.slotError   = null;
        self.slotCharacter = null;
        self.selectedBondSlotId  = "";
        self.selectedTraitSlotId = "";
        self.selectedEffectId    = "";

        api
          .get("/api/v1/characters/" + self.slotCharacterId)
          .then(function (data) {
            self.slotCharacter = data;
          })
          .catch(function (err) {
            self.slotError = (err && err.message) || "Could not load character.";
          })
          .finally(function () {
            self.slotLoading = false;
          });
      },

      // -----------------------------------------------------------------------
      // Form reset
      // -----------------------------------------------------------------------

      /**
       * Reset all changes fields to defaults (called when action type changes).
       */
      _resetChanges: function () {
        this.mc_stress_op           = "delta";
        this.mc_stress_value        = 0;
        this.mc_free_time_op        = "delta";
        this.mc_free_time_value     = 0;
        this.mc_plot_op             = "delta";
        this.mc_plot_value          = 0;
        this.mc_gnosis_op           = "delta";
        this.mc_gnosis_value        = 0;
        this.mc_last_session_time_now = false;
        this.mc_skill_changes       = [];
        this.mc_magic_changes       = [];
        this.mc_attributes_json     = "";

        this.xp_magic_stat = "";
        this.xp_amount     = 1;

        this.bond_source_label       = "";
        this.bond_target_label       = "";
        this.bond_description        = "";
        this.bond_bidirectional      = false;
        this.bond_stress_op          = "delta";
        this.bond_stress_value       = 0;
        this.bond_degradations_op    = "delta";
        this.bond_degradations_value = 0;

        this.trait_slot_type    = "";
        this.trait_template_id  = "";
        this.trait_name         = "";
        this.trait_description  = "";

        this.trait_charge_op          = "delta";
        this.trait_charge_value       = 0;
        this.trait_new_name           = "";
        this.trait_new_description    = "";

        this.effect_name            = "";
        this.effect_description     = "";
        this.effect_type            = "charged";
        this.effect_power_level     = 1;
        this.effect_charges_current = 0;
        this.effect_charges_max     = 5;

        this.meff_power_level               = 0;
        this.meff_charges_current_op        = "delta";
        this.meff_charges_current_value     = 0;
        this.meff_charges_max_op            = "delta";
        this.meff_charges_max_value         = 0;
        this.meff_new_name                  = "";
        this.meff_new_description           = "";

        this.group_tier        = 1;
        this.location_parent_id = "";

        this.clock_progress_op      = "delta";
        this.clock_progress_value   = 1;
        this.clock_notes            = "";
        this.clock_related_events   = "";
        this.clock_related_objects  = "";

        this.narrative  = "";
        this.visibility = "";
        this.errors     = {};

        // Target state
        this.selectedCharacterId = "";
        this.selectedGroupId     = "";
        this.selectedLocationId  = "";
        this.selectedClockId     = "";
        this.slotCharacterId     = "";
        this.slotCharacter       = null;
        this.selectedBondSlotId  = "";
        this.selectedTraitSlotId = "";
        this.selectedEffectId    = "";
        this.bondOwnerType  = "";
        this.bondOwnerId    = "";
        this.bondTargetType = "";
        this.bondTargetId   = "";
      },

      // -----------------------------------------------------------------------
      // Payload builder
      // -----------------------------------------------------------------------

      /**
       * Build the action payload for the current form state.
       * Returns null if validation fails (and populates this.errors).
       */
      _buildPayload: function () {
        var self = this;
        var errors = {};

        if (!self.selectedType) {
          errors.selectedType = "Please select an action type.";
          self.errors = errors;
          return null;
        }

        var type = self.selectedType;
        var payload = {
          action_type: type,
          narrative:   self.narrative.trim() || null,
          visibility:  self.visibility || null,
        };

        // ---- modify_character ----
        if (type === "modify_character") {
          if (!self.selectedCharacterId) {
            errors.target = "Please select a character.";
            self.errors = errors;
            return null;
          }
          payload.target_id = self.selectedCharacterId;

          var changes = {};

          // Only include meter changes that are non-zero or explicitly "set"
          if (self.mc_stress_op === "set" || parseInt(self.mc_stress_value, 10) !== 0) {
            changes.stress = { op: self.mc_stress_op, value: parseInt(self.mc_stress_value, 10) || 0 };
          }
          if (self.mc_free_time_op === "set" || parseInt(self.mc_free_time_value, 10) !== 0) {
            changes.free_time = { op: self.mc_free_time_op, value: parseInt(self.mc_free_time_value, 10) || 0 };
          }
          if (self.mc_plot_op === "set" || parseInt(self.mc_plot_value, 10) !== 0) {
            changes.plot = { op: self.mc_plot_op, value: parseInt(self.mc_plot_value, 10) || 0 };
          }
          if (self.mc_gnosis_op === "set" || parseInt(self.mc_gnosis_value, 10) !== 0) {
            changes.gnosis = { op: self.mc_gnosis_op, value: parseInt(self.mc_gnosis_value, 10) || 0 };
          }

          if (self.mc_last_session_time_now) {
            changes.last_session_time_now = Math.floor(Date.now() / 1000);
          }

          // Skills
          if (self.mc_skill_changes.length > 0) {
            var skills = {};
            for (var i = 0; i < self.mc_skill_changes.length; i++) {
              var sc = self.mc_skill_changes[i];
              if (sc.name) {
                skills[sc.name] = parseInt(sc.level, 10) || 0;
              }
            }
            if (Object.keys(skills).length > 0) {
              changes.skills = skills;
            }
          }

          // Magic stats
          if (self.mc_magic_changes.length > 0) {
            var magic_stats = {};
            for (var j = 0; j < self.mc_magic_changes.length; j++) {
              var mc = self.mc_magic_changes[j];
              if (mc.stat) {
                var stat_change = {};
                if (mc.xp !== null && mc.xp !== "" && parseInt(mc.xp, 10) !== 0) {
                  stat_change.xp = parseInt(mc.xp, 10) || 0;
                }
                if (mc.level !== null && mc.level !== "") {
                  stat_change.level = parseInt(mc.level, 10) || 0;
                }
                if (Object.keys(stat_change).length > 0) {
                  magic_stats[mc.stat] = stat_change;
                }
              }
            }
            if (Object.keys(magic_stats).length > 0) {
              changes.magic_stats = magic_stats;
            }
          }

          // Attributes JSON
          if (self.mc_attributes_json.trim()) {
            try {
              changes.attributes = JSON.parse(self.mc_attributes_json);
            } catch (_) {
              errors.mc_attributes_json = "Invalid JSON for attributes.";
              self.errors = errors;
              return null;
            }
          }

          payload.changes = changes;
        }

        // ---- award_xp ----
        else if (type === "award_xp") {
          if (!self.selectedCharacterId) {
            errors.target = "Please select a character.";
            self.errors = errors;
            return null;
          }
          if (!self.xp_magic_stat) {
            errors.xp_magic_stat = "Please select a magic stat.";
            self.errors = errors;
            return null;
          }
          payload.character_id = self.selectedCharacterId;
          payload.magic_stat   = self.xp_magic_stat;
          payload.xp_amount    = parseInt(self.xp_amount, 10) || 1;
        }

        // ---- create_bond ----
        else if (type === "create_bond") {
          if (!self.slotCharacterId) {
            errors.target = "Please select a bond owner (character).";
            self.errors = errors;
            return null;
          }
          if (!self.bondTargetType || !self.bondTargetId) {
            errors.bond_target = "Please select a bond target.";
            self.errors = errors;
            return null;
          }
          payload.owner_type      = "character";
          payload.owner_id        = self.slotCharacterId;
          payload.target_type     = self.bondTargetType;
          payload.target_id       = self.bondTargetId;
          payload.source_label    = self.bond_source_label.trim() || null;
          payload.target_label    = self.bond_target_label.trim() || null;
          payload.description     = self.bond_description.trim() || null;
          payload.bidirectional   = self.bond_bidirectional;
        }

        // ---- modify_bond ----
        else if (type === "modify_bond") {
          if (!self.selectedBondSlotId) {
            errors.target = "Please select a bond to modify.";
            self.errors = errors;
            return null;
          }
          payload.bond_id = self.selectedBondSlotId;
          var bond_changes = {};
          if (self.bond_stress_op === "set" || parseInt(self.bond_stress_value, 10) !== 0) {
            bond_changes.stress = { op: self.bond_stress_op, value: parseInt(self.bond_stress_value, 10) || 0 };
          }
          if (self.bond_degradations_op === "set" || parseInt(self.bond_degradations_value, 10) !== 0) {
            bond_changes.stress_degradations = { op: self.bond_degradations_op, value: parseInt(self.bond_degradations_value, 10) || 0 };
          }
          if (self.bond_source_label.trim()) {
            bond_changes.source_label = self.bond_source_label.trim();
          }
          if (self.bond_target_label.trim()) {
            bond_changes.target_label = self.bond_target_label.trim();
          }
          if (self.bond_description.trim()) {
            bond_changes.description = self.bond_description.trim();
          }
          payload.changes = bond_changes;
        }

        // ---- retire_bond ----
        else if (type === "retire_bond") {
          if (!self.selectedBondSlotId) {
            errors.target = "Please select a bond to retire.";
            self.errors = errors;
            return null;
          }
          payload.bond_id = self.selectedBondSlotId;
        }

        // ---- create_trait ----
        else if (type === "create_trait") {
          if (!self.slotCharacterId) {
            errors.target = "Please select a character (owner).";
            self.errors = errors;
            return null;
          }
          if (!self.trait_slot_type) {
            errors.trait_slot_type = "Please select a slot type.";
            self.errors = errors;
            return null;
          }
          payload.owner_type  = "character";
          payload.owner_id    = self.slotCharacterId;
          payload.slot_type   = self.trait_slot_type;
          payload.template_id = self.trait_template_id || null;
          payload.name        = self.trait_name.trim() || null;
          payload.description = self.trait_description.trim() || null;
        }

        // ---- modify_trait ----
        else if (type === "modify_trait") {
          if (!self.selectedTraitSlotId) {
            errors.target = "Please select a trait to modify.";
            self.errors = errors;
            return null;
          }
          payload.trait_id = self.selectedTraitSlotId;
          var trait_changes = {};
          if (self.trait_charge_op === "set" || parseInt(self.trait_charge_value, 10) !== 0) {
            trait_changes.charge = { op: self.trait_charge_op, value: parseInt(self.trait_charge_value, 10) || 0 };
          }
          if (self.trait_new_name.trim()) {
            trait_changes.name = self.trait_new_name.trim();
          }
          if (self.trait_new_description.trim()) {
            trait_changes.description = self.trait_new_description.trim();
          }
          payload.changes = trait_changes;
        }

        // ---- retire_trait ----
        else if (type === "retire_trait") {
          if (!self.selectedTraitSlotId) {
            errors.target = "Please select a trait to retire.";
            self.errors = errors;
            return null;
          }
          payload.trait_id = self.selectedTraitSlotId;
        }

        // ---- create_effect ----
        else if (type === "create_effect") {
          if (!self.selectedCharacterId) {
            errors.target = "Please select a character.";
            self.errors = errors;
            return null;
          }
          if (!self.effect_name.trim()) {
            errors.effect_name = "Effect name is required.";
            self.errors = errors;
            return null;
          }
          payload.character_id     = self.selectedCharacterId;
          payload.name             = self.effect_name.trim();
          payload.description      = self.effect_description.trim() || null;
          payload.effect_type      = self.effect_type;
          payload.power_level      = parseInt(self.effect_power_level, 10) || 1;
          payload.charges_current  = parseInt(self.effect_charges_current, 10) || 0;
          payload.charges_max      = parseInt(self.effect_charges_max, 10) || 5;
        }

        // ---- modify_effect ----
        else if (type === "modify_effect") {
          if (!self.selectedEffectId) {
            errors.target = "Please select an effect to modify.";
            self.errors = errors;
            return null;
          }
          payload.effect_id = self.selectedEffectId;
          var eff_changes = {};
          if (parseInt(self.meff_power_level, 10) !== 0) {
            eff_changes.power_level = { op: "set", value: parseInt(self.meff_power_level, 10) };
          }
          if (self.meff_charges_current_op === "set" || parseInt(self.meff_charges_current_value, 10) !== 0) {
            eff_changes.charges_current = { op: self.meff_charges_current_op, value: parseInt(self.meff_charges_current_value, 10) || 0 };
          }
          if (self.meff_charges_max_op === "set" || parseInt(self.meff_charges_max_value, 10) !== 0) {
            eff_changes.charges_max = { op: self.meff_charges_max_op, value: parseInt(self.meff_charges_max_value, 10) || 0 };
          }
          if (self.meff_new_name.trim()) {
            eff_changes.name = self.meff_new_name.trim();
          }
          if (self.meff_new_description.trim()) {
            eff_changes.description = self.meff_new_description.trim();
          }
          payload.changes = eff_changes;
        }

        // ---- retire_effect ----
        else if (type === "retire_effect") {
          if (!self.selectedEffectId) {
            errors.target = "Please select an effect to retire.";
            self.errors = errors;
            return null;
          }
          payload.effect_id = self.selectedEffectId;
        }

        // ---- modify_group ----
        else if (type === "modify_group") {
          if (!self.selectedGroupId) {
            errors.target = "Please select a group.";
            self.errors = errors;
            return null;
          }
          payload.target_id = self.selectedGroupId;
          payload.changes   = { tier: parseInt(self.group_tier, 10) || 1 };
        }

        // ---- modify_location ----
        else if (type === "modify_location") {
          if (!self.selectedLocationId) {
            errors.target = "Please select a location.";
            self.errors = errors;
            return null;
          }
          payload.target_id = self.selectedLocationId;
          payload.changes   = { parent_id: self.location_parent_id || null };
        }

        // ---- modify_clock ----
        else if (type === "modify_clock") {
          if (!self.selectedClockId) {
            errors.target = "Please select a clock.";
            self.errors = errors;
            return null;
          }
          payload.target_id = self.selectedClockId;
          payload.changes   = {
            progress: { op: self.clock_progress_op, value: parseInt(self.clock_progress_value, 10) || 0 },
          };
          // Optional metadata fields
          if (self.clock_notes.trim() || self.clock_related_events.trim() || self.clock_related_objects.trim()) {
            payload.metadata = {};
            if (self.clock_notes.trim()) {
              payload.metadata.notes = self.clock_notes.trim();
            }
            if (self.clock_related_events.trim()) {
              payload.metadata.related_events = self.clock_related_events.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
            }
            if (self.clock_related_objects.trim()) {
              payload.metadata.related_objects = self.clock_related_objects.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
            }
          }
        }

        self.errors = {};
        return payload;
      },

      // -----------------------------------------------------------------------
      // Submission
      // -----------------------------------------------------------------------

      /**
       * Submit the current action immediately (single mode).
       */
      submit: function () {
        var self = this;
        var payload = self._buildPayload();
        if (!payload) return;

        self.submitting = true;

        api
          .post("/api/v1/gm/actions", payload)
          .then(function (data) {
            var eventType = (data && data.event_type) || payload.action_type;
            document.dispatchEvent(new CustomEvent("api:success", {
              detail: { message: "Action applied: " + eventType },
              bubbles: true,
            }));
            self._resetChanges();
            self.selectedType = "";
          })
          .catch(function () {
            // api.js shows the error toast; just re-enable the button
          })
          .finally(function () {
            self.submitting = false;
          });
      },

      /**
       * Add the current action to the batch queue (batch mode).
       */
      addToBatch: function () {
        var self = this;
        var payload = self._buildPayload();
        if (!payload) return;

        if (self.batchQueue.length >= 50) {
          self.batchError = "Batch limit reached (50 actions maximum).";
          return;
        }

        self.batchQueue.push(payload);
        self.batchError = null;
        self._resetChanges();
        self.selectedType = "";
      },

      /**
       * Remove an action from the batch queue by index.
       */
      removeFromBatch: function (index) {
        this.batchQueue.splice(index, 1);
      },

      /**
       * Submit all queued actions as a batch.
       */
      submitBatch: function () {
        var self = this;
        if (self.batchQueue.length === 0) {
          self.batchError = "No actions in the batch queue.";
          return;
        }

        self.submitting = true;
        self.batchError = null;

        api
          .post("/api/v1/gm/actions/batch", { actions: self.batchQueue })
          .then(function (data) {
            var count = (data && data.events && data.events.length) || self.batchQueue.length;
            document.dispatchEvent(new CustomEvent("api:success", {
              detail: { message: "Batch applied: " + count + " action" + (count === 1 ? "" : "s") },
              bubbles: true,
            }));
            self.batchQueue = [];
            self._resetChanges();
            self.selectedType = "";
          })
          .catch(function () {
            // api.js shows the error toast
          })
          .finally(function () {
            self.submitting = false;
          });
      },
    };
  }

  // ---------------------------------------------------------------------------
  // HTML escape helper
  // ---------------------------------------------------------------------------

  function _esc(str) {
    return window.utils.esc(str).replace(/'/g, "&#39;");
  }

  // ---------------------------------------------------------------------------
  // HTML template helpers
  // ---------------------------------------------------------------------------

  /**
   * Build the action type dropdown HTML.
   */
  function _buildTypeSelectHtml() {
    var optionsHtml = '<option value="" disabled>Select action type...</option>';
    for (var g = 0; g < ACTION_GROUPS.length; g++) {
      var group = ACTION_GROUPS[g];
      optionsHtml += '<optgroup label="' + _esc(group.label) + '">';
      for (var a = 0; a < group.actions.length; a++) {
        var action = group.actions[a];
        optionsHtml += '<option value="' + _esc(action.type) + '">' + _esc(action.label) + '</option>';
      }
      optionsHtml += '</optgroup>';
    }

    return [
      '<div class="gm-actions__type-row">',
      '  <label for="gm-action-type">Action Type</label>',
      '  <select id="gm-action-type"',
      '          x-model="selectedType"',
      '          @change="_resetChanges()">',
      optionsHtml,
      '  </select>',
      '  <p x-show="errors.selectedType" role="alert" class="error-text" x-text="errors.selectedType"></p>',
      '</div>',
    ].join("\n");
  }

  /**
   * Build the magic stat select options.
   */
  function _buildMagicStatOptions() {
    return MAGIC_STATS.map(function (s) {
      return '<option value="' + _esc(s.value) + '">' + _esc(s.label) + '</option>';
    }).join("");
  }

  /**
   * Build a meter change row (op toggle + value input).
   * Generates x-model bindings for Alpine.
   * @param {string} fieldPrefix — e.g. "mc_stress"
   * @param {string} label — human label
   * @param {string} idPrefix — unique HTML id prefix
   */
  function _buildMeterChangeHtml(fieldPrefix, label, idPrefix) {
    return [
      '<div class="gm-actions__meter-row">',
      '  <label>' + _esc(label) + '</label>',
      '  <div class="gm-actions__meter-controls">',
      '    <select id="' + _esc(idPrefix) + '-op" x-model="' + _esc(fieldPrefix) + '_op"',
      '            aria-label="' + _esc(label) + ' operation">',
      '      <option value="delta">Delta (+/-)</option>',
      '      <option value="set">Set (absolute)</option>',
      '    </select>',
      '    <input id="' + _esc(idPrefix) + '-val" type="number"',
      '           x-model.number="' + _esc(fieldPrefix) + '_value"',
      '           :placeholder="' + _esc(fieldPrefix) + '_op === \'set\' ? \'new value\' : \'amount\'"',
      '           inputmode="numeric"',
      '           aria-label="' + _esc(label) + ' amount" />',
      '  </div>',
      '</div>',
    ].join("\n");
  }

  /**
   * Build the target picker section HTML.
   * Uses x-show directives so only the relevant picker is visible.
   */
  function _buildTargetPickerHtml() {
    // Character options (shared by multiple x-shows)
    var charOpts = [
      '<option value="" disabled>Select character...</option>',
      '<template x-for="c in characters" :key="c.id">',
      '  <option :value="c.id" x-text="c.name"></option>',
      '</template>',
    ].join("\n");

    // Character slot picker (for bond/trait/effect actions)
    var slotCharOpts = [
      '<option value="" disabled>Select character...</option>',
      '<template x-for="c in characters" :key="c.id">',
      '  <option :value="c.id" x-text="c.name"></option>',
      '</template>',
    ].join("\n");

    var groupOpts = [
      '<option value="" disabled>Select group...</option>',
      '<template x-for="g in groups" :key="g.id">',
      '  <option :value="g.id" x-text="g.name"></option>',
      '</template>',
    ].join("\n");

    var locationOpts = [
      '<option value="" disabled>Select location...</option>',
      '<template x-for="l in locations" :key="l.id">',
      '  <option :value="l.id" x-text="l.name"></option>',
      '</template>',
    ].join("\n");

    var clockOpts = [
      '<option value="" disabled>Select clock...</option>',
      '<template x-for="ck in clocks" :key="ck.id">',
      '  <option :value="ck.id" x-text="ck.name"></option>',
      '</template>',
    ].join("\n");

    var ownerTypeOpts = [
      '<option value="" disabled>Select owner type...</option>',
      '<option value="character">Character</option>',
      '<option value="group">Group</option>',
      '<option value="location">Location</option>',
    ].join("\n");

    return [
      // Loading / error
      '<div x-show="listsLoading" aria-live="polite" class="gm-actions__loading">Loading data...</div>',
      '<div x-show="listsError" role="alert" class="error-text" x-text="listsError"></div>',
      '<p x-show="errors.target" role="alert" class="error-text" x-text="errors.target"></p>',

      // Character picker — modify_character, award_xp, create_effect
      '<div x-show="selectedType === \'modify_character\' || selectedType === \'award_xp\' || selectedType === \'create_effect\'" class="gm-actions__target">',
      '  <label for="target-char">Character</label>',
      '  <select id="target-char" x-model="selectedCharacterId">',
      charOpts,
      '  </select>',
      '</div>',

      // Group picker — modify_group
      '<div x-show="selectedType === \'modify_group\'" class="gm-actions__target">',
      '  <label for="target-group">Group</label>',
      '  <select id="target-group" x-model="selectedGroupId">',
      groupOpts,
      '  </select>',
      '</div>',

      // Location picker — modify_location
      '<div x-show="selectedType === \'modify_location\'" class="gm-actions__target">',
      '  <label for="target-loc">Location</label>',
      '  <select id="target-loc" x-model="selectedLocationId">',
      locationOpts,
      '  </select>',
      '</div>',

      // Clock picker — modify_clock
      '<div x-show="selectedType === \'modify_clock\'" class="gm-actions__target">',
      '  <label for="target-clock">Clock</label>',
      '  <select id="target-clock" x-model="selectedClockId">',
      clockOpts,
      '  </select>',
      '</div>',

      // Slot character picker — modify_bond, retire_bond, create_bond (owner), create_trait, modify_trait, retire_trait, modify_effect, retire_effect
      '<div x-show="needsSlotCharacter()" class="gm-actions__target">',
      '  <label for="slot-char">',
      '    <span x-text="selectedType === \'create_bond\' || selectedType === \'create_trait\' ? \'Owner Character\' : \'Character\'"></span>',
      '  </label>',
      '  <select id="slot-char" x-model="slotCharacterId" @change="_loadSlotCharacter()">',
      slotCharOpts,
      '  </select>',
      '  <div x-show="slotLoading" aria-live="polite" class="gm-actions__loading">Loading character...</div>',
      '  <div x-show="slotError" role="alert" class="error-text" x-text="slotError"></div>',
      '</div>',

      // Bond slot picker — modify_bond, retire_bond
      '<div x-show="(selectedType === \'modify_bond\' || selectedType === \'retire_bond\') && slotCharacter" class="gm-actions__target">',
      '  <label for="slot-bond">Bond</label>',
      '  <select id="slot-bond" x-model="selectedBondSlotId">',
      '    <option value="" disabled>Select bond...</option>',
      '    <template x-for="b in characterBonds()" :key="b.id">',
      '      <option :value="b.id"',
      '              x-text="(b.source_label || b.slot_type) + (b.target_name ? \' \u2192 \' + b.target_name : \'\') + \' (charges: \' + (b.stress || 0) + \')\'">',
      '      </option>',
      '    </template>',
      '  </select>',
      '  <template x-if="slotCharacter && characterBonds().length === 0">',
      '    <p class="gm-actions__empty">No active bonds on this character.</p>',
      '  </template>',
      '</div>',

      // Trait slot picker — modify_trait, retire_trait
      '<div x-show="(selectedType === \'modify_trait\' || selectedType === \'retire_trait\') && slotCharacter" class="gm-actions__target">',
      '  <label for="slot-trait">Trait</label>',
      '  <select id="slot-trait" x-model="selectedTraitSlotId">',
      '    <option value="" disabled>Select trait...</option>',
      '    <template x-for="t in characterTraits()" :key="t.id">',
      '      <option :value="t.id"',
      '              x-text="t.name + \' (\' + (t.slot_type || \'trait\').replace(/_/g, \' \') + \', charge: \' + (t.charge || 0) + \')\'">',
      '      </option>',
      '    </template>',
      '  </select>',
      '  <template x-if="slotCharacter && characterTraits().length === 0">',
      '    <p class="gm-actions__empty">No active traits on this character.</p>',
      '  </template>',
      '</div>',

      // Effect picker — modify_effect, retire_effect
      '<div x-show="(selectedType === \'modify_effect\' || selectedType === \'retire_effect\') && slotCharacter" class="gm-actions__target">',
      '  <label for="slot-effect">Effect</label>',
      '  <select id="slot-effect" x-model="selectedEffectId">',
      '    <option value="" disabled>Select effect...</option>',
      '    <template x-for="e in characterEffects()" :key="e.id">',
      '      <option :value="e.id"',
      '              x-text="e.name + \' (\' + (e.effect_type || \'effect\') + \', power: \' + (e.power_level || 1) + \')\'">',
      '      </option>',
      '    </template>',
      '  </select>',
      '  <template x-if="slotCharacter && characterEffects().length === 0">',
      '    <p class="gm-actions__empty">No active effects on this character.</p>',
      '  </template>',
      '</div>',

      // create_bond: owner type/id + target type/id
      '<div x-show="selectedType === \'create_bond\' && slotCharacter" class="gm-actions__target">',
      // Bond target type
      '  <label for="bond-target-type">Bond Target Type</label>',
      '  <select id="bond-target-type" x-model="bondTargetType">',
      ownerTypeOpts,
      '  </select>',
      // Bond target id — character
      '  <template x-if="bondTargetType === \'character\'">',
      '    <div>',
      '      <label for="bond-target-char">Target Character</label>',
      '      <select id="bond-target-char" x-model="bondTargetId">',
      '        <option value="" disabled>Select character...</option>',
      '        <template x-for="c in characters" :key="c.id">',
      '          <option :value="c.id" x-text="c.name"></option>',
      '        </template>',
      '      </select>',
      '    </div>',
      '  </template>',
      // Bond target id — group
      '  <template x-if="bondTargetType === \'group\'">',
      '    <div>',
      '      <label for="bond-target-grp">Target Group</label>',
      '      <select id="bond-target-grp" x-model="bondTargetId">',
      '        <option value="" disabled>Select group...</option>',
      '        <template x-for="g in groups" :key="g.id">',
      '          <option :value="g.id" x-text="g.name"></option>',
      '        </template>',
      '      </select>',
      '    </div>',
      '  </template>',
      // Bond target id — location
      '  <template x-if="bondTargetType === \'location\'">',
      '    <div>',
      '      <label for="bond-target-loc">Target Location</label>',
      '      <select id="bond-target-loc" x-model="bondTargetId">',
      '        <option value="" disabled>Select location...</option>',
      '        <template x-for="l in locations" :key="l.id">',
      '          <option :value="l.id" x-text="l.name"></option>',
      '        </template>',
      '      </select>',
      '    </div>',
      '  </template>',
      '  <p x-show="errors.bond_target" role="alert" class="error-text" x-text="errors.bond_target"></p>',
      '</div>',
    ].join("\n");
  }

  /**
   * Build the changes section HTML for modify_character.
   */
  function _buildModifyCharacterHtml() {
    var skillOptions = [
      "awareness", "composure", "influence", "finesse",
      "speed", "power", "knowledge", "technology",
    ].map(function (s) {
      return '<option value="' + s + '">' + s.charAt(0).toUpperCase() + s.slice(1) + '</option>';
    }).join("");

    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'modify_character\'">',
      '  <legend>Character Changes</legend>',

      _buildMeterChangeHtml("mc_stress",     "Stress",     "mc-stress"),
      _buildMeterChangeHtml("mc_free_time",  "Free Time",  "mc-ft"),
      _buildMeterChangeHtml("mc_plot",       "Plot",       "mc-plot"),
      _buildMeterChangeHtml("mc_gnosis",     "Gnosis",     "mc-gnosis"),

      '  <div class="gm-actions__checkbox-row">',
      '    <label>',
      '      <input type="checkbox" x-model="mc_last_session_time_now" />',
      '      Set last session time to now',
      '    </label>',
      '  </div>',

      // Skills
      '  <div class="gm-actions__sub-section">',
      '    <h4>Skill Changes</h4>',
      '    <template x-for="(sc, i) in mc_skill_changes" :key="i">',
      '      <div class="gm-actions__skill-row">',
      '        <select x-model="sc.name" aria-label="Skill name">',
      '          <option value="" disabled>Select skill...</option>',
      skillOptions,
      '        </select>',
      '        <label>Level',
      '          <input type="number" x-model.number="sc.level" min="0" max="10" inputmode="numeric" aria-label="Skill level" />',
      '        </label>',
      '        <button type="button" class="secondary" @click="removeSkillChange(i)" aria-label="Remove skill change">Remove</button>',
      '      </div>',
      '    </template>',
      '    <button type="button" class="secondary" @click="addSkillChange()">+ Add Skill Change</button>',
      '  </div>',

      // Magic stats
      '  <div class="gm-actions__sub-section">',
      '    <h4>Magic Stat Changes</h4>',
      '    <template x-for="(mc, i) in mc_magic_changes" :key="i">',
      '      <div class="gm-actions__magic-row">',
      '        <select x-model="mc.stat" aria-label="Magic stat">',
      '          <option value="" disabled>Select stat...</option>',
      _buildMagicStatOptions(),
      '        </select>',
      '        <label>XP delta',
      '          <input type="number" x-model.number="mc.xp" inputmode="numeric" aria-label="XP delta" />',
      '        </label>',
      '        <label>Force level',
      '          <input type="number" x-model.number="mc.level" min="0" placeholder="(keep current)" inputmode="numeric" aria-label="Force level" />',
      '        </label>',
      '        <button type="button" class="secondary" @click="removeMagicChange(i)" aria-label="Remove magic stat change">Remove</button>',
      '      </div>',
      '    </template>',
      '    <button type="button" class="secondary" @click="addMagicChange()">+ Add Magic Stat Change</button>',
      '  </div>',

      // Attributes JSON
      '  <div class="gm-actions__sub-section">',
      '    <label for="mc-attributes">Attributes (JSON patch, optional)</label>',
      '    <textarea id="mc-attributes" rows="3"',
      '              x-model="mc_attributes_json"',
      '              placeholder=\'{"key": "value"}\'',
      '              aria-label="Attributes JSON"></textarea>',
      '    <p x-show="errors.mc_attributes_json" role="alert" class="error-text" x-text="errors.mc_attributes_json"></p>',
      '  </div>',

      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build the changes section for award_xp.
   */
  function _buildAwardXpHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'award_xp\'">',
      '  <legend>Award XP</legend>',
      '  <label for="xp-stat">Magic Stat</label>',
      '  <select id="xp-stat" x-model="xp_magic_stat"',
      '          :aria-invalid="errors.xp_magic_stat ? \'true\' : \'false\'">',
      '    <option value="" disabled>Select magic stat...</option>',
      _buildMagicStatOptions(),
      '  </select>',
      '  <p x-show="errors.xp_magic_stat" role="alert" class="error-text" x-text="errors.xp_magic_stat"></p>',
      '  <label for="xp-amount">XP Amount</label>',
      '  <input id="xp-amount" type="number" x-model.number="xp_amount" min="1" value="1" inputmode="numeric" />',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build the bond fields (used by create_bond and modify_bond).
   */
  function _buildBondFieldsHtml() {
    return [
      '<div class="gm-actions__sub-section">',
      '  <label for="bond-src-label">Source Label <small>(how owner sees the bond)</small></label>',
      '  <input id="bond-src-label" type="text" x-model="bond_source_label" placeholder="e.g. Ally, Enemy, Friend..." />',
      '  <label for="bond-tgt-label">Target Label <small>(how target sees the bond)</small></label>',
      '  <input id="bond-tgt-label" type="text" x-model="bond_target_label" placeholder="e.g. Patron, Rival..." />',
      '  <label for="bond-desc">Description</label>',
      '  <textarea id="bond-desc" rows="2" x-model="bond_description" placeholder="Describe the bond..."></textarea>',
      '</div>',
    ].join("\n");
  }

  /**
   * Build create_bond specific fields.
   */
  function _buildCreateBondHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'create_bond\'">',
      '  <legend>Create Bond</legend>',
      // Owner — slotCharacterId is already set by the target picker; show confirmation
      '  <p x-show="slotCharacter">',
      '    Owner: <strong x-text="slotCharacter && slotCharacter.name"></strong> (character)',
      '  </p>',
      _buildBondFieldsHtml(),
      '  <label class="gm-actions__checkbox-label">',
      '    <input type="checkbox" x-model="bond_bidirectional" />',
      '    Bidirectional (create matching bond in reverse)',
      '  </label>',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build modify_bond fields.
   */
  function _buildModifyBondHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'modify_bond\'">',
      '  <legend>Modify Bond</legend>',
      _buildMeterChangeHtml("bond_stress",        "Charges (stress)",       "bond-stress"),
      _buildMeterChangeHtml("bond_degradations",  "Degradations",           "bond-degrad"),
      _buildBondFieldsHtml(),
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build retire_bond section (no extra fields, just confirmation text).
   */
  function _buildRetireBondHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'retire_bond\'">',
      '  <legend>Retire Bond</legend>',
      '  <p x-show="selectedBondSlotId" class="gm-actions__confirm-text">',
      '    This will permanently retire the selected bond.',
      '  </p>',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build create_trait fields.
   */
  function _buildCreateTraitHtml() {
    var slotTypeOptions = SLOT_TYPES.map(function (s) {
      return '<option value="' + _esc(s.value) + '">' + _esc(s.label) + '</option>';
    }).join("");

    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'create_trait\'">',
      '  <legend>Create Trait</legend>',
      '  <label for="trait-slot-type">Slot Type</label>',
      '  <select id="trait-slot-type" x-model="trait_slot_type"',
      '          :aria-invalid="errors.trait_slot_type ? \'true\' : \'false\'">',
      '    <option value="" disabled>Select slot type...</option>',
      slotTypeOptions,
      '  </select>',
      '  <p x-show="errors.trait_slot_type" role="alert" class="error-text" x-text="errors.trait_slot_type"></p>',

      '  <label for="trait-template">Template <small>(optional)</small></label>',
      '  <select id="trait-template" x-model="trait_template_id">',
      '    <option value="">No template (custom trait)</option>',
      '    <template x-for="t in traitTemplates" :key="t.id">',
      '      <option :value="t.id" x-text="t.name + \' (\' + (t.type || \'?\') + \')\'"></option>',
      '    </template>',
      '  </select>',

      '  <label for="trait-name">Name <small>(required if no template)</small></label>',
      '  <input id="trait-name" type="text" x-model="trait_name" placeholder="Trait name..." />',

      '  <label for="trait-desc">Description <small>(optional)</small></label>',
      '  <textarea id="trait-desc" rows="2" x-model="trait_description" placeholder="Describe this trait..."></textarea>',

      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build modify_trait fields.
   */
  function _buildModifyTraitHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'modify_trait\'">',
      '  <legend>Modify Trait</legend>',
      _buildMeterChangeHtml("trait_charge", "Charge", "trait-charge"),
      '  <label for="trait-new-name">New Name <small>(optional)</small></label>',
      '  <input id="trait-new-name" type="text" x-model="trait_new_name" placeholder="Leave blank to keep current..." />',
      '  <label for="trait-new-desc">New Description <small>(optional)</small></label>',
      '  <textarea id="trait-new-desc" rows="2" x-model="trait_new_description" placeholder="Leave blank to keep current..."></textarea>',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build retire_trait fields.
   */
  function _buildRetireTraitHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'retire_trait\'">',
      '  <legend>Retire Trait</legend>',
      '  <p x-show="selectedTraitSlotId" class="gm-actions__confirm-text">',
      '    This will permanently retire the selected trait.',
      '  </p>',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build create_effect fields.
   */
  function _buildCreateEffectHtml() {
    var effectTypeOptions = EFFECT_TYPES.map(function (e) {
      return '<option value="' + _esc(e.value) + '">' + _esc(e.label) + '</option>';
    }).join("");

    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'create_effect\'">',
      '  <legend>Create Effect</legend>',
      '  <label for="eff-name">Name <span aria-hidden="true">*</span></label>',
      '  <input id="eff-name" type="text" x-model="effect_name" placeholder="Effect name..."',
      '         :aria-invalid="errors.effect_name ? \'true\' : \'false\'" />',
      '  <p x-show="errors.effect_name" role="alert" class="error-text" x-text="errors.effect_name"></p>',

      '  <label for="eff-desc">Description</label>',
      '  <textarea id="eff-desc" rows="2" x-model="effect_description" placeholder="Describe this effect..."></textarea>',

      '  <label for="eff-type">Effect Type</label>',
      '  <select id="eff-type" x-model="effect_type">',
      effectTypeOptions,
      '  </select>',

      '  <label for="eff-power">Power Level (1–5)</label>',
      '  <input id="eff-power" type="number" x-model.number="effect_power_level" min="1" max="5" inputmode="numeric" />',

      '  <div x-show="effect_type === \'charged\'">',
      '    <label for="eff-charges-cur">Current Charges</label>',
      '    <input id="eff-charges-cur" type="number" x-model.number="effect_charges_current" min="0" inputmode="numeric" />',
      '    <label for="eff-charges-max">Max Charges</label>',
      '    <input id="eff-charges-max" type="number" x-model.number="effect_charges_max" min="0" inputmode="numeric" />',
      '  </div>',

      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build modify_effect fields.
   */
  function _buildModifyEffectHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'modify_effect\'">',
      '  <legend>Modify Effect</legend>',
      '  <label for="meff-power">Power Level (0 = keep current)</label>',
      '  <input id="meff-power" type="number" x-model.number="meff_power_level" min="0" max="5" inputmode="numeric" />',
      _buildMeterChangeHtml("meff_charges_current", "Current Charges", "meff-cur"),
      _buildMeterChangeHtml("meff_charges_max",      "Max Charges",     "meff-max"),
      '  <label for="meff-name">New Name <small>(optional)</small></label>',
      '  <input id="meff-name" type="text" x-model="meff_new_name" placeholder="Leave blank to keep current..." />',
      '  <label for="meff-desc">New Description <small>(optional)</small></label>',
      '  <textarea id="meff-desc" rows="2" x-model="meff_new_description" placeholder="Leave blank to keep current..."></textarea>',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build retire_effect fields.
   */
  function _buildRetireEffectHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'retire_effect\'">',
      '  <legend>Retire Effect</legend>',
      '  <p x-show="selectedEffectId" class="gm-actions__confirm-text">',
      '    This will permanently retire the selected effect.',
      '  </p>',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build modify_group fields.
   */
  function _buildModifyGroupHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'modify_group\'">',
      '  <legend>Modify Group</legend>',
      '  <label for="group-tier">Tier</label>',
      '  <input id="group-tier" type="number" x-model.number="group_tier" min="0" max="10" inputmode="numeric" />',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build modify_location fields.
   */
  function _buildModifyLocationHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'modify_location\'">',
      '  <legend>Modify Location</legend>',
      '  <label for="loc-parent">Parent Location <small>(empty = top-level)</small></label>',
      '  <select id="loc-parent" x-model="location_parent_id">',
      '    <option value="">(none — top-level)</option>',
      '    <template x-for="l in locations" :key="l.id">',
      '      <option :value="l.id" x-text="l.name"></option>',
      '    </template>',
      '  </select>',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build modify_clock fields.
   */
  function _buildModifyClockHtml() {
    return [
      '<fieldset class="gm-actions__changes" x-show="selectedType === \'modify_clock\'">',
      '  <legend>Modify Clock</legend>',
      _buildMeterChangeHtml("clock_progress", "Progress", "clock-prog"),
      '  <label for="clock-notes">Notes <small>(optional)</small></label>',
      '  <textarea id="clock-notes" rows="2" x-model="clock_notes" placeholder="Annotation for this clock update..."></textarea>',
      '  <label for="clock-events">Related Events <small>(comma-separated IDs, optional)</small></label>',
      '  <input id="clock-events" type="text" x-model="clock_related_events" placeholder="event-id-1, event-id-2..." />',
      '  <label for="clock-objects">Related Objects <small>(comma-separated IDs, optional)</small></label>',
      '  <input id="clock-objects" type="text" x-model="clock_related_objects" placeholder="object-id-1, object-id-2..." />',
      '</fieldset>',
    ].join("\n");
  }

  /**
   * Build the batch queue list HTML.
   */
  function _buildBatchQueueHtml() {
    return [
      '<div x-show="batchMode && batchQueue.length > 0" class="gm-actions__batch-queue">',
      '  <h3>Batch Queue (<span x-text="batchQueue.length"></span>)</h3>',
      '  <ul class="gm-actions__batch-list" aria-label="Queued actions">',
      '    <template x-for="(action, i) in batchQueue" :key="i">',
      '      <li class="gm-actions__batch-item">',
      '        <span x-text="(i + 1) + \'. \' + action.action_type.replace(/_/g, \' \')"></span>',
      '        <span x-show="action.target_id" x-text="\' — target: \' + (action.target_id || \'\')"></span>',
      '        <span x-show="action.character_id" x-text="\' — char: \' + (action.character_id || \'\')"></span>',
      '        <button type="button" class="secondary gm-actions__batch-remove"',
      '                @click="removeFromBatch(i)"',
      '                :aria-label="\'Remove action \' + (i + 1) + \' from batch\'">Remove</button>',
      '      </li>',
      '    </template>',
      '  </ul>',
      '  <p x-show="batchError" role="alert" class="error-text" x-text="batchError"></p>',
      '  <button class="gm-actions__btn-submit"',
      '          @click="submitBatch()"',
      '          :disabled="submitting || batchQueue.length === 0"',
      '          :aria-busy="submitting ? \'true\' : \'false\'">',
      '    <span x-text="submitting ? \'Submitting...\' : \'Submit Batch (\' + batchQueue.length + \' actions)\'"></span>',
      '  </button>',
      '</div>',
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // Full form HTML
  // ---------------------------------------------------------------------------

  function _buildFormHtml() {
    var visibilityOptions = VISIBILITY_OPTIONS.map(function (v) {
      return '<option value="' + _esc(v.value) + '">' + _esc(v.label) + '</option>';
    }).join("");

    return [
      '<div id="gm-actions-root" x-data="gmActionsData" class="gm-actions">',

      // Title row
      '<hgroup>',
      '  <h2>GM Direct Actions</h2>',
      '  <p>Apply game state changes directly, bypassing the proposal workflow.</p>',
      '</hgroup>',

      // Batch mode toggle
      '<div class="gm-actions__batch-toggle">',
      '  <label>',
      '    <input type="checkbox" x-model="batchMode" />',
      '    Batch Mode — queue multiple actions, submit together',
      '  </label>',
      '</div>',

      // Batch queue (shown when in batch mode and queue is non-empty)
      _buildBatchQueueHtml(),

      '<hr />',

      // Action type selector
      _buildTypeSelectHtml(),

      // Target picker section (only when a type is selected)
      '<div x-show="selectedType" class="gm-actions__section">',
      '  <h3>Target</h3>',
      _buildTargetPickerHtml(),
      '</div>',

      // Changes section — one fieldset per type (x-show controls visibility)
      '<div x-show="selectedType" class="gm-actions__section">',
      '  <h3>Changes</h3>',
      _buildModifyCharacterHtml(),
      _buildAwardXpHtml(),
      _buildCreateBondHtml(),
      _buildModifyBondHtml(),
      _buildRetireBondHtml(),
      _buildCreateTraitHtml(),
      _buildModifyTraitHtml(),
      _buildRetireTraitHtml(),
      _buildCreateEffectHtml(),
      _buildModifyEffectHtml(),
      _buildRetireEffectHtml(),
      _buildModifyGroupHtml(),
      _buildModifyLocationHtml(),
      _buildModifyClockHtml(),
      '</div>',

      // Narrative + visibility (all types)
      '<div x-show="selectedType" class="gm-actions__section">',
      '  <h3>Narrative &amp; Metadata</h3>',
      '  <label for="gm-narrative">Narrative <small>(optional — appears in event log)</small></label>',
      '  <textarea id="gm-narrative" rows="3"',
      '            x-model="narrative"',
      '            placeholder="Describe what happened..."></textarea>',
      '  <label for="gm-visibility">Visibility Override <small>(optional)</small></label>',
      '  <select id="gm-visibility" x-model="visibility">',
      visibilityOptions,
      '  </select>',
      '</div>',

      // Submit button (single mode) or Add to Batch (batch mode)
      '<div x-show="selectedType" class="gm-actions__submit-row">',
      '  <template x-if="!batchMode">',
      '    <button class="gm-actions__btn-submit"',
      '            @click="submit()"',
      '            :disabled="submitting"',
      '            :aria-busy="submitting ? \'true\' : \'false\'">',
      '      <span x-text="submitting ? \'Applying...\' : \'Apply Action\'"></span>',
      '    </button>',
      '  </template>',
      '  <template x-if="batchMode">',
      '    <button class="gm-actions__btn-secondary"',
      '            @click="addToBatch()"',
      '            :disabled="submitting">',
      '      Add to Batch',
      '    </button>',
      '  </template>',
      '</div>',

      '</div>', // end #gm-actions-root
    ].join("\n");
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  return function render() {
    var el = document.getElementById("view");
    if (!el) return;

    // Guard: GM only
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      var store = Alpine.store("app");
      if (!store.isGm()) {
        el.innerHTML =
          '<div class="gm-actions">' +
            '<p class="error-text" role="alert">Access denied — GM only.</p>' +
          '</div>';
        return;
      }
    }

    el.innerHTML = _buildFormHtml();

    // Register Alpine data component
    if (typeof Alpine !== "undefined") {
      Alpine.data("gmActionsData", _makeData);

      var root = document.getElementById("gm-actions-root");
      if (root) {
        Alpine.initTree(root);

        // Load reference lists once Alpine has initialised the tree
        // so that the data object is available
        var _tryLoadLists = function () {
          if (root._x_dataStack && root._x_dataStack[0] && root._x_dataStack[0]._loadLists) {
            root._x_dataStack[0]._loadLists();
          } else {
            setTimeout(_tryLoadLists, 50);
          }
        };
        _tryLoadLists();
      }
    }
  };
})();
