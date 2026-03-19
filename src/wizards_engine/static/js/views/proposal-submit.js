/* Wizards Engine — Proposal Submission view (3-step flow)
 *
 * Route:  #/proposals/new
 *
 * Step 1 — Choose Action Type
 *   Displays all action types grouped by category. use_skill, use_magic,
 *   and charge_magic are enabled. Selecting one advances to Step 2.
 *
 * Step 2 — Fill Details
 *   use_skill: Skill dropdown, optional modifier pickers, Plot spend, narrative.
 *   use_magic: Magic stat selector, sacrifice builder, optional modifiers, narrative.
 *   charge_magic: Effect selector, magic stat selector, sacrifice builder,
 *                 optional modifiers, narrative.
 *   Fetches GET /api/v1/characters/{id} on mount to populate pickers.
 *
 * Step 3 — Preview & Submit
 *   Summary of all selections. "Submit" posts to POST /api/v1/proposals
 *   and redirects to #/proposals on success.
 *
 * State persists across steps via the shared Alpine x-data object.
 * Back navigation does NOT lose form state.
 *
 * Registers as: window.views.proposalSubmit
 * Called by:    router.js route table entry for "/proposals/new"
 */

window.views = window.views || {};

window.views.proposalSubmit = (function () {
  // -------------------------------------------------------------------------
  // Constants
  // -------------------------------------------------------------------------

  var STEP_LABELS = ["Choose Action", "Fill Details", "Review"];

  var SKILLS = [
    { value: "awareness",   label: "Awareness"   },
    { value: "composure",   label: "Composure"   },
    { value: "influence",   label: "Influence"   },
    { value: "finesse",     label: "Finesse"     },
    { value: "speed",       label: "Speed"       },
    { value: "power",       label: "Power"       },
    { value: "knowledge",   label: "Knowledge"   },
    { value: "technology",  label: "Technology"  },
  ];

  // The 5 canonical magic stats (lowercase, matching backend CANONICAL_MAGIC_STATS).
  var MAGIC_STATS = [
    { value: "being",      label: "Being"      },
    { value: "wyrding",    label: "Wyrding"    },
    { value: "summoning",  label: "Summoning"  },
    { value: "enchanting", label: "Enchanting" },
    { value: "dreaming",   label: "Dreaming"   },
  ];

  // Action type definitions used to render Step 1.
  var ACTION_GROUPS = [
    {
      label: "Session Actions",
      actions: [
        { type: "use_skill",     label: "Use Skill",    desc: "Roll skill + modifiers",   enabled: true  },
        { type: "use_magic",     label: "Use Magic",    desc: "Freeform magic action",     enabled: true  },
        { type: "charge_magic",  label: "Charge Magic", desc: "Recharge/boost an effect",  enabled: true  },
      ],
    },
    {
      label: "Downtime Actions",
      note: "Cost 1 Free Time each",
      actions: [
        { type: "regain_gnosis",   label: "Regain Gnosis",   desc: "Recover magical energy",    enabled: true },
        { type: "work_on_project", label: "Work on Project", desc: "Advance a Story/Arc",       enabled: true },
        { type: "rest",            label: "Rest",            desc: "Heal Stress",               enabled: true },
        { type: "new_trait",       label: "New Trait",       desc: "Replace/fill a trait slot", enabled: true },
        { type: "new_bond",        label: "New Bond",        desc: "Replace/fill a bond slot",  enabled: true },
      ],
    },
  ];

  // -------------------------------------------------------------------------
  // Shared state — persists across all three steps
  // -------------------------------------------------------------------------

  /**
   * Build the initial Alpine data object.
   * Defined as a function so each render() call starts clean.
   */
  function _makeData() {
    return {
      // Step tracking — 1, 2, or 3
      step: 1,

      // Step 1 selection
      selectedType: null,

      // Character data fetched in Step 2
      characterLoading: false,
      characterError: null,
      character: null,        // full character object from GET /api/v1/characters/:id

      // Step 2 form fields — use_skill
      selectedSkill: "",
      selectedCoreTrait: "",
      selectedRoleTrait: "",
      selectedBond: "",
      plotSpend: 0,
      narrative: "",

      // Step 2 form fields — use_magic / charge_magic
      selectedMagicStat: "",
      selectedEffectId: "",        // charge_magic only
      magicCoreTrait: "",
      magicRoleTrait: "",
      magicBond: "",

      // Sacrifice builder state (managed by sacrificeBuilder component data).
      // Merged directly into this data object for Alpine reactivity.
      sacrifices: [],
      addSacrificeType: "gnosis",
      _character: null,            // kept in sync with character field below

      // Step 2 validation
      skillError: null,
      magicStatError: null,
      effectError: null,

      // Step 3 submission
      submitting: false,

      // -----------------------------------------------------------------------
      // Downtime extra state
      // -----------------------------------------------------------------------

      // work_on_project
      storiesLoading: false,
      storiesError: null,
      stories: [],           // [{id, name, status}, ...]
      selectedStoryId: "",

      // new_trait
      traitSlotType: "",         // "core_trait" or "role_trait"
      traitTemplatesLoading: false,
      traitTemplatesError: null,
      traitTemplates: [],        // [{id, name, description, type}, ...]
      selectedTemplateId: "",    // empty string = "propose new"
      proposedTraitName: "",
      proposedTraitDescription: "",
      selectedRetireTraitId: "",

      // new_bond
      bondTargetType: "",        // "character", "group", or "location"
      bondTargetsLoading: false,
      bondTargetsError: null,
      bondTargets: [],           // [{id, name}, ...]
      selectedBondTargetId: "",
      selectedRetireBondId: "",

      // narrative validation (downtime types)
      narrativeError: null,

      // -----------------------------------------------------------------------
      // Computed helpers (called as methods because Alpine v3 store plain obj)
      // -----------------------------------------------------------------------

      /**
       * List of core traits available for selection (slot_type === 'core_trait',
       * charge > 0).
       */
      coreTraits: function () {
        var active = (this.character && this.character.traits && this.character.traits.active) || [];
        return active.filter(function (t) {
          return t.slot_type === "core_trait" && t.charge > 0;
        });
      },

      /**
       * List of role traits available for selection (slot_type === 'role_trait',
       * charge > 0).
       */
      roleTraits: function () {
        var active = (this.character && this.character.traits && this.character.traits.active) || [];
        return active.filter(function (t) {
          return t.slot_type === "role_trait" && t.charge > 0;
        });
      },

      /**
       * List of bonds available for selection (slot_type contains 'bond',
       * stress > 0).
       */
      bonds: function () {
        var active = (this.character && this.character.bonds && this.character.bonds.active) || [];
        return active.filter(function (b) {
          return b.slot_type && b.slot_type.indexOf("bond") !== -1 && b.stress > 0;
        });
      },

      /**
       * The current Plot meter value (upper bound for plotSpend).
       * plot is a top-level field on CharacterDetailResponse.
       */
      maxPlot: function () {
        return (this.character && this.character.plot) || 0;
      },

      /**
       * The skill level for the selected skill (fallback 0).
       */
      skillLevel: function () {
        if (!this.character || !this.character.skills || !this.selectedSkill) return 0;
        return this.character.skills[this.selectedSkill] || 0;
      },

      /**
       * Count of modifiers applied (+1d each).
       */
      modifierCount: function () {
        var count = 0;
        if (this.selectedCoreTrait) count++;
        if (this.selectedRoleTrait) count++;
        if (this.selectedBond)      count++;
        return count;
      },

      /**
       * Total dice pool for the preview summary.
       * Plot spend is NOT added here — Plot is guaranteed successes, not dice.
       */
      totalDice: function () {
        return this.skillLevel() + this.modifierCount();
      },

      /**
       * Label for the selected skill.
       */
      skillLabel: function () {
        for (var i = 0; i < SKILLS.length; i++) {
          if (SKILLS[i].value === this.selectedSkill) return SKILLS[i].label;
        }
        return this.selectedSkill;
      },

      /**
       * Name of the selected core trait (for preview).
       */
      coreTraitName: function () {
        if (!this.selectedCoreTrait) return "";
        var list = this.coreTraits();
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === this.selectedCoreTrait) return list[i].name;
        }
        return this.selectedCoreTrait;
      },

      /**
       * Name of the selected role trait (for preview).
       */
      roleTraitName: function () {
        if (!this.selectedRoleTrait) return "";
        var list = this.roleTraits();
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === this.selectedRoleTrait) return list[i].name;
        }
        return this.selectedRoleTrait;
      },

      /**
       * Name of the selected bond (for preview).
       */
      bondName: function () {
        if (!this.selectedBond) return "";
        var list = this.bonds();
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === this.selectedBond) return list[i].name;
        }
        return this.selectedBond;
      },

      /**
       * All active pc_bonds on the character (for retire picker in new_bond).
       * @returns {Array}
       */
      allBonds: function () {
        var active = (this.character && this.character.bonds && this.character.bonds.active) || [];
        return active.filter(function (b) {
          return b.slot_type && b.slot_type.indexOf("bond") !== -1;
        });
      },

      /**
       * Traits available to retire for new_trait (filtered by traitSlotType).
       * @returns {Array}
       */
      retirableTraits: function () {
        var active = (this.character && this.character.traits && this.character.traits.active) || [];
        var slotType = this.traitSlotType;
        return active.filter(function (t) {
          return t.slot_type === slotType;
        });
      },

      /**
       * Name of the selected story (for work_on_project preview).
       * @returns {string}
       */
      storyName: function () {
        if (!this.selectedStoryId) return "";
        for (var i = 0; i < this.stories.length; i++) {
          if (this.stories[i].id === this.selectedStoryId) return this.stories[i].name;
        }
        return this.selectedStoryId;
      },

      /**
       * Name of the selected template (for new_trait preview).
       * @returns {string}
       */
      templateName: function () {
        if (!this.selectedTemplateId) return "(propose new)";
        for (var i = 0; i < this.traitTemplates.length; i++) {
          if (this.traitTemplates[i].id === this.selectedTemplateId) {
            return this.traitTemplates[i].name;
          }
        }
        return this.selectedTemplateId;
      },

      /**
       * Name of the selected bond target (for new_bond preview).
       * @returns {string}
       */
      bondTargetName: function () {
        if (!this.selectedBondTargetId) return "";
        for (var i = 0; i < this.bondTargets.length; i++) {
          if (this.bondTargets[i].id === this.selectedBondTargetId) {
            return this.bondTargets[i].name;
          }
        }
        return this.selectedBondTargetId;
      },

      /**
       * Name of the selected bond to retire (for new_bond preview).
       * @returns {string}
       */
      retireBondName: function () {
        if (!this.selectedRetireBondId) return "";
        var list = this.allBonds();
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === this.selectedRetireBondId) return list[i].name;
        }
        return this.selectedRetireBondId;
      },

      /**
       * Name of the trait to retire (for new_trait preview).
       * @returns {string}
       */
      retireTraitName: function () {
        if (!this.selectedRetireTraitId) return "";
        var list = this.retirableTraits();
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === this.selectedRetireTraitId) return list[i].name;
        }
        return this.selectedRetireTraitId;
      },

      // -----------------------------------------------------------------------
      // Magic helpers
      // -----------------------------------------------------------------------

      /**
       * Label for the selected magic stat (for preview).
       * @returns {string}
       */
      magicStatLabel: function () {
        for (var i = 0; i < MAGIC_STATS.length; i++) {
          if (MAGIC_STATS[i].value === this.selectedMagicStat) return MAGIC_STATS[i].label;
        }
        return this.selectedMagicStat;
      },

      /**
       * Active magic effects that can be targeted by charge_magic.
       * Only "charged" and "permanent" effects are eligible.
       * @returns {Array}
       */
      chargeableEffects: function () {
        var active = (this.character && this.character.magic_effects && this.character.magic_effects.active) || [];
        return active.filter(function (e) {
          return e.effect_type === "charged" || e.effect_type === "permanent";
        });
      },

      /**
       * Name of the selected effect (for preview).
       * @returns {string}
       */
      selectedEffectName: function () {
        if (!this.selectedEffectId) return "";
        var list = this.chargeableEffects();
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === this.selectedEffectId) return list[i].name;
        }
        return this.selectedEffectId;
      },

      /**
       * Running Gnosis-equivalent total from all sacrifice entries.
       * Delegates to the sacrifice builder's logic inline.
       * @returns {number}
       */
      totalGnosisEquiv: function () {
        var total = 0;
        for (var i = 0; i < this.sacrifices.length; i++) {
          var entry = this.sacrifices[i];
          switch (entry.type) {
            case "gnosis":
              total += Math.max(0, parseInt(entry.amount, 10) || 0);
              break;
            case "stress":
              total += Math.max(0, parseInt(entry.amount, 10) || 0) * 2;
              break;
            case "free_time":
              total += Math.max(0, parseInt(entry.amount, 10) || 0) * 3;
              break;
            case "bond":
            case "trait":
              total += entry.target_id ? 10 : 0;
              break;
            // "other" contributes 0 (GM assigns value)
          }
        }
        return total;
      },

      /**
       * True if any sacrifice entry is of type "other".
       * @returns {boolean}
       */
      hasOther: function () {
        for (var i = 0; i < this.sacrifices.length; i++) {
          if (this.sacrifices[i].type === "other") return true;
        }
        return false;
      },

      /**
       * List of active bonds for the magic modifier picker.
       * (Same data as bonds() but aliased for clarity.)
       * @returns {Array}
       */
      magicBonds: function () {
        return this.bonds();
      },

      /**
       * List of active core traits for the magic modifier picker.
       * @returns {Array}
       */
      magicCoreTraits: function () {
        return this.coreTraits();
      },

      /**
       * List of active role traits for the magic modifier picker.
       * @returns {Array}
       */
      magicRoleTraits: function () {
        return this.roleTraits();
      },

      /**
       * Name of the selected magic core trait (for preview).
       * @returns {string}
       */
      magicCoreTraitName: function () {
        if (!this.magicCoreTrait) return "";
        var list = this.magicCoreTraits();
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === this.magicCoreTrait) return list[i].name;
        }
        return this.magicCoreTrait;
      },

      /**
       * Name of the selected magic role trait (for preview).
       * @returns {string}
       */
      magicRoleTraitName: function () {
        if (!this.magicRoleTrait) return "";
        var list = this.magicRoleTraits();
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === this.magicRoleTrait) return list[i].name;
        }
        return this.magicRoleTrait;
      },

      /**
       * Name of the selected magic bond modifier (for preview).
       * @returns {string}
       */
      magicBondName: function () {
        if (!this.magicBond) return "";
        var list = this.magicBonds();
        for (var i = 0; i < list.length; i++) {
          if (list[i].id === this.magicBond) return list[i].name;
        }
        return this.magicBond;
      },

      /**
       * Add a sacrifice entry of the currently-selected type.
       * Mirrors window.components.sacrificeBuilder logic for Alpine reactivity.
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
       * Serialise the sacrifice list to the API shape.
       * @returns {Array}
       */
      _toApiSacrificeList: function () {
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

      // -----------------------------------------------------------------------
      // Step navigation
      // -----------------------------------------------------------------------

      /**
       * Advance to Step 2 after choosing an action type.
       * @param {string} type — action type key, e.g. 'use_skill'
       */
      selectType: function (type) {
        this.selectedType = type;
        this.step = 2;
        this._fetchCharacter();
        // work_on_project needs the stories list up front
        if (type === "work_on_project") {
          this._fetchStories();
        }
      },

      /**
       * Validate Step 2 and advance to Step 3 (preview).
       */
      goToPreview: function () {
        // use_skill validation
        if (this.selectedType === "use_skill") {
          if (!this.selectedSkill) {
            this.skillError = "Please select a skill before continuing.";
            return;
          }
          this.skillError = null;
        }

        // use_magic / charge_magic validation
        if (this.selectedType === "use_magic" || this.selectedType === "charge_magic") {
          this.magicStatError = null;
          this.effectError = null;

          if (!this.selectedMagicStat) {
            this.magicStatError = "Please select a magic stat before continuing.";
            return;
          }
          if (this.selectedType === "charge_magic" && !this.selectedEffectId) {
            this.effectError = "Please select an effect to charge before continuing.";
            return;
          }
        }

        // All downtime types require a non-empty narrative
        var downtimeTypes = {
          regain_gnosis: true, work_on_project: true,
          rest: true, new_trait: true, new_bond: true,
        };
        if (downtimeTypes[this.selectedType]) {
          if (!this.narrative.trim()) {
            this.narrativeError = "Narrative is required for downtime actions.";
            return;
          }
          this.narrativeError = null;
        }

        // work_on_project: story required
        if (this.selectedType === "work_on_project" && !this.selectedStoryId) {
          this.narrativeError = "Please select a story before continuing.";
          return;
        }

        // new_trait: slot type + template or name required
        if (this.selectedType === "new_trait") {
          if (!this.traitSlotType) {
            this.narrativeError = "Please select a slot type before continuing.";
            return;
          }
          if (!this.selectedTemplateId && !this.proposedTraitName.trim()) {
            this.narrativeError = "Please select a template or enter a trait name before continuing.";
            return;
          }
        }

        // new_bond: target type + id required
        if (this.selectedType === "new_bond") {
          if (!this.bondTargetType || !this.selectedBondTargetId) {
            this.narrativeError = "Please select a bond target before continuing.";
            return;
          }
        }

        this.step = 3;
      },

      /**
       * Navigate back one step without losing form state.
       */
      goBack: function () {
        if (this.step > 1) {
          this.step--;
        }
      },

      // -----------------------------------------------------------------------
      // Data fetching
      // -----------------------------------------------------------------------

      /**
       * Fetch the character's current state from the API to populate
       * modifier pickers and current meter values.
       */
      _fetchCharacter: function () {
        var self = this;
        var characterId = null;
        if (typeof Alpine !== "undefined" && Alpine.store("app")) {
          characterId = Alpine.store("app").character_id;
        }
        if (!characterId) {
          self.characterError = "No linked character found. Contact your GM.";
          return;
        }

        self.characterLoading = true;
        self.characterError = null;

        api
          .get("/api/v1/characters/" + characterId)
          .then(function (data) {
            self.character = data;
            self._character = data;  // keep sacrifice builder reference in sync
            // Clamp plotSpend to the actual available plot
            var maxP = self.maxPlot();
            if (parseInt(self.plotSpend, 10) > maxP) {
              self.plotSpend = maxP;
            }
          })
          .catch(function (err) {
            self.characterError =
              (err && err.message) || "Could not load character data.";
          })
          .finally(function () {
            self.characterLoading = false;
          });
      },

      /**
       * Fetch active stories for the work_on_project picker.
       */
      _fetchStories: function () {
        var self = this;
        self.storiesLoading = true;
        self.storiesError = null;

        api
          .get("/api/v1/stories?status=active&limit=100")
          .then(function (data) {
            self.stories = (data && data.items) || [];
          })
          .catch(function (err) {
            self.storiesError = (err && err.message) || "Could not load stories.";
          })
          .finally(function () {
            self.storiesLoading = false;
          });
      },

      /**
       * Fetch trait templates for the new_trait picker.
       * Called when the slot type selector changes.
       * @param {string} slotType — "core_trait" or "role_trait"
       */
      _fetchTraitTemplates: function (slotType) {
        var self = this;
        // Convert "core_trait" to "core", "role_trait" to "role" for the API
        var apiType = slotType === "core_trait" ? "core" : "role";

        self.traitTemplatesLoading = true;
        self.traitTemplatesError = null;
        self.traitTemplates = [];
        self.selectedTemplateId = "";
        self.selectedRetireTraitId = "";

        api
          .get("/api/v1/trait-templates?type=" + apiType + "&limit=100")
          .then(function (data) {
            self.traitTemplates = (data && data.items) || [];
          })
          .catch(function (err) {
            self.traitTemplatesError =
              (err && err.message) || "Could not load trait templates.";
          })
          .finally(function () {
            self.traitTemplatesLoading = false;
          });
      },

      /**
       * Fetch bond targets (characters, groups, or locations) for new_bond.
       * Called when the target type selector changes.
       * @param {string} targetType — "character", "group", or "location"
       */
      _fetchBondTargets: function (targetType) {
        var self = this;
        self.bondTargetsLoading = true;
        self.bondTargetsError = null;
        self.bondTargets = [];
        self.selectedBondTargetId = "";

        var url;
        if (targetType === "character") {
          url = "/api/v1/characters?limit=100";
        } else if (targetType === "group") {
          url = "/api/v1/groups?limit=100";
        } else {
          url = "/api/v1/locations?limit=100";
        }

        api
          .get(url)
          .then(function (data) {
            self.bondTargets = (data && data.items) || [];
          })
          .catch(function (err) {
            self.bondTargetsError = (err && err.message) || "Could not load targets.";
          })
          .finally(function () {
            self.bondTargetsLoading = false;
          });
      },

      // -----------------------------------------------------------------------
      // Submission
      // -----------------------------------------------------------------------

      /**
       * Build and submit the proposal to the API.
       */
      submit: function () {
        var self = this;
        self.submitting = true;

        var characterId = null;
        if (typeof Alpine !== "undefined" && Alpine.store("app")) {
          characterId = Alpine.store("app").character_id;
        }

        var selections;
        if (self.selectedType === "use_skill") {
          selections = {
            skill: self.selectedSkill,
            modifiers: {
              core_trait_id: self.selectedCoreTrait || null,
              role_trait_id: self.selectedRoleTrait || null,
              bond_id:       self.selectedBond       || null,
            },
            plot_spend: parseInt(self.plotSpend, 10) || 0,
          };
        } else if (self.selectedType === "use_magic") {
          selections = {
            suggested_stat: self.selectedMagicStat,
            sacrifice:      self._toApiSacrificeList(),
            modifiers: {
              core_trait_id: self.magicCoreTrait || null,
              role_trait_id: self.magicRoleTrait || null,
              bond_id:       self.magicBond      || null,
            },
          };
        } else if (self.selectedType === "charge_magic") {
          selections = {
            effect_id:      self.selectedEffectId,
            suggested_stat: self.selectedMagicStat,
            sacrifice:      self._toApiSacrificeList(),
            modifiers: {
              core_trait_id: self.magicCoreTrait || null,
              role_trait_id: self.magicRoleTrait || null,
              bond_id:       self.magicBond      || null,
            },
          };
        } else if (self.selectedType === "regain_gnosis" || self.selectedType === "rest") {
          selections = {
            modifiers: {
              core_trait_id: self.selectedCoreTrait || null,
              role_trait_id: self.selectedRoleTrait || null,
              bond_id:       self.selectedBond       || null,
            },
          };
        } else if (self.selectedType === "work_on_project") {
          selections = {
            story_id:   self.selectedStoryId,
            // The service also requires entry_text in selections (narrative supplies this)
            entry_text: self.narrative.trim(),
          };
        } else if (self.selectedType === "new_trait") {
          selections = {
            slot_type:            self.traitSlotType,
            template_id:          self.selectedTemplateId            || null,
            proposed_name:        self.proposedTraitName.trim()       || null,
            proposed_description: self.proposedTraitDescription.trim() || null,
            retire_trait_id:      self.selectedRetireTraitId          || null,
          };
        } else if (self.selectedType === "new_bond") {
          selections = {
            target_type:    self.bondTargetType,
            target_id:      self.selectedBondTargetId,
            retire_bond_id: self.selectedRetireBondId || null,
          };
        } else {
          selections = {};
        }

        var payload = {
          character_id: characterId,
          action_type: self.selectedType,
          selections: selections,
          narrative: self.narrative.trim() || null,
        };

        api
          .post("/api/v1/proposals", payload)
          .then(function () {
            // Success — dispatch a friendly notice via the existing toast system
            document.dispatchEvent(new CustomEvent("api:success", { detail: { message: "Proposal submitted!" } }));
            window.location.hash = "#/proposals";
          })
          .catch(function () {
            // api.js already shows the error toast; just re-enable the button
            self.submitting = false;
          });
      },
    };
  }

  // -------------------------------------------------------------------------
  // HTML template builders
  // -------------------------------------------------------------------------

  /**
   * Build the Step 1 HTML — action type selector.
   */
  function _buildStep1Html() {
    var html = [];

    for (var g = 0; g < ACTION_GROUPS.length; g++) {
      var group = ACTION_GROUPS[g];
      html.push('<section class="proposal-group">');
      html.push('<h3 class="proposal-group__heading">' + _esc(group.label) + '</h3>');
      if (group.note) {
        html.push('<p class="proposal-group__note">' + _esc(group.note) + '</p>');
      }
      html.push('<ul class="proposal-action-list">');

      for (var a = 0; a < group.actions.length; a++) {
        var action = group.actions[a];
        if (action.enabled) {
          html.push(
            '<li>' +
            '<button class="proposal-action proposal-action--enabled"' +
            ' @click="selectType(\'' + action.type + '\')"' +
            ' aria-label="' + _esc(action.label) + ': ' + _esc(action.desc) + '">' +
            '<span class="proposal-action__label">' + _esc(action.label) + '</span>' +
            '<span class="proposal-action__desc">' + _esc(action.desc) + '</span>' +
            '</button>' +
            '</li>'
          );
        } else {
          html.push(
            '<li>' +
            '<div class="proposal-action proposal-action--disabled"' +
            ' aria-disabled="true">' +
            '<span class="proposal-action__label">' + _esc(action.label) + '</span>' +
            '<span class="proposal-action__desc">' + _esc(action.desc) + '</span>' +
            '<span class="proposal-action__soon">(coming soon)</span>' +
            '</div>' +
            '</li>'
          );
        }
      }

      html.push('</ul>');
      html.push('</section>');
    }

    return html.join("\n");
  }

  /**
   * Build Step 2 HTML — use_skill detail form.
   * Wrapped in x-show so it only appears when selectedType === 'use_skill'.
   */
  function _buildStep2UseSkillHtml() {
    var skillOptions = SKILLS.map(function (s) {
      return '<option value="' + _esc(s.value) + '">' + _esc(s.label) + '</option>';
    }).join("");

    return [
      '<form id="proposal-details-form"',
      '      x-show="selectedType === \'use_skill\'"',
      '      novalidate',
      '      @submit.prevent="goToPreview()">',

      '  <label for="skill-select">Skill <span aria-hidden="true">*</span></label>',
      '  <select id="skill-select" name="skill" x-model="selectedSkill" required',
      '          :aria-invalid="skillError ? \'true\' : \'false\'">',
      '    <option value="" disabled>Select a skill...</option>',
      skillOptions,
      '  </select>',
      '  <p x-show="skillError" role="alert" class="error-text" x-text="skillError"></p>',

      '  <fieldset class="proposal-modifiers">',
      '    <legend>Modifiers <small>(optional — max 1 each, +1d)</small></legend>',

      '    <label for="core-trait-select">Core Trait</label>',
      '    <select id="core-trait-select" name="core_trait" x-model="selectedCoreTrait">',
      '      <option value="">None</option>',
      '      <template x-for="t in coreTraits()" :key="t.id">',
      '        <option :value="t.id" x-text="t.name + \' (charge: \' + t.charge + \')\'"></option>',
      '      </template>',
      '    </select>',

      '    <label for="role-trait-select">Role Trait</label>',
      '    <select id="role-trait-select" name="role_trait" x-model="selectedRoleTrait">',
      '      <option value="">None</option>',
      '      <template x-for="t in roleTraits()" :key="t.id">',
      '        <option :value="t.id" x-text="t.name + \' (charge: \' + t.charge + \')\'"></option>',
      '      </template>',
      '    </select>',

      '    <label for="bond-select">Bond</label>',
      '    <select id="bond-select" name="bond" x-model="selectedBond">',
      '      <option value="">None</option>',
      '      <template x-for="b in bonds()" :key="b.id">',
      '        <option :value="b.id" x-text="b.label + (b.target_name ? \' (with \' + b.target_name + \', stress: \' + b.stress + \')\' : \' (stress: \' + b.stress + \')\')" ></option>',
      '      </template>',
      '    </select>',
      '  </fieldset>',

      '  <label for="plot-spend">Plot spend</label>',
      '  <input id="plot-spend" type="number" name="plot_spend"',
      '         x-model.number="plotSpend"',
      '         min="0" :max="maxPlot()"',
      '         :disabled="maxPlot() === 0"',
      '         inputmode="numeric"',
      '  />',
      '  <small x-text="\'Available: \' + maxPlot() + \' Plot\'"></small>',

      '  <label for="narrative">Narrative <small>(optional)</small></label>',
      '  <textarea id="narrative" name="narrative" rows="4"',
      '            x-model="narrative"',
      '            placeholder="Describe what your character does..."',
      '  ></textarea>',

      '  <button type="submit" class="proposal-btn-primary">Preview</button>',

      '</form>',
    ].join("\n");
  }

  /**
   * Build the shared magic stat selector used by use_magic and charge_magic.
   * @param {string} fieldId — the id attribute for the select element
   * @returns {string}
   */
  function _buildMagicStatSelectorHtml(fieldId) {
    var statOptions = MAGIC_STATS.map(function (s) {
      return '<option value="' + _esc(s.value) + '">' + _esc(s.label) + '</option>';
    }).join("");

    return [
      '  <label for="' + _esc(fieldId) + '">Magic Stat <span aria-hidden="true">*</span></label>',
      '  <select id="' + _esc(fieldId) + '" name="magic_stat" x-model="selectedMagicStat" required',
      '          :aria-invalid="magicStatError ? \'true\' : \'false\'">',
      '    <option value="" disabled>Select a magic stat...</option>',
      statOptions,
      '  </select>',
      '  <p x-show="magicStatError" role="alert" class="error-text" x-text="magicStatError"></p>',
    ].join("\n");
  }

  /**
   * Build the shared magic modifiers fieldset (core trait, role trait, bond).
   * The modifier fields are named differently from use_skill to avoid
   * Alpine model collisions.
   * @returns {string}
   */
  function _buildMagicModifiersHtml() {
    return [
      '  <fieldset class="proposal-modifiers">',
      '    <legend>Modifiers <small>(optional — max 1 each, +1d)</small></legend>',

      '    <label for="magic-core-trait-select">Core Trait</label>',
      '    <select id="magic-core-trait-select" name="magic_core_trait" x-model="magicCoreTrait">',
      '      <option value="">None</option>',
      '      <template x-for="t in magicCoreTraits()" :key="t.id">',
      '        <option :value="t.id" x-text="t.name + \' (charge: \' + t.charge + \')\'"></option>',
      '      </template>',
      '    </select>',

      '    <label for="magic-role-trait-select">Role Trait</label>',
      '    <select id="magic-role-trait-select" name="magic_role_trait" x-model="magicRoleTrait">',
      '      <option value="">None</option>',
      '      <template x-for="t in magicRoleTraits()" :key="t.id">',
      '        <option :value="t.id" x-text="t.name + \' (charge: \' + t.charge + \')\'"></option>',
      '      </template>',
      '    </select>',

      '    <label for="magic-bond-select">Bond</label>',
      '    <select id="magic-bond-select" name="magic_bond" x-model="magicBond">',
      '      <option value="">None</option>',
      '      <template x-for="b in magicBonds()" :key="b.id">',
      '        <option :value="b.id" x-text="b.label + (b.target_name ? \' (with \' + b.target_name + \')\' : \'\')"></option>',
      '      </template>',
      '    </select>',
      '  </fieldset>',
    ].join("\n");
  }

  /**
   * Build the sacrifice list builder HTML.
   * Works with sacrifices / addSacrificeType / addSacrifice() / removeSacrifice()
   * methods defined directly on the Alpine data object.
   * @returns {string}
   */
  function _buildSacrificeBuilderHtml() {
    var typeOptions = [
      { value: "gnosis",     label: "Gnosis"                   },
      { value: "stress",     label: "Stress"                   },
      { value: "free_time",  label: "Free Time"                },
      { value: "bond",       label: "Bond (destroys)"          },
      { value: "trait",      label: "Trait (destroys)"         },
      { value: "other",      label: "Other (GM assigns value)" },
    ].map(function (opt) {
      return '<option value="' + _esc(opt.value) + '">' + _esc(opt.label) + '</option>';
    }).join("");

    return [
      '  <fieldset class="sacrifice-builder">',
      '    <legend>Sacrifices</legend>',

      // Running total
      '    <div class="sacrifice-total" aria-live="polite">',
      '      <strong>Gnosis equivalent: </strong>',
      '      <span x-text="totalGnosisEquiv()"></span>',
      '      <template x-if="hasOther()">',
      '        <span> + <abbr title="GM assigns value for Other entries">?</abbr></span>',
      '      </template>',
      '      <small> (converted to sacrifice dice on submit)</small>',
      '    </div>',

      // Entry list
      '    <ul class="sacrifice-list" aria-label="Sacrifice entries">',
      '      <template x-for="(entry, index) in sacrifices" :key="index">',
      '        <li class="sacrifice-entry">',
      '          <span class="sacrifice-entry__type" x-text="entry.type.replace(\'_\', \' \')"></span>',

      // Gnosis amount
      '          <template x-if="entry.type === \'gnosis\'">',
      '            <label>Amount',
      '              <input type="number" x-model.number="entry.amount" min="0"',
      '                     inputmode="numeric"',
      '                     aria-label="Gnosis sacrifice amount" />',
      '            </label>',
      '          </template>',

      // Stress amount
      '          <template x-if="entry.type === \'stress\'">',
      '            <div>',
      '              <label>Amount',
      '                <input type="number" x-model.number="entry.amount" min="0"',
      '                       inputmode="numeric"',
      '                       aria-label="Stress sacrifice amount" />',
      '              </label>',
      '              <small class="sacrifice-stress-warn">Warning: taking Stress may trigger Trauma if near maximum.</small>',
      '            </div>',
      '          </template>',

      // Free Time amount
      '          <template x-if="entry.type === \'free_time\'">',
      '            <label>Amount',
      '              <input type="number" x-model.number="entry.amount" min="0"',
      '                     inputmode="numeric"',
      '                     aria-label="Free Time sacrifice amount" />',
      '            </label>',
      '          </template>',

      // Bond picker
      '          <template x-if="entry.type === \'bond\'">',
      '            <div>',
      '              <label>Bond',
      '                <select x-model="entry.target_id" aria-label="Select bond to sacrifice">',
      '                  <option value="">Select a bond...</option>',
      '                  <template x-for="b in bonds()" :key="b.id">',
      '                    <option :value="b.id"',
      '                            x-text="b.label + (b.target_name ? \' (with \' + b.target_name + \')\' : \'\') + \' — 10 Gnosis\'"></option>',
      '                  </template>',
      '                </select>',
      '              </label>',
      '              <small>Destroys the bond permanently.</small>',
      '            </div>',
      '          </template>',

      // Trait picker
      '          <template x-if="entry.type === \'trait\'">',
      '            <div>',
      '              <label>Trait',
      '                <select x-model="entry.target_id" aria-label="Select trait to sacrifice">',
      '                  <option value="">Select a trait...</option>',
      '                  <template x-for="t in coreTraits().concat(roleTraits())" :key="t.id">',
      '                    <option :value="t.id"',
      '                            x-text="t.name + \' (\' + t.slot_type.replace(\'_\', \' \') + \') — 10 Gnosis\'"></option>',
      '                  </template>',
      '                </select>',
      '              </label>',
      '              <small>Destroys the trait permanently.</small>',
      '            </div>',
      '          </template>',

      // Other: description + amount
      '          <template x-if="entry.type === \'other\'">',
      '            <div class="sacrifice-other-fields">',
      '              <label>Description',
      '                <input type="text" x-model="entry.description"',
      '                       placeholder="Describe what you are sacrificing..."',
      '                       aria-label="Other sacrifice description" />',
      '              </label>',
      '              <label>Estimated amount <small>(GM assigns final value)</small>',
      '                <input type="number" x-model.number="entry.amount" min="0"',
      '                       inputmode="numeric"',
      '                       aria-label="Other sacrifice estimated amount" />',
      '              </label>',
      '            </div>',
      '          </template>',

      '          <button type="button" class="sacrifice-entry__remove"',
      '                  @click="removeSacrifice(index)"',
      '                  :aria-label="\'Remove \' + entry.type.replace(\'_\', \' \') + \' sacrifice\'">',
      '            Remove',
      '          </button>',
      '        </li>',
      '      </template>',
      '      <template x-if="sacrifices.length === 0">',
      '        <li class="sacrifice-list__empty"><em>No sacrifices added yet.</em></li>',
      '      </template>',
      '    </ul>',

      // Add controls
      '    <div class="sacrifice-add">',
      '      <label for="magic-add-type">Add sacrifice</label>',
      '      <select id="magic-add-type" x-model="addSacrificeType">',
      typeOptions,
      '      </select>',
      '      <button type="button" class="sacrifice-add__btn" @click="addSacrifice()">Add</button>',
      '    </div>',
      '  </fieldset>',
    ].join("\n");
  }

  /**
   * Build Step 2 HTML — use_magic detail form.
   * Wrapped in x-show so it only appears when selectedType === 'use_magic'.
   */
  function _buildStep2UseMagicHtml() {
    return [
      '<form id="proposal-magic-form"',
      '      x-show="selectedType === \'use_magic\'"',
      '      novalidate',
      '      @submit.prevent="goToPreview()">',

      _buildMagicStatSelectorHtml("magic-stat-select"),
      _buildSacrificeBuilderHtml(),
      _buildMagicModifiersHtml(),

      '  <label for="magic-narrative">Narrative <small>(optional)</small></label>',
      '  <textarea id="magic-narrative" name="narrative" rows="4"',
      '            x-model="narrative"',
      '            placeholder="Describe the magical action..."',
      '  ></textarea>',

      '  <button type="submit" class="proposal-btn-primary">Preview</button>',
      '</form>',
    ].join("\n");
  }

  /**
   * Build Step 2 HTML — charge_magic detail form.
   * Wrapped in x-show so it only appears when selectedType === 'charge_magic'.
   */
  function _buildStep2ChargeMagicHtml() {
    return [
      '<form id="proposal-charge-magic-form"',
      '      x-show="selectedType === \'charge_magic\'"',
      '      novalidate',
      '      @submit.prevent="goToPreview()">',

      // Effect selector
      '  <label for="effect-select">Effect to charge <span aria-hidden="true">*</span></label>',
      '  <select id="effect-select" name="effect_id" x-model="selectedEffectId" required',
      '          :aria-invalid="effectError ? \'true\' : \'false\'">',
      '    <option value="" disabled>Select an effect...</option>',
      '    <template x-for="e in chargeableEffects()" :key="e.id">',
      '      <option :value="e.id"',
      '              x-text="e.name + \' (\' + e.effect_type +',
      '                (e.effect_type === \'charged\' ? \', \' + (e.charges_current || 0) + \'/\' + (e.charges_max || 0) + \' charges\' : \'\') +',
      '              \')\'">',
      '      </option>',
      '    </template>',
      '  </select>',
      '  <template x-if="chargeableEffects().length === 0">',
      '    <p class="proposal-empty-note">No chargeable effects. Only charged and permanent effects can be targeted.</p>',
      '  </template>',
      '  <p x-show="effectError" role="alert" class="error-text" x-text="effectError"></p>',

      _buildMagicStatSelectorHtml("charge-magic-stat-select"),
      _buildSacrificeBuilderHtml(),
      _buildMagicModifiersHtml(),

      '  <label for="charge-magic-narrative">Narrative <small>(optional)</small></label>',
      '  <textarea id="charge-magic-narrative" name="narrative" rows="4"',
      '            x-model="narrative"',
      '            placeholder="Describe how you are charging this effect..."',
      '  ></textarea>',

      '  <button type="submit" class="proposal-btn-primary">Preview</button>',
      '</form>',
    ].join("\n");
  }

  /**
   * Shared modifier fieldset HTML (core trait, role trait, bond selects).
   * Used by regain_gnosis and rest in addition to use_skill.
   * @param {string} idSuffix — appended to element IDs to avoid duplicates
   * @returns {string}
   */
  function _buildDowntimeModifierFieldsetHtml(idSuffix) {
    var suffix = idSuffix || "";
    return [
      '  <fieldset class="proposal-modifiers">',
      '    <legend>Modifiers <small>(optional — max 1 each, +1)</small></legend>',

      '    <label for="dt-core-trait-select' + suffix + '">Core Trait</label>',
      '    <select id="dt-core-trait-select' + suffix + '" name="core_trait" x-model="selectedCoreTrait">',
      '      <option value="">None</option>',
      '      <template x-for="t in coreTraits()" :key="t.id">',
      '        <option :value="t.id" x-text="t.name + \' (charge: \' + t.charge + \')\'"></option>',
      '      </template>',
      '    </select>',

      '    <label for="dt-role-trait-select' + suffix + '">Role Trait</label>',
      '    <select id="dt-role-trait-select' + suffix + '" name="role_trait" x-model="selectedRoleTrait">',
      '      <option value="">None</option>',
      '      <template x-for="t in roleTraits()" :key="t.id">',
      '        <option :value="t.id" x-text="t.name + \' (charge: \' + t.charge + \')\'"></option>',
      '      </template>',
      '    </select>',

      '    <label for="dt-bond-select' + suffix + '">Bond</label>',
      '    <select id="dt-bond-select' + suffix + '" name="bond" x-model="selectedBond">',
      '      <option value="">None</option>',
      '      <template x-for="b in bonds()" :key="b.id">',
      '        <option :value="b.id" x-text="b.label + (b.target_name ? \' (with \' + b.target_name + \', stress: \' + b.stress + \')\' : \' (stress: \' + b.stress + \')\')" ></option>',
      '      </template>',
      '    </select>',
      '  </fieldset>',
    ].join("\n");
  }

  /**
   * Build Step 2 HTML — regain_gnosis detail form.
   * Formula: Base 3 + lowest Magic Stat + modifier count
   * @returns {string}
   */
  function _buildStep2RegainGnosisHtml() {
    return [
      '<form id="proposal-regain-gnosis-form"',
      '      x-show="selectedType === \'regain_gnosis\'"',
      '      novalidate',
      '      @submit.prevent="goToPreview()">',

      '  <p class="proposal-formula">Formula: Base 3 + lowest Magic Stat + modifiers</p>',

      _buildDowntimeModifierFieldsetHtml("-rg"),

      '  <label for="narrative-rg">Narrative <span aria-hidden="true">*</span></label>',
      '  <textarea id="narrative-rg" name="narrative" rows="4"',
      '            x-model="narrative"',
      '            placeholder="Describe what your character does..."',
      '            required',
      '  ></textarea>',
      '  <p x-show="narrativeError" role="alert" class="error-text" x-text="narrativeError"></p>',

      '  <button type="submit" class="proposal-btn-primary">Preview</button>',

      '</form>',
    ].join("\n");
  }

  /**
   * Build Step 2 HTML — rest detail form.
   * Formula: Base 3 Stress healed + modifier count
   * @returns {string}
   */
  function _buildStep2RestHtml() {
    return [
      '<form id="proposal-rest-form"',
      '      x-show="selectedType === \'rest\'"',
      '      novalidate',
      '      @submit.prevent="goToPreview()">',

      '  <p class="proposal-formula">Formula: Base 3 Stress healed + modifiers</p>',

      _buildDowntimeModifierFieldsetHtml("-rest"),

      '  <label for="narrative-rest">Narrative <span aria-hidden="true">*</span></label>',
      '  <textarea id="narrative-rest" name="narrative" rows="4"',
      '            x-model="narrative"',
      '            placeholder="Describe what your character does..."',
      '            required',
      '  ></textarea>',
      '  <p x-show="narrativeError" role="alert" class="error-text" x-text="narrativeError"></p>',

      '  <button type="submit" class="proposal-btn-primary">Preview</button>',

      '</form>',
    ].join("\n");
  }

  /**
   * Build Step 2 HTML — work_on_project detail form.
   * Requires a story picker and a narrative that becomes the story entry text.
   * @returns {string}
   */
  function _buildStep2WorkOnProjectHtml() {
    return [
      '<form id="proposal-work-on-project-form"',
      '      x-show="selectedType === \'work_on_project\'"',
      '      novalidate',
      '      @submit.prevent="goToPreview()">',

      '  <div x-show="storiesLoading" aria-live="polite" class="proposal-loading">',
      '    Loading stories...',
      '  </div>',
      '  <div x-show="storiesError" role="alert" class="error-text" x-text="storiesError"></div>',

      '  <label for="story-select">Story <span aria-hidden="true">*</span></label>',
      '  <select id="story-select" name="story_id"',
      '          x-model="selectedStoryId"',
      '          :disabled="storiesLoading"',
      '          required>',
      '    <option value="" disabled>Select a story...</option>',
      '    <template x-for="s in stories" :key="s.id">',
      '      <option :value="s.id" x-text="s.name"></option>',
      '    </template>',
      '  </select>',
      '  <template x-if="stories.length === 0 && !storiesLoading && !storiesError">',
      '    <p class="proposal-empty-hint">No active stories found. Ask your GM to create one.</p>',
      '  </template>',

      '  <label for="narrative-wop">Narrative <span aria-hidden="true">*</span></label>',
      '  <textarea id="narrative-wop" name="narrative" rows="4"',
      '            x-model="narrative"',
      '            placeholder="Describe what your character works on..."',
      '            required',
      '  ></textarea>',
      '  <p x-show="narrativeError" role="alert" class="error-text" x-text="narrativeError"></p>',
      '  <small>This narrative will be added as an entry in the selected story on approval.</small>',

      '  <button type="submit" class="proposal-btn-primary"',
      '          :disabled="!selectedStoryId || storiesLoading">Preview</button>',

      '</form>',
    ].join("\n");
  }

  /**
   * Build Step 2 HTML — new_trait detail form.
   * Slot type picker drives template fetch and retire picker population.
   * @returns {string}
   */
  function _buildStep2NewTraitHtml() {
    return [
      '<form id="proposal-new-trait-form"',
      '      x-show="selectedType === \'new_trait\'"',
      '      novalidate',
      '      @submit.prevent="goToPreview()">',

      '  <label for="trait-slot-type">Slot Type <span aria-hidden="true">*</span></label>',
      '  <select id="trait-slot-type" name="slot_type"',
      '          x-model="traitSlotType"',
      '          @change="_fetchTraitTemplates(traitSlotType)"',
      '          required>',
      '    <option value="" disabled>Select slot type...</option>',
      '    <option value="core_trait">Core Trait</option>',
      '    <option value="role_trait">Role Trait</option>',
      '  </select>',

      '  <template x-if="traitSlotType">',
      '    <div>',

      '      <div x-show="traitTemplatesLoading" aria-live="polite" class="proposal-loading">',
      '        Loading templates...',
      '      </div>',
      '      <div x-show="traitTemplatesError" role="alert" class="error-text" x-text="traitTemplatesError"></div>',

      '      <label for="template-select">Template <small>(or propose new below)</small></label>',
      '      <select id="template-select" name="template_id"',
      '              x-model="selectedTemplateId"',
      '              :disabled="traitTemplatesLoading">',
      '        <option value="">Propose new (no template)</option>',
      '        <template x-for="t in traitTemplates" :key="t.id">',
      '          <option :value="t.id" x-text="t.name"></option>',
      '        </template>',
      '      </select>',

      '      <template x-if="!selectedTemplateId">',
      '        <div class="proposal-propose-new">',
      '          <label for="proposed-trait-name">Trait Name <span aria-hidden="true">*</span></label>',
      '          <input id="proposed-trait-name" type="text" name="proposed_name"',
      '                 x-model="proposedTraitName"',
      '                 placeholder="Enter a name for the new trait..."',
      '                 required />',

      '          <label for="proposed-trait-desc">Trait Description <span aria-hidden="true">*</span></label>',
      '          <textarea id="proposed-trait-desc" name="proposed_description" rows="3"',
      '                    x-model="proposedTraitDescription"',
      '                    placeholder="Describe what this trait does..."',
      '                    required></textarea>',
      '        </div>',
      '      </template>',

      '      <template x-if="retirableTraits().length > 0">',
      '        <div>',
      '          <label for="retire-trait-select">Retire Existing Trait <small>(required if at slot limit)</small></label>',
      '          <select id="retire-trait-select" name="retire_trait_id"',
      '                  x-model="selectedRetireTraitId">',
      '            <option value="">None</option>',
      '            <template x-for="t in retirableTraits()" :key="t.id">',
      '              <option :value="t.id" x-text="t.name"></option>',
      '            </template>',
      '          </select>',
      '        </div>',
      '      </template>',

      '    </div>',
      '  </template>',

      '  <label for="narrative-nt">Narrative <span aria-hidden="true">*</span></label>',
      '  <textarea id="narrative-nt" name="narrative" rows="4"',
      '            x-model="narrative"',
      '            placeholder="Describe what your character does..."',
      '            required',
      '  ></textarea>',
      '  <p x-show="narrativeError" role="alert" class="error-text" x-text="narrativeError"></p>',

      '  <button type="submit" class="proposal-btn-primary"',
      '          :disabled="!traitSlotType || (!selectedTemplateId && !proposedTraitName.trim())">Preview</button>',

      '</form>',
    ].join("\n");
  }

  /**
   * Build Step 2 HTML — new_bond detail form.
   * Target type picker drives target list fetch; all bonds shown for retire.
   * @returns {string}
   */
  function _buildStep2NewBondHtml() {
    return [
      '<form id="proposal-new-bond-form"',
      '      x-show="selectedType === \'new_bond\'"',
      '      novalidate',
      '      @submit.prevent="goToPreview()">',

      '  <label for="bond-target-type">Bond With <span aria-hidden="true">*</span></label>',
      '  <select id="bond-target-type" name="target_type"',
      '          x-model="bondTargetType"',
      '          @change="_fetchBondTargets(bondTargetType)"',
      '          required>',
      '    <option value="" disabled>Select target type...</option>',
      '    <option value="character">Character</option>',
      '    <option value="group">Group</option>',
      '    <option value="location">Location</option>',
      '  </select>',

      '  <template x-if="bondTargetType">',
      '    <div>',

      '      <div x-show="bondTargetsLoading" aria-live="polite" class="proposal-loading">',
      '        Loading targets...',
      '      </div>',
      '      <div x-show="bondTargetsError" role="alert" class="error-text" x-text="bondTargetsError"></div>',

      '      <label for="bond-target-select">',
      '        <span x-text="bondTargetType === \'character\' ? \'Character\' : bondTargetType === \'group\' ? \'Group\' : \'Location\'"></span>',
      '        <span aria-hidden="true"> *</span>',
      '      </label>',
      '      <select id="bond-target-select" name="target_id"',
      '              x-model="selectedBondTargetId"',
      '              :disabled="bondTargetsLoading"',
      '              required>',
      '        <option value="" disabled>Select target...</option>',
      '        <template x-for="t in bondTargets" :key="t.id">',
      '          <option :value="t.id" x-text="t.name"></option>',
      '        </template>',
      '      </select>',
      '      <template x-if="bondTargets.length === 0 && !bondTargetsLoading && !bondTargetsError">',
      '        <p class="proposal-empty-hint">No targets found.</p>',
      '      </template>',

      '    </div>',
      '  </template>',

      '  <template x-if="allBonds().length > 0">',
      '    <div>',
      '      <label for="retire-bond-select">Retire Existing Bond <small>(required if at bond limit)</small></label>',
      '      <select id="retire-bond-select" name="retire_bond_id"',
      '              x-model="selectedRetireBondId">',
      '        <option value="">None</option>',
      '        <template x-for="b in allBonds()" :key="b.id">',
      '          <option :value="b.id" x-text="b.label || b.name"></option>',
      '        </template>',
      '      </select>',
      '    </div>',
      '  </template>',

      '  <label for="narrative-nb">Narrative <span aria-hidden="true">*</span></label>',
      '  <textarea id="narrative-nb" name="narrative" rows="4"',
      '            x-model="narrative"',
      '            placeholder="Describe what your character does..."',
      '            required',
      '  ></textarea>',
      '  <p x-show="narrativeError" role="alert" class="error-text" x-text="narrativeError"></p>',

      '  <button type="submit" class="proposal-btn-primary"',
      '          :disabled="!bondTargetType || !selectedBondTargetId || bondTargetsLoading">Preview</button>',

      '</form>',
    ].join("\n");
  }

  // Builds all Step 2 form variants — only the matching type is visible via x-show.
  function _buildStep2Html() {
    return [
      '<div x-show="characterLoading" aria-live="polite" class="proposal-loading">',
      '  Loading character data...',
      '</div>',
      '<div x-show="characterError" role="alert" class="error-text" x-text="characterError"></div>',
      '<div x-show="!characterLoading && !characterError">',
      _buildStep2UseSkillHtml(),
      _buildStep2UseMagicHtml(),
      _buildStep2ChargeMagicHtml(),
      _buildStep2RegainGnosisHtml(),
      _buildStep2RestHtml(),
      _buildStep2WorkOnProjectHtml(),
      _buildStep2NewTraitHtml(),
      _buildStep2NewBondHtml(),
      '</div>',
    ].join("\n");
  }

  /**
   * Build Step 3 HTML — preview and confirm.
   * Shows different content depending on selectedType.
   */
  function _buildStep3Html() {
    return [
      // ---- use_skill summary ----
      '<template x-if="selectedType === \'use_skill\'">',
      '  <dl class="proposal-summary">',

      '    <dt>Skill</dt>',
      '    <dd x-text="skillLabel()"></dd>',

      '    <template x-if="selectedCoreTrait">',
      '      <div>',
      '        <dt>Core Trait</dt>',
      '        <dd x-text="coreTraitName() + \' (+1d)\'"></dd>',
      '      </div>',
      '    </template>',

      '    <template x-if="selectedRoleTrait">',
      '      <div>',
      '        <dt>Role Trait</dt>',
      '        <dd x-text="roleTraitName() + \' (+1d)\'"></dd>',
      '      </div>',
      '    </template>',

      '    <template x-if="selectedBond">',
      '      <div>',
      '        <dt>Bond</dt>',
      '        <dd x-text="bondName() + \' (+1d)\'"></dd>',
      '      </div>',
      '    </template>',

      '    <template x-if="plotSpend > 0">',
      '      <div>',
      '        <dt>Plot Spend</dt>',
      '        <dd x-text="plotSpend + \' Plot (guaranteed successes)\'"></dd>',
      '      </div>',
      '    </template>',

      '    <template x-if="narrative.trim()">',
      '      <div>',
      '        <dt>Narrative</dt>',
      '        <dd class="proposal-summary__narrative" x-text="narrative.trim()"></dd>',
      '      </div>',
      '    </template>',

      '  </dl>',
      '</template>',

      '<template x-if="selectedType === \'use_skill\'">',
      '  <div class="proposal-dice-pool">',
      '    <p x-text="',
      '      \'Dice pool: Base \' + skillLevel() + \'d\' +',
      '      (modifierCount() > 0 ? \' + \' + modifierCount() + \'d (modifiers)\' : \'\') +',
      '      \' = \' + totalDice() + \'d\'',
      '    "></p>',
      '    <template x-if="plotSpend > 0">',
      '      <p x-text="\'Plot: \' + plotSpend + \' guaranteed success\' + (plotSpend !== 1 ? \'es\' : \'\')"></p>',
      '    </template>',
      '  </div>',
      '</template>',

      // ---- use_magic summary ----
      '<template x-if="selectedType === \'use_magic\'">',
      '  <dl class="proposal-summary">',

      '    <dt>Magic Stat</dt>',
      '    <dd x-text="magicStatLabel()"></dd>',

      '    <dt>Total Gnosis Equivalent</dt>',
      '    <dd>',
      '      <span x-text="totalGnosisEquiv()"></span>',
      '      <template x-if="hasOther()">',
      '        <span> + <abbr title="GM assigns value for Other entries">?</abbr></span>',
      '      </template>',
      '      <small> Gnosis equivalent</small>',
      '    </dd>',

      '    <template x-if="sacrifices.length > 0">',
      '      <div>',
      '        <dt>Sacrifice breakdown</dt>',
      '        <dd>',
      '          <ul class="proposal-summary__sacrifice-list">',
      '            <template x-for="(s, i) in sacrifices" :key="i">',
      '              <li x-text="',
      '                s.type === \'bond\'  ? (s.target_id ? \'Bond: \' + (bonds().find(function(b){return b.id===s.target_id;}) || {label: s.target_id}).label + \' (10 Gnosis)\' : \'Bond: (none selected)\') :',
      '                s.type === \'trait\' ? (s.target_id ? \'Trait: \' + (coreTraits().concat(roleTraits()).find(function(t){return t.id===s.target_id;}) || {name: s.target_id}).name + \' (10 Gnosis)\' : \'Trait: (none selected)\') :',
      '                s.type === \'other\' ? (\'Other: \' + (s.description || \'(no description)\') + \' (GM assigns value)\') :',
      '                (s.type.replace(\'_\', \' \') + \': \' + (s.amount || 0))">',
      '              </li>',
      '            </template>',
      '          </ul>',
      '        </dd>',
      '      </div>',
      '    </template>',

      '    <template x-if="magicCoreTrait">',
      '      <div><dt>Core Trait modifier</dt><dd x-text="magicCoreTraitName() + \' (+1d)\'"></dd></div>',
      '    </template>',
      '    <template x-if="magicRoleTrait">',
      '      <div><dt>Role Trait modifier</dt><dd x-text="magicRoleTraitName() + \' (+1d)\'"></dd></div>',
      '    </template>',
      '    <template x-if="magicBond">',
      '      <div><dt>Bond modifier</dt><dd x-text="magicBondName() + \' (+1d)\'"></dd></div>',
      '    </template>',

      '    <template x-if="narrative.trim()">',
      '      <div>',
      '        <dt>Intention</dt>',
      '        <dd class="proposal-summary__narrative" x-text="narrative.trim()"></dd>',
      '      </div>',
      '    </template>',

      '  </dl>',
      '</template>',

      // ---- charge_magic summary ----
      '<template x-if="selectedType === \'charge_magic\'">',
      '  <dl class="proposal-summary">',

      '    <dt>Effect</dt>',
      '    <dd x-text="selectedEffectName()"></dd>',

      '    <dt>Magic Stat</dt>',
      '    <dd x-text="magicStatLabel()"></dd>',

      '    <dt>Total Gnosis Equivalent</dt>',
      '    <dd>',
      '      <span x-text="totalGnosisEquiv()"></span>',
      '      <template x-if="hasOther()">',
      '        <span> + <abbr title="GM assigns value for Other entries">?</abbr></span>',
      '      </template>',
      '      <small> Gnosis equivalent</small>',
      '    </dd>',

      '    <template x-if="sacrifices.length > 0">',
      '      <div>',
      '        <dt>Sacrifice breakdown</dt>',
      '        <dd>',
      '          <ul class="proposal-summary__sacrifice-list">',
      '            <template x-for="(s, i) in sacrifices" :key="i">',
      '              <li x-text="',
      '                s.type === \'bond\'  ? (s.target_id ? \'Bond: \' + (bonds().find(function(b){return b.id===s.target_id;}) || {label: s.target_id}).label + \' (10 Gnosis)\' : \'Bond: (none selected)\') :',
      '                s.type === \'trait\' ? (s.target_id ? \'Trait: \' + (coreTraits().concat(roleTraits()).find(function(t){return t.id===s.target_id;}) || {name: s.target_id}).name + \' (10 Gnosis)\' : \'Trait: (none selected)\') :',
      '                s.type === \'other\' ? (\'Other: \' + (s.description || \'(no description)\') + \' (GM assigns value)\') :',
      '                (s.type.replace(\'_\', \' \') + \': \' + (s.amount || 0))">',
      '              </li>',
      '            </template>',
      '          </ul>',
      '        </dd>',
      '      </div>',
      '    </template>',

      '    <template x-if="magicCoreTrait">',
      '      <div><dt>Core Trait modifier</dt><dd x-text="magicCoreTraitName() + \' (+1d)\'"></dd></div>',
      '    </template>',
      '    <template x-if="magicRoleTrait">',
      '      <div><dt>Role Trait modifier</dt><dd x-text="magicRoleTraitName() + \' (+1d)\'"></dd></div>',
      '    </template>',
      '    <template x-if="magicBond">',
      '      <div><dt>Bond modifier</dt><dd x-text="magicBondName() + \' (+1d)\'"></dd></div>',
      '    </template>',

      '    <template x-if="narrative.trim()">',
      '      <div>',
      '        <dt>Intention</dt>',
      '        <dd class="proposal-summary__narrative" x-text="narrative.trim()"></dd>',
      '      </div>',
      '    </template>',

      '  </dl>',
      '</template>',

      // ---- regain_gnosis summary ----
      '<template x-if="selectedType === \'regain_gnosis\'">',
      '  <div>',
      '    <dl class="proposal-summary">',
      '      <dt>Effect</dt>',
      '      <dd>Regain Gnosis — Base 3 + lowest Magic Stat<span x-text="modifierCount() > 0 ? \' + \' + modifierCount() + \' (modifiers)\' : \'\'"></span></dd>',
      '      <template x-if="selectedCoreTrait">',
      '        <div><dt>Core Trait</dt><dd x-text="coreTraitName() + \' (+1)\'"></dd></div>',
      '      </template>',
      '      <template x-if="selectedRoleTrait">',
      '        <div><dt>Role Trait</dt><dd x-text="roleTraitName() + \' (+1)\'"></dd></div>',
      '      </template>',
      '      <template x-if="selectedBond">',
      '        <div><dt>Bond</dt><dd x-text="bondName() + \' (+1)\'"></dd></div>',
      '      </template>',
      '      <dt>Narrative</dt>',
      '      <dd class="proposal-summary__narrative" x-text="narrative.trim()"></dd>',
      '    </dl>',
      '    <p class="proposal-cost-note">Cost: 1 Free Time</p>',
      '  </div>',
      '</template>',

      // ---- rest summary ----
      '<template x-if="selectedType === \'rest\'">',
      '  <div>',
      '    <dl class="proposal-summary">',
      '      <dt>Effect</dt>',
      '      <dd>Rest — Heal Base 3 Stress<span x-text="modifierCount() > 0 ? \' + \' + modifierCount() + \' (modifiers)\' : \'\'"></span></dd>',
      '      <template x-if="selectedCoreTrait">',
      '        <div><dt>Core Trait</dt><dd x-text="coreTraitName() + \' (+1)\'"></dd></div>',
      '      </template>',
      '      <template x-if="selectedRoleTrait">',
      '        <div><dt>Role Trait</dt><dd x-text="roleTraitName() + \' (+1)\'"></dd></div>',
      '      </template>',
      '      <template x-if="selectedBond">',
      '        <div><dt>Bond</dt><dd x-text="bondName() + \' (+1)\'"></dd></div>',
      '      </template>',
      '      <dt>Narrative</dt>',
      '      <dd class="proposal-summary__narrative" x-text="narrative.trim()"></dd>',
      '    </dl>',
      '    <p class="proposal-cost-note">Cost: 1 Free Time</p>',
      '  </div>',
      '</template>',

      // ---- work_on_project summary ----
      '<template x-if="selectedType === \'work_on_project\'">',
      '  <div>',
      '    <dl class="proposal-summary">',
      '      <dt>Story</dt>',
      '      <dd x-text="storyName()"></dd>',
      '      <dt>Entry Text</dt>',
      '      <dd class="proposal-summary__narrative" x-text="narrative.trim()"></dd>',
      '    </dl>',
      '    <p class="proposal-cost-note">Cost: 1 Free Time. Narrative will be added as a story entry on approval.</p>',
      '  </div>',
      '</template>',

      // ---- new_trait summary ----
      '<template x-if="selectedType === \'new_trait\'">',
      '  <div>',
      '    <dl class="proposal-summary">',
      '      <dt>Slot Type</dt>',
      '      <dd x-text="traitSlotType === \'core_trait\' ? \'Core Trait\' : \'Role Trait\'"></dd>',
      '      <dt>Template</dt>',
      '      <dd x-text="templateName()"></dd>',
      '      <template x-if="!selectedTemplateId && proposedTraitName.trim()">',
      '        <div>',
      '          <dt>Proposed Name</dt>',
      '          <dd x-text="proposedTraitName.trim()"></dd>',
      '          <dt>Proposed Description</dt>',
      '          <dd x-text="proposedTraitDescription.trim()"></dd>',
      '        </div>',
      '      </template>',
      '      <template x-if="selectedRetireTraitId">',
      '        <div><dt>Retire</dt><dd x-text="retireTraitName()"></dd></div>',
      '      </template>',
      '      <dt>Narrative</dt>',
      '      <dd class="proposal-summary__narrative" x-text="narrative.trim()"></dd>',
      '    </dl>',
      '    <p class="proposal-cost-note">Cost: 1 Free Time</p>',
      '  </div>',
      '</template>',

      // ---- new_bond summary ----
      '<template x-if="selectedType === \'new_bond\'">',
      '  <div>',
      '    <dl class="proposal-summary">',
      '      <dt>Bond With</dt>',
      '      <dd x-text="bondTargetType.charAt(0).toUpperCase() + bondTargetType.slice(1)"></dd>',
      '      <dt>Target</dt>',
      '      <dd x-text="bondTargetName()"></dd>',
      '      <template x-if="selectedRetireBondId">',
      '        <div><dt>Retire Bond</dt><dd x-text="retireBondName()"></dd></div>',
      '      </template>',
      '      <dt>Narrative</dt>',
      '      <dd class="proposal-summary__narrative" x-text="narrative.trim()"></dd>',
      '    </dl>',
      '    <p class="proposal-cost-note">Cost: 1 Free Time</p>',
      '  </div>',
      '</template>',

      // ---- Submit controls (all types) ----
      '<div class="proposal-actions">',
      '  <button class="proposal-btn-secondary" @click="goBack()">Back</button>',
      '  <button class="proposal-btn-primary"',
      '          @click="submit()"',
      '          :disabled="submitting"',
      '          :aria-busy="submitting ? \'true\' : \'false\'">',
      '    <span x-text="submitting ? \'Submitting...\' : \'Submit\'"></span>',
      '  </button>',
      '</div>',
    ].join("\n");
  }

  // -------------------------------------------------------------------------
  // HTML escape helper
  // -------------------------------------------------------------------------

  /**
   * Escape a string for safe inclusion in HTML attribute values and text.
   * Delegates to window.utils.esc and additionally escapes single quotes.
   * @param {string} str
   * @returns {string}
   */
  function _esc(str) {
    return window.utils.esc(str).replace(/'/g, "&#39;");
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return function render() {
    var el = document.getElementById("view");
    if (!el) return;

    var stepIndicatorPlaceholder = '<div id="proposal-step-indicator"></div>';

    // The outer wrapper carries the x-data Alpine scope.
    // We build the initial data via JSON serialisation of simple values only;
    // the methods are attached via Alpine.data registration below.
    el.innerHTML = [
      '<div id="proposal-submit-root" x-data="proposalSubmitData">',

      stepIndicatorPlaceholder,

      '<h2 class="proposal-heading" x-text="',
      '  step === 1 ? \'New Proposal\' :',
      '  step === 2 && selectedType === \'use_skill\'       ? \'Use Skill\'       :',
      '  step === 2 && selectedType === \'use_magic\'       ? \'Use Magic\'       :',
      '  step === 2 && selectedType === \'charge_magic\'    ? \'Charge Magic\'    :',
      '  step === 2 && selectedType === \'regain_gnosis\'   ? \'Regain Gnosis\'   :',
      '  step === 2 && selectedType === \'rest\'            ? \'Rest\'            :',
      '  step === 2 && selectedType === \'work_on_project\' ? \'Work on Project\' :',
      '  step === 2 && selectedType === \'new_trait\'       ? \'New Trait\'       :',
      '  step === 2 && selectedType === \'new_bond\'        ? \'New Bond\'        :',
      '  step === 2 ? \'Fill Details\' :',
      '  \'Review\'',
      '"></h2>',

      // ---- Step 1 ----
      '<div x-show="step === 1" class="proposal-step">',
      _buildStep1Html(),
      '</div>',

      // ---- Step 2 ----
      '<div x-show="step === 2" class="proposal-step">',
      _buildStep2Html(),
      '<div class="proposal-actions" x-show="!characterLoading">',
      '  <button class="proposal-btn-secondary" @click="goBack()">Back</button>',
      '</div>',
      '</div>',

      // ---- Step 3 ----
      '<div x-show="step === 3" class="proposal-step">',
      _buildStep3Html(),
      '</div>',

      '</div>', // end #proposal-submit-root
    ].join("\n");

    // Register Alpine data component (idempotent — safe if called again)
    if (typeof Alpine !== "undefined") {
      // Alpine.data() registers a named component factory. If already
      // registered this is a no-op in practice because Alpine caches by name.
      Alpine.data("proposalSubmitData", _makeData);

      // Initialize Alpine on the newly-rendered subtree so directives are
      // processed without a full page reload.
      var root = document.getElementById("proposal-submit-root");
      if (root) {
        Alpine.initTree(root);
      }
    }

    // Inject the step indicator now that Alpine owns the root.
    // We re-render it imperatively on each step change via a MutationObserver
    // watching the heading text, but the simplest approach is to let Alpine
    // update it. We use a custom event dispatched from within Alpine instead.
    // For the initial render, inject Step 1 indicator immediately.
    _injectStepIndicator(1);

    // Listen for Alpine-driven step changes and update the indicator.
    // Alpine x-data doesn't natively emit step changes, so we use a polling
    // approach on the root element's Alpine data — or, more cleanly, we watch
    // for hashchange (since we're in a SPA). The simplest durable solution:
    // have the step indicator refresh itself whenever a step-related click fires.
    // We delegate to the root element with a data attribute approach.
    var rootEl = document.getElementById("proposal-submit-root");
    if (rootEl) {
      // Observe attribute/text changes to detect step changes
      var observer = new MutationObserver(function () {
        if (typeof Alpine !== "undefined" && rootEl._x_dataStack) {
          var data = rootEl._x_dataStack[0];
          if (data && typeof data.step === "number") {
            _injectStepIndicator(data.step);
          }
        }
      });
      observer.observe(rootEl, { subtree: true, childList: true, attributes: true });

      // Disconnect when the user navigates away
      window.addEventListener("hashchange", function _cleanup() {
        observer.disconnect();
        window.removeEventListener("hashchange", _cleanup);
      }, { once: true });
    }
  };

  // -------------------------------------------------------------------------
  // Step indicator injection helper
  // -------------------------------------------------------------------------

  /**
   * Replace the step indicator placeholder with a freshly-rendered indicator.
   * @param {number} currentStep — 1-based
   */
  function _injectStepIndicator(currentStep) {
    var placeholder = document.getElementById("proposal-step-indicator");
    if (!placeholder) return;

    placeholder.textContent = "";

    if (window.components && window.components.stepIndicator) {
      var indicator = window.components.stepIndicator.render({
        steps: STEP_LABELS,
        current: currentStep,
      });
      placeholder.appendChild(indicator);
    }
  }
})();
