/* Wizards Engine — Character Sheet view
 *
 * Routes: #/character  (player's own character)
 *         #/gm/character  (GM viewing their linked character)
 *
 * Layout
 * ------
 * Tier 1 — Always visible
 *   Character name, description snippet, edit button, resource meters,
 *   "Find Time" button (visible when plot >= 3, no-op placeholder).
 *
 * Tier 2 — Tabbed sections
 *   Traits | Bonds | Effects | Skills | Feed
 *
 * Tier 3 — Collapsible sections (collapsed by default)
 *   Magic Stats | Past / Retired | Session History
 *
 * Data
 * ----
 * Primary:  GET /api/v1/characters/{id}       (CharacterDetailResponse)
 * Feed:     GET /api/v1/characters/{id}/feed?limit=20
 * Polling:  60-second interval via store.registerPoll('character-sheet', ...)
 *
 * Registers as: window.views.character
 * Called by:    router.js entries for "/character" and "/gm/character"
 */

window.views = window.views || {};

window.views.character = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var POLL_KEY = "character-sheet";
  var POLL_INTERVAL_MS = 60000;
  var FEED_LIMIT = 20;

  // Domain maximums not present in the API response.
  var STRESS_MAX  = 9;
  var FT_MAX      = 20;
  var PLOT_MAX    = 5;
  var GNOSIS_DISPLAY_MAX = 23; // Gnosis has no hard cap; display up to 23

  // Tab identifiers
  var TABS = ["traits", "bonds", "effects", "skills", "feed"];

  var SKILL_LABELS = {
    awareness:  "Awareness",
    composure:  "Composure",
    influence:  "Influence",
    finesse:    "Finesse",
    speed:      "Speed",
    power:      "Power",
    knowledge:  "Knowledge",
    technology: "Technology",
  };

  var MAGIC_STAT_LABELS = {
    being:      "Being",
    wyrding:    "Wyrding",
    summoning:  "Summoning",
    enchanting: "Enchanting",
    dreaming:   "Dreaming",
  };

  // ---------------------------------------------------------------------------
  // Module-level state
  // ---------------------------------------------------------------------------

  /** The #view DOM element — set at render time. */
  var _viewEl = null;

  /** Whether this view is currently mounted. */
  var _mounted = false;

  /** The character ID we are displaying. */
  var _characterId = null;

  /** Latest character data from the API. */
  var _character = null;

  /**
   * True while any action POST is in flight.
   * Used to disable all action buttons during the request to prevent
   * double-tap on mobile.
   */
  var _actionInFlight = false;

  /** Active tab key ("traits", "bonds", "effects", "skills", "feed"). */
  var _activeTab = "traits";

  /** Feed state. */
  var _feedItems = [];
  var _feedNextCursor = null;
  var _feedHasMore = false;
  var _feedLoading = false;

  // ---------------------------------------------------------------------------
  // HTML helpers
  // ---------------------------------------------------------------------------

  /**
   * HTML-escape for text content. Delegates to window.utils.esc.
   * @param {*} str
   * @returns {string}
   */
  function _esc(str) {
    return window.utils.esc(str);
  }

  /**
   * Truncate a string to maxLen characters, appending ellipsis if trimmed.
   * @param {string} text
   * @param {number} maxLen
   * @returns {string}
   */
  function _snippet(text, maxLen) {
    if (!text) return "";
    var s = String(text);
    if (s.length <= maxLen) return s;
    return s.slice(0, maxLen).trimEnd() + "\u2026";
  }

  // ---------------------------------------------------------------------------
  // Tier 1 — Header & meters
  // ---------------------------------------------------------------------------

  /**
   * Build the Tier 1 header: name, description, edit button, meters,
   * and the "Find Time" placeholder button.
   *
   * @param {object} c — character data from CharacterDetailResponse
   * @returns {string} HTML
   */
  function _buildHeader(c) {
    var canEdit = false;
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      var store = Alpine.store("app");
      canEdit = store.isGm() || store.isOwner(c.id);
    }

    var editBtn = canEdit
      ? '<a href="#/character/edit"' +
        '   class="cs-edit-btn"' +
        '   aria-label="Edit character">' +
        '  Edit' +
        '</a>'
      : "";

    // "Find Time" is visible when plot >= 3
    var plotValue = Number(c.plot) || 0;
    var findTimeBtn = plotValue >= 3
      ? '<button class="cs-find-time-btn outline secondary"' +
        '        data-action="find-time">' +
        '  Find Time' +
        '</button>'
      : "";

    // Stress bar: effectiveMax marker when trauma bonds have lowered the cap
    var stressEffMax = (c.effective_stress_max !== null && c.effective_stress_max !== undefined)
      ? Number(c.effective_stress_max)
      : STRESS_MAX;

    var stressBar = window.components.meterBar.render({
      label: "Stress",
      current: Number(c.stress) || 0,
      max: STRESS_MAX,
      color: "var(--we-stress-red)",
      effectiveMax: stressEffMax < STRESS_MAX ? stressEffMax : undefined,
    });

    var ftBar = window.components.meterBar.render({
      label: "Free Time",
      current: Number(c.free_time) || 0,
      max: FT_MAX,
      color: "var(--we-ft-green)",
    });

    var plotBar = window.components.meterBar.render({
      label: "Plot",
      current: plotValue,
      max: PLOT_MAX,
      color: "var(--we-plot-amber)",
    });

    var gnosisValue = Number(c.gnosis) || 0;
    var gnosisBar = window.components.meterBar.render({
      label: "Gnosis",
      current: gnosisValue,
      max: GNOSIS_DISPLAY_MAX,
      color: "var(--we-gnosis-blue)",
    });

    var descSnippet = _snippet(c.description || "", 160);

    return (
      '<div class="cs-header">' +
        '<div class="cs-header__title-row">' +
          '<h2 class="cs-header__name">' + _esc(c.name) + '</h2>' +
          editBtn +
        '</div>' +
        (descSnippet
          ? '<p class="cs-header__desc">' + _esc(descSnippet) + '</p>'
          : '') +
        '<div class="cs-meters">' +
          stressBar +
          ftBar +
          plotBar +
          gnosisBar +
        '</div>' +
        (findTimeBtn
          ? '<div class="cs-find-time-row">' + findTimeBtn + '</div>'
          : '') +
      '</div>'
    );
  }

  // ---------------------------------------------------------------------------
  // Tier 2 — Tab bar
  // ---------------------------------------------------------------------------

  /**
   * Build the tab navigation bar.
   * @returns {string} HTML
   */
  function _buildTabBar() {
    var TAB_LABELS = {
      traits:  "Traits",
      bonds:   "Bonds",
      effects: "Effects",
      skills:  "Skills",
      feed:    "Feed",
    };

    var html = '<nav class="cs-tabs" role="tablist" aria-label="Character sheet sections">';
    for (var i = 0; i < TABS.length; i++) {
      var key = TABS[i];
      var isActive = key === _activeTab;
      html +=
        '<button class="cs-tab' + (isActive ? ' cs-tab--active' : '') + '"' +
        '        role="tab"' +
        '        aria-selected="' + (isActive ? 'true' : 'false') + '"' +
        '        data-tab="' + _esc(key) + '">' +
        _esc(TAB_LABELS[key]) +
        '</button>';
    }
    html += '</nav>';
    return html;
  }

  // ---------------------------------------------------------------------------
  // Traits tab
  // ---------------------------------------------------------------------------

  /**
   * Build the Traits tab content.
   * Active traits grouped by slot_type: core_trait, role_trait.
   *
   * @param {object} traits — { active: [...], past: [...] }
   * @returns {string} HTML
   */
  function _buildTraitsTab(traits) {
    var active = (traits && traits.active) ? traits.active : [];

    var coreTraits = active.filter(function (t) { return t.slot_type === "core_trait"; });
    var roleTraits = active.filter(function (t) { return t.slot_type === "role_trait"; });

    if (active.length === 0) {
      return '<p class="cs-empty">No active traits.</p>';
    }

    var html = "";

    if (coreTraits.length > 0) {
      html += '<section class="cs-trait-group">';
      html += '<h3 class="cs-group-heading">Core Traits</h3>';
      html += '<ul class="cs-trait-list">';
      for (var i = 0; i < coreTraits.length; i++) {
        html += _buildTraitItem(coreTraits[i]);
      }
      html += '</ul>';
      html += '</section>';
    }

    if (roleTraits.length > 0) {
      html += '<section class="cs-trait-group">';
      html += '<h3 class="cs-group-heading">Role Traits</h3>';
      html += '<ul class="cs-trait-list">';
      for (var j = 0; j < roleTraits.length; j++) {
        html += _buildTraitItem(roleTraits[j]);
      }
      html += '</ul>';
      html += '</section>';
    }

    return html;
  }

  /**
   * Build a single trait list item with ChargeDots and a Recharge button.
   * @param {object} t — CharacterTraitResponse
   * @returns {string} HTML
   */
  function _buildTraitItem(t) {
    var charge = (t.charge !== null && t.charge !== undefined) ? Number(t.charge) : 0;
    var dots = window.components.chargeDots.render({ current: charge, max: 5, variant: "trait" });

    // Recharge button: visible when charge < 5.
    var rechargeBtn = charge < 5
      ? '<button class="cs-action-btn"' +
        '        data-action="recharge-trait"' +
        '        data-trait-id="' + _esc(t.id) + '"' +
        '        data-trait-name="' + _esc(t.name) + '">' +
        'Recharge' +
        '</button>'
      : "";

    var descSnippet = _snippet(t.description || "", 120);

    return (
      '<li class="cs-trait-item">' +
        '<div class="cs-trait-item__header">' +
          '<strong class="cs-trait-item__name">' + _esc(t.name) + '</strong>' +
          dots +
        '</div>' +
        (descSnippet
          ? '<p class="cs-trait-item__desc">' + _esc(descSnippet) + '</p>'
          : '') +
        (rechargeBtn
          ? '<div class="cs-trait-item__actions">' + rechargeBtn + '</div>'
          : '') +
      '</li>'
    );
  }

  // ---------------------------------------------------------------------------
  // Bonds tab
  // ---------------------------------------------------------------------------

  /**
   * Build the Bonds tab content.
   * Active bonds; trauma bonds have a distinct visual style.
   *
   * @param {object} bonds — { active: [...], past: [...] }
   * @returns {string} HTML
   */
  function _buildBondsTab(bonds) {
    var active = (bonds && bonds.active) ? bonds.active : [];

    if (active.length === 0) {
      return '<p class="cs-empty">No active bonds.</p>';
    }

    var html = '<ul class="cs-bond-list">';
    for (var i = 0; i < active.length; i++) {
      html += _buildBondItem(active[i]);
    }
    html += '</ul>';
    return html;
  }

  /**
   * Build a single bond list item.
   * @param {object} b — BondDisplayResponse
   * @returns {string} HTML
   */
  function _buildBondItem(b) {
    var isTrauma = !!b.is_trauma;
    var isPC = b.slot_type === "pc_bond";

    var itemClass = "cs-bond-item" + (isTrauma ? " cs-bond-item--trauma" : "");

    // For PC bonds, show ChargeDots.
    // stress = current charges, stress_degradations = degradation count
    var dotsHtml = "";
    var maintainBtn = "";
    if (isPC && b.stress !== null && b.stress !== undefined) {
      var charges = Number(b.stress) || 0;
      var degradations = Number(b.stress_degradations) || 0;
      var effectiveMax = 5 - degradations;

      dotsHtml = window.components.chargeDots.render({
        current: charges,
        max: 5,
        variant: "bond",
        effectiveMax: effectiveMax < 5 ? effectiveMax : undefined,
      });

      // Maintain button: visible on non-trauma bonds when charges < effective max
      if (!isTrauma && charges < effectiveMax) {
        var targetDisplay = b.label && b.target_name
          ? b.label + " \u2014 " + b.target_name
          : b.label || b.target_name || "Bond";
        maintainBtn =
          '<button class="cs-action-btn"' +
          '        data-action="maintain-bond"' +
          '        data-bond-id="' + _esc(b.id) + '"' +
          '        data-bond-name="' + _esc(targetDisplay) + '">' +
          'Maintain' +
          '</button>';
      }
    }

    var label = b.label || "";
    var targetName = b.target_name || "";
    var displayName = label && targetName ? label + " — " + targetName
                    : label || targetName || "Unknown";

    var traumaBadge = isTrauma
      ? '<mark class="cs-trauma-badge">Trauma</mark>'
      : "";

    var descSnippet = _snippet(b.description || "", 100);

    return (
      '<li class="' + _esc(itemClass) + '">' +
        '<div class="cs-bond-item__header">' +
          '<span class="cs-bond-item__name">' + _esc(displayName) + '</span>' +
          traumaBadge +
          dotsHtml +
        '</div>' +
        (descSnippet
          ? '<p class="cs-bond-item__desc">' + _esc(descSnippet) + '</p>'
          : '') +
        (maintainBtn
          ? '<div class="cs-bond-item__actions">' + maintainBtn + '</div>'
          : '') +
      '</li>'
    );
  }

  // ---------------------------------------------------------------------------
  // Effects tab
  // ---------------------------------------------------------------------------

  /**
   * Build the Effects tab content.
   * Shows active magic effects with type badges and charge info.
   *
   * @param {object} magic_effects — { active: [...], past: [...] }
   * @returns {string} HTML
   */
  function _buildEffectsTab(magic_effects) {
    var active = (magic_effects && magic_effects.active) ? magic_effects.active : [];

    if (active.length === 0) {
      return '<p class="cs-empty">No active effects.</p>';
    }

    var html = '<ul class="cs-effect-list">';
    for (var i = 0; i < active.length; i++) {
      html += _buildEffectItem(active[i]);
    }
    html += '</ul>';
    return html;
  }

  /**
   * Build a single magic effect list item.
   * @param {object} e — MagicEffectResponse
   * @returns {string} HTML
   */
  function _buildEffectItem(e) {
    var effectType = e.effect_type || "";

    // Type badge
    var badgeLabel = effectType === "charged"   ? "Charged"
                   : effectType === "permanent" ? "Permanent"
                   : effectType === "instant"   ? "Instant"
                   : _esc(effectType);
    var badgeMod = effectType === "charged"   ? "charged"
                 : effectType === "permanent" ? "permanent"
                 : "instant";

    var badge = '<mark class="cs-effect-badge cs-effect-badge--' + badgeMod + '">' + badgeLabel + '</mark>';

    // Charges or power level display
    var chargesHtml = "";
    if (effectType === "charged" && e.charges_current !== null && e.charges_current !== undefined) {
      chargesHtml = window.components.chargeDots.render({
        current: Number(e.charges_current) || 0,
        max: Number(e.charges_max) || 5,
        variant: "trait",
      });
    } else if (effectType === "permanent") {
      chargesHtml =
        '<span class="cs-effect-power">Power ' + _esc(e.power_level) + '</span>';
    }

    // Use button: only for charged effects with at least 1 charge remaining.
    var currentCharges = (e.charges_current !== null && e.charges_current !== undefined)
      ? Number(e.charges_current) : 0;
    var useBtn = (effectType === "charged" && currentCharges > 0)
      ? '<button class="cs-action-btn"' +
        '        data-action="use-effect"' +
        '        data-effect-id="' + _esc(e.id) + '"' +
        '        data-effect-name="' + _esc(e.name) + '">' +
        'Use' +
        '</button>'
      : "";
    var retireBtn =
      '<button class="cs-action-btn cs-action-btn--secondary"' +
      '        data-action="retire-effect"' +
      '        data-effect-id="' + _esc(e.id) + '"' +
      '        data-effect-name="' + _esc(e.name) + '">' +
      'Retire' +
      '</button>';

    var descSnippet = _snippet(e.description || "", 100);

    return (
      '<li class="cs-effect-item">' +
        '<div class="cs-effect-item__header">' +
          '<strong class="cs-effect-item__name">' + _esc(e.name) + '</strong>' +
          badge +
          chargesHtml +
        '</div>' +
        (descSnippet
          ? '<p class="cs-effect-item__desc">' + _esc(descSnippet) + '</p>'
          : '') +
        '<div class="cs-effect-item__actions">' +
          useBtn +
          retireBtn +
        '</div>' +
      '</li>'
    );
  }

  // ---------------------------------------------------------------------------
  // Skills tab
  // ---------------------------------------------------------------------------

  /**
   * Build the Skills tab content.
   * @param {object} skills — dict of skill name to level
   * @returns {string} HTML
   */
  function _buildSkillsTab(skills) {
    if (!skills) {
      return '<p class="cs-empty">No skill data available.</p>';
    }

    var skillKeys = Object.keys(SKILL_LABELS);
    var html = '<ul class="cs-skill-list">';
    for (var i = 0; i < skillKeys.length; i++) {
      var key = skillKeys[i];
      var level = (skills[key] !== undefined && skills[key] !== null) ? Number(skills[key]) : 0;
      html +=
        '<li class="cs-skill-item">' +
          '<span class="cs-skill-item__name">' + _esc(SKILL_LABELS[key]) + '</span>' +
          '<span class="cs-skill-item__level">' + level + '</span>' +
        '</li>';
    }
    html += '</ul>';
    return html;
  }

  // ---------------------------------------------------------------------------
  // Feed tab
  // ---------------------------------------------------------------------------

  /**
   * Build the Feed tab content using current _feedItems state.
   * @returns {string} HTML
   */
  function _buildFeedTab() {
    if (_feedLoading && _feedItems.length === 0) {
      return '<p class="cs-loading" aria-busy="true">Loading feed...</p>';
    }

    if (_feedItems.length === 0) {
      return '<p class="cs-empty">No activity yet.</p>';
    }

    var html = '<div class="cs-feed">';

    var store = (typeof Alpine !== "undefined" && Alpine.store("app")) || {};
    var myCharId = store.character_id || null;

    for (var i = 0; i < _feedItems.length; i++) {
      var item = _feedItems[i];
      var isOwn = myCharId && item.character_id === myCharId;
      html += window.components.feedItem.render({
        item: item,
        type: item.item_type || item.type || "event",
        isOwn: !!isOwn,
      });
    }

    html += '</div>';

    if (_feedHasMore) {
      html +=
        '<div class="cs-feed-more">' +
          '<button id="cs-load-more-btn"' +
          '        class="outline secondary"' +
          '        ' + (_feedLoading ? 'aria-busy="true" disabled' : '') + '>' +
          (_feedLoading ? 'Loading...' : 'Load more') +
          '</button>' +
        '</div>';
    }

    return html;
  }

  // ---------------------------------------------------------------------------
  // Tier 3 — Collapsible sections
  // ---------------------------------------------------------------------------

  /**
   * Build Tier 3 collapsible sections: Magic Stats, Past/Retired, Session History.
   * @param {object} c — character data
   * @returns {string} HTML
   */
  function _buildTier3(c) {
    var html = '<div class="cs-tier3">';

    // --- Magic Stats ---------------------------------------------------------
    html += '<details class="cs-expandable">';
    html += '<summary class="cs-expandable__title">Magic Stats</summary>';
    html += '<div class="cs-expandable__body">';

    if (c.magic_stats) {
      html += '<ul class="cs-magic-stat-list">';
      var statKeys = Object.keys(MAGIC_STAT_LABELS);
      for (var i = 0; i < statKeys.length; i++) {
        var key = statKeys[i];
        var statBlock = c.magic_stats[key] || { level: 0, xp: 0 };
        var level = Number(statBlock.level) || 0;
        var xp    = Number(statBlock.xp)    || 0;
        html +=
          '<li class="cs-magic-stat-item">' +
            '<span class="cs-magic-stat-item__name">' + _esc(MAGIC_STAT_LABELS[key]) + '</span>' +
            '<span class="cs-magic-stat-item__level">Level ' + level + '</span>' +
            '<span class="cs-magic-stat-item__xp">XP ' + xp + '</span>' +
          '</li>';
      }
      html += '</ul>';
    } else {
      html += '<p class="cs-empty">No magic stats available.</p>';
    }

    html += '</div></details>';

    // --- Past / Retired ------------------------------------------------------
    html += '<details class="cs-expandable">';
    html += '<summary class="cs-expandable__title">Past / Retired</summary>';
    html += '<div class="cs-expandable__body">';

    var pastTraits  = (c.traits && c.traits.past)         ? c.traits.past         : [];
    var pastBonds   = (c.bonds  && c.bonds.past)          ? c.bonds.past          : [];
    var pastEffects = (c.magic_effects && c.magic_effects.past) ? c.magic_effects.past : [];
    var anyPast = pastTraits.length + pastBonds.length + pastEffects.length;

    if (!anyPast) {
      html += '<p class="cs-empty">Nothing retired yet.</p>';
    } else {
      if (pastTraits.length > 0) {
        html += '<h4 class="cs-past-heading">Traits</h4>';
        html += '<ul class="cs-past-list">';
        for (var pt = 0; pt < pastTraits.length; pt++) {
          html +=
            '<li class="cs-past-item">' +
              '<span class="cs-past-item__name">' + _esc(pastTraits[pt].name) + '</span>' +
              '<mark class="cs-past-badge">' + _esc(pastTraits[pt].slot_type === "core_trait" ? "Core" : "Role") + '</mark>' +
            '</li>';
        }
        html += '</ul>';
      }
      if (pastBonds.length > 0) {
        html += '<h4 class="cs-past-heading">Bonds</h4>';
        html += '<ul class="cs-past-list">';
        for (var pb = 0; pb < pastBonds.length; pb++) {
          var b = pastBonds[pb];
          var bDisplay = b.label && b.target_name ? b.label + " — " + b.target_name
                       : b.label || b.target_name || "Unknown";
          html +=
            '<li class="cs-past-item">' +
              '<span class="cs-past-item__name">' + _esc(bDisplay) + '</span>' +
            '</li>';
        }
        html += '</ul>';
      }
      if (pastEffects.length > 0) {
        html += '<h4 class="cs-past-heading">Effects</h4>';
        html += '<ul class="cs-past-list">';
        for (var pe = 0; pe < pastEffects.length; pe++) {
          html +=
            '<li class="cs-past-item">' +
              '<span class="cs-past-item__name">' + _esc(pastEffects[pe].name) + '</span>' +
            '</li>';
        }
        html += '</ul>';
      }
    }

    html += '</div></details>';

    // --- Session History ------------------------------------------------------
    html += '<details class="cs-expandable">';
    html += '<summary class="cs-expandable__title">Session History</summary>';
    html += '<div class="cs-expandable__body">';

    var sessionIds = c.session_ids || [];
    if (sessionIds.length === 0) {
      html += '<p class="cs-empty">No sessions attended yet.</p>';
    } else {
      html += '<p class="cs-session-count">' + sessionIds.length + ' session' + (sessionIds.length === 1 ? '' : 's') + ' attended.</p>';
    }

    html += '</div></details>';

    html += '</div>'; // cs-tier3
    return html;
  }

  // ---------------------------------------------------------------------------
  // Active tab panel content
  // ---------------------------------------------------------------------------

  /**
   * Build the content area for the currently active tab.
   * @param {object} c — character data
   * @returns {string} HTML
   */
  function _buildTabPanel(c) {
    var html = '<div class="cs-tab-panel" role="tabpanel">';

    switch (_activeTab) {
      case "traits":
        html += _buildTraitsTab(c.traits);
        break;
      case "bonds":
        html += _buildBondsTab(c.bonds);
        break;
      case "effects":
        html += _buildEffectsTab(c.magic_effects);
        break;
      case "skills":
        html += _buildSkillsTab(c.skills);
        break;
      case "feed":
        html += _buildFeedTab();
        break;
      default:
        html += _buildTraitsTab(c.traits);
    }

    html += '</div>';
    return html;
  }

  // ---------------------------------------------------------------------------
  // Action helpers
  // ---------------------------------------------------------------------------

  /**
   * Dispatch the api:success custom event so the success toast is shown.
   * @param {string} message
   */
  function _dispatchSuccess(message) {
    var event = new CustomEvent("api:success", {
      detail: { message: message || "Done." },
      bubbles: true,
    });
    document.dispatchEvent(event);
  }

  /**
   * Disable or re-enable all action buttons inside _viewEl.
   * Used to prevent double-tap during an in-flight request.
   * @param {boolean} disabled
   */
  function _setActionButtonsDisabled(disabled) {
    if (!_viewEl) return;
    var btns = _viewEl.querySelectorAll("[data-action]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].disabled = disabled;
    }
  }

  /**
   * Perform a POST action, handling the in-flight guard, then re-fetching
   * the full character data on success.
   *
   * @param {string}   url      — full API path
   * @param {object}   body     — request body
   * @param {string}   successMsg
   * @param {function} [optimistic] — called immediately before the request to
   *                                  update local state; receives no args.
   *                                  If provided, the view is re-rendered
   *                                  immediately, then re-rendered again after
   *                                  the server response.
   */
  function _doAction(url, body, successMsg, optimistic) {
    if (_actionInFlight) return;
    _actionInFlight = true;
    _setActionButtonsDisabled(true);

    // Snapshot the character data before optimistic mutations so we can
    // restore it exactly on error.
    var _snapshot = _character ? JSON.parse(JSON.stringify(_character)) : null;

    if (typeof optimistic === "function") {
      optimistic();
      _renderSheet();
    }

    api
      .post(url, body)
      .then(function () {
        if (!_mounted) return;
        _dispatchSuccess(successMsg);
        // Re-fetch the full character sheet so meters/charges are accurate
        return api.get("/api/v1/characters/" + _characterId);
      })
      .then(function (fresh) {
        if (!_mounted || !fresh) return;
        _character = fresh;
        _renderSheet();
      })
      .catch(function () {
        if (!_mounted) return;
        // Roll back optimistic changes by restoring the pre-action snapshot.
        // api.js already dispatched the error toast.
        if (_snapshot) {
          _character = _snapshot;
        }
        _renderSheet();
      })
      .finally(function () {
        _actionInFlight = false;
        // Re-enable buttons (renderSheet replaces the DOM, so this is a
        // safety net for cases where _renderSheet was not reached)
        _setActionButtonsDisabled(false);
      });
  }

  // ---------------------------------------------------------------------------
  // Individual action handlers
  // ---------------------------------------------------------------------------

  /**
   * Handle "Find Time": POST directly → refresh. No confirmation dialog.
   * The button is only rendered when plot >= 3, so tapping it always
   * succeeds (barring network error). A single tap is all that is needed.
   */
  function _onFindTime() {
    var id = _characterId;
    _doAction(
      "/api/v1/characters/" + id + "/find-time",
      {},
      "Found time! Plot -3, Free Time +1."
    );
  }

  /**
   * Handle "Recharge Trait": open narrative modal → POST → refresh.
   * @param {string} traitId   — Slot ULID (trait_instance_id)
   * @param {string} traitName — display label for the modal title
   */
  function _onRechargeTrait(traitId, traitName) {
    var id = _characterId;
    window.components.narrativeModal.show({
      title: "Recharge: " + traitName,
      required: true,
      onSubmit: function (narrative) {
        // Optimistic: set this trait's charge to 5, decrement FT by 1
        function optimistic() {
          if (!_character) return;
          var traits = (_character.traits && _character.traits.active) || [];
          for (var i = 0; i < traits.length; i++) {
            if (traits[i].id === traitId) {
              traits[i].charge = 5;
              break;
            }
          }
          if (_character.free_time !== null && _character.free_time !== undefined) {
            _character.free_time = Math.max(0, Number(_character.free_time) - 1);
          }
        }

        _doAction(
          "/api/v1/characters/" + id + "/recharge-trait",
          { trait_instance_id: traitId, narrative: narrative },
          "Trait recharged.",
          optimistic
        );
      },
    });
  }

  /**
   * Handle "Maintain Bond": open narrative modal → POST → refresh.
   * @param {string} bondId   — Slot ULID (bond_instance_id)
   * @param {string} bondName — display label for the modal title
   */
  function _onMaintainBond(bondId, bondName) {
    var id = _characterId;
    window.components.narrativeModal.show({
      title: "Maintain: " + bondName,
      required: true,
      onSubmit: function (narrative) {
        _doAction(
          "/api/v1/characters/" + id + "/maintain-bond",
          { bond_instance_id: bondId, narrative: narrative },
          "Bond maintained."
        );
      },
    });
  }

  /**
   * Handle "Use Effect": open optional narrative modal → POST → refresh.
   * @param {string} effectId   — MagicEffect ULID
   * @param {string} effectName — display label for the modal title
   */
  function _onUseEffect(effectId, effectName) {
    var id = _characterId;
    window.components.narrativeModal.show({
      title: "Use: " + effectName,
      required: false,
      onSubmit: function (narrative) {
        // Optimistic: decrement charges_current by 1
        function optimistic() {
          if (!_character) return;
          var effects = (_character.magic_effects && _character.magic_effects.active) || [];
          for (var i = 0; i < effects.length; i++) {
            if (effects[i].id === effectId) {
              if (effects[i].charges_current !== null && effects[i].charges_current !== undefined) {
                effects[i].charges_current = Math.max(0, Number(effects[i].charges_current) - 1);
              }
              break;
            }
          }
        }

        var body = {};
        if (narrative) { body.narrative = narrative; }

        _doAction(
          "/api/v1/characters/" + id + "/effects/" + effectId + "/use",
          body,
          "Effect used.",
          optimistic
        );
      },
    });
  }

  /**
   * Handle "Retire Effect": confirm → POST → refresh.
   * @param {string} effectId   — MagicEffect ULID
   * @param {string} effectName — display label for the confirm dialog
   */
  function _onRetireEffect(effectId, effectName) {
    if (!window.confirm("Retire \"" + effectName + "\"? This cannot be undone.")) return;

    var id = _characterId;
    _doAction(
      "/api/v1/characters/" + id + "/effects/" + effectId + "/retire",
      {},
      "Effect retired."
    );
  }

  // ---------------------------------------------------------------------------
  // Button wiring
  // ---------------------------------------------------------------------------

  /**
   * Attach click handlers to all [data-action] buttons rendered into _viewEl.
   * Called after every _renderSheet() call.
   */
  function _bindActionButtons() {
    if (!_viewEl) return;

    var btns = _viewEl.querySelectorAll("[data-action]");
    for (var i = 0; i < btns.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var action = btn.getAttribute("data-action");

          if (action === "find-time") {
            _onFindTime();
          } else if (action === "recharge-trait") {
            _onRechargeTrait(
              btn.getAttribute("data-trait-id"),
              btn.getAttribute("data-trait-name")
            );
          } else if (action === "maintain-bond") {
            _onMaintainBond(
              btn.getAttribute("data-bond-id"),
              btn.getAttribute("data-bond-name")
            );
          } else if (action === "use-effect") {
            _onUseEffect(
              btn.getAttribute("data-effect-id"),
              btn.getAttribute("data-effect-name")
            );
          } else if (action === "retire-effect") {
            _onRetireEffect(
              btn.getAttribute("data-effect-id"),
              btn.getAttribute("data-effect-name")
            );
          }
        });
      })(btns[i]);
    }
  }

  // ---------------------------------------------------------------------------
  // Full render
  // ---------------------------------------------------------------------------

  /**
   * Re-render the full character sheet into _viewEl.
   * Called on data load, tab switch, and poll callback.
   */
  function _renderSheet() {
    if (!_viewEl || !_mounted || !_character) return;

    var c = _character;

    var html =
      '<div class="cs-root">' +
        _buildHeader(c) +
        _buildTabBar() +
        _buildTabPanel(c) +
        _buildTier3(c) +
      '</div>';

    _viewEl.innerHTML = html;

    // Wire tab button click handlers
    var tabBtns = _viewEl.querySelectorAll(".cs-tab[data-tab]");
    for (var i = 0; i < tabBtns.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var tab = btn.getAttribute("data-tab");
          if (tab && tab !== _activeTab) {
            _activeTab = tab;
            if (_activeTab === "feed" && _feedItems.length === 0 && !_feedLoading) {
              _fetchFeed(true);
            } else {
              _renderSheet();
            }
          }
        });
      })(tabBtns[i]);
    }

    // Wire "Load more" button if present
    var loadMoreBtn = document.getElementById("cs-load-more-btn");
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", function () {
        _fetchFeed(false);
      });
    }

    // Wire action buttons (Find Time, Recharge, Maintain, Use, Retire)
    _bindActionButtons();
  }

  /**
   * Render the loading state.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="cs-root">' +
        '<hgroup>' +
          '<h2>Character Sheet</h2>' +
          '<p aria-busy="true">Loading...</p>' +
        '</hgroup>' +
      '</div>';
  }

  /**
   * Render an error state with a retry button.
   * @param {string} [message]
   */
  function _renderError(message) {
    if (!_viewEl) return;
    var msg = message || "Could not load character data.";
    _viewEl.innerHTML =
      '<div class="cs-root">' +
        '<hgroup>' +
          '<h2>Character Sheet</h2>' +
        '</hgroup>' +
        '<p class="error-text" role="alert">' + _esc(msg) + '</p>' +
        '<button id="cs-retry-btn">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("cs-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        _fetchCharacter(true);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Data fetching — character
  // ---------------------------------------------------------------------------

  /**
   * Fetch character data and re-render.
   * @param {boolean} [isInitial] — show loading state first on true
   */
  function _fetchCharacter(isInitial) {
    if (!_mounted || !_characterId) return;

    if (isInitial) {
      _renderLoading();
    }

    api
      .get("/api/v1/characters/" + _characterId)
      .then(function (data) {
        if (!_mounted) return;
        _character = data;
        _renderSheet();
        // If Feed tab was active on first load, prime the feed.
        if (_activeTab === "feed" && _feedItems.length === 0 && !_feedLoading) {
          _fetchFeed(true);
        }
      })
      .catch(function (err) {
        if (!_mounted) return;
        _renderError((err && err.message) || undefined);
      });
  }

  // ---------------------------------------------------------------------------
  // Data fetching — feed
  // ---------------------------------------------------------------------------

  /**
   * Fetch one page of feed items.
   * On initial load (reset=true) replaces _feedItems; on load-more appends.
   *
   * @param {boolean} reset — true = first page, false = append next page
   */
  function _fetchFeed(reset) {
    if (!_mounted || !_characterId || _feedLoading) return;

    _feedLoading = true;
    if (reset) {
      _feedNextCursor = null;
    }

    // Render the loading indicator if we're already on the feed tab
    if (_activeTab === "feed" && _character) {
      _renderSheet();
    }

    var url = "/api/v1/characters/" + _characterId + "/feed?limit=" + FEED_LIMIT;
    if (!reset && _feedNextCursor) {
      url += "&after=" + encodeURIComponent(_feedNextCursor);
    }

    api
      .get(url)
      .then(function (data) {
        if (!_mounted) return;
        var items = (data && data.items) ? data.items : [];
        _feedNextCursor = (data && data.next_cursor) ? data.next_cursor : null;
        _feedHasMore    = !!(data && data.has_more);

        if (reset) {
          _feedItems = items;
        } else {
          _feedItems = _feedItems.concat(items);
        }
      })
      .catch(function () {
        // Feed errors are non-fatal; leave the current list in place
      })
      .finally(function () {
        _feedLoading = false;
        if (_mounted && _activeTab === "feed" && _character) {
          _renderSheet();
        }
      });
  }

  // ---------------------------------------------------------------------------
  // Poll callback
  // ---------------------------------------------------------------------------

  /**
   * Called by store polling every 60 seconds with fresh character data.
   * Updates _character and re-renders if still mounted.
   *
   * @param {object} data — CharacterDetailResponse from GET /api/v1/characters/{id}
   */
  function _pollCallback(data) {
    if (!_mounted) return;
    if (data) {
      _character = data;
      _renderSheet();
    }
  }

  // ---------------------------------------------------------------------------
  // Teardown / cleanup
  // ---------------------------------------------------------------------------

  /**
   * Called when navigating away from this view.
   * Stops polling and clears mounted flag to prevent stale callbacks.
   */
  function _teardown() {
    _mounted = false;
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").unregisterPoll(POLL_KEY);
    }
  }

  /**
   * One-time hashchange listener: calls _teardown when leaving this view's routes.
   * Removes itself after the first qualifying navigation.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/character" && path !== "/gm/character") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render and mount the Character Sheet view.
   * Called by router.js for "/character" and "/gm/character" routes.
   */
  return function render() {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // Resolve the character ID from the Alpine store.
    var characterId = null;
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      characterId = Alpine.store("app").character_id;
    }

    if (!characterId) {
      _viewEl.innerHTML =
        '<div class="cs-root">' +
          '<p class="error-text" role="alert">No character linked to this account.</p>' +
        '</div>';
      return;
    }

    // Reset state for a fresh mount.
    _mounted         = true;
    _characterId     = characterId;
    _character       = null;
    _activeTab       = "traits";
    _feedItems       = [];
    _feedNextCursor  = null;
    _feedHasMore     = false;
    _feedLoading     = false;
    _actionInFlight  = false;

    // Initial data load.
    _fetchCharacter(true);

    // Register 60-second polling.
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      Alpine.store("app").registerPoll(POLL_KEY, {
        url: "/api/v1/characters/" + characterId,
        intervalMs: POLL_INTERVAL_MS,
        callback: _pollCallback,
      });
    }

    // Teardown on navigation away.
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
