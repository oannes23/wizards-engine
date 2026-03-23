/* Wizards Engine — World Detail view
 *
 * Routes:
 *   #/world/characters/:id    — Character detail (PC sheet or NPC summary)
 *   #/world/groups/:id        — Group detail
 *   #/world/locations/:id     — Location detail
 *   #/gm/world/characters/:id
 *   #/gm/world/groups/:id
 *   #/gm/world/locations/:id
 *
 * Discriminates on the `type` argument passed by the router.
 *
 * Character detail:
 *   For PCs (detail_level === "full"), reuses character.js rendering logic
 *   with the given ID (not the store's character_id).
 *   For NPCs (detail_level === "simplified"), renders a compact summary card.
 *
 * Group detail:
 *   Fetches GET /api/v1/groups/{id} and GET /api/v1/clocks?associated_type=group&associated_id={id}
 *   Displays name, tier, description, traits, bonds, members, and clocks.
 *
 * Location detail:
 *   Fetches GET /api/v1/locations/{id}, GET /api/v1/clocks?associated_type=location&associated_id={id},
 *   and if parent_id is set, GET /api/v1/locations/{parent_id} for the parent name.
 *   Also fetches GET /api/v1/locations?parent={id} for children.
 *   Displays name, description, parent link, children, traits, bonds, and clocks.
 *
 * Registers as: window.views.worldDetail
 * Called by:    router.js parameterized routes for world object types
 */

window.views = window.views || {};

window.views.worldDetail = (function () {
  // ---------------------------------------------------------------------------
  // Module-level starred set
  // ---------------------------------------------------------------------------

  /**
   * Set of "type/id" keys for objects the current user has starred.
   * Populated on each render() call (lazy, non-blocking).
   */
  var _starredSet = {};

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /**
   * HTML-escape a value for text content or attribute values.
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

  /**
   * Render the "back to world browser" button HTML.
   * @returns {string} HTML
   */
  function _buildBackButton() {
    return (
      '<div class="wd-back-row">' +
        '<a href="#/world"' +
        '   class="wd-back-btn"' +
        '   role="button"' +
        '   aria-label="Back to world browser">' +
          '\u2190 World' +
        '</a>' +
      '</div>'
    );
  }

  /**
   * Render a loading state into the #view container.
   * @param {HTMLElement} el
   * @param {string} label
   */
  function _renderLoading(el, label) {
    el.innerHTML =
      '<div class="wd-root">' +
        _buildBackButton() +
        '<p class="wd-loading" aria-busy="true">Loading ' + _esc(label) + '...</p>' +
      '</div>';
  }

  /**
   * Render an error state into #view with a retry callback option.
   * @param {HTMLElement} el
   * @param {string} message
   */
  function _renderError(el, message) {
    el.innerHTML =
      '<div class="wd-root">' +
        _buildBackButton() +
        '<p class="wd-error" role="alert">' + _esc(message) + '</p>' +
      '</div>';
  }

  /**
   * Build a bond list item HTML string for a BondDisplayResponse.
   * Bonds link to the target object's detail page.
   * @param {object} b — BondDisplayResponse
   * @returns {string} HTML
   */
  function _buildBondItem(b) {
    var targetType = b.target_type || "";
    var targetId   = b.target_id   || "";
    var targetName = b.target_name || "Unknown";
    var label      = b.label       || "";
    var isTrauma   = !!b.is_trauma;

    // Compute link href to the target's detail page
    var typeToPath = { character: "characters", group: "groups", location: "locations" };
    var pathSeg = typeToPath[targetType] || targetType;
    var href = "#/world/" + pathSeg + "/" + encodeURIComponent(targetId);

    // Build display label: "label — targetName" or just one if the other is absent
    var displayName = label && targetName
      ? label + " \u2014 " + targetName
      : label || targetName;

    var traumaBadge = isTrauma
      ? '<mark class="wd-trauma-badge">Trauma</mark>'
      : "";

    var slotBadge = "";
    var slotType = b.slot_type || "";
    if (slotType === "group_holding") {
      slotBadge = '<mark class="wd-bond-slot-badge">Holding</mark>';
    } else if (slotType === "group_relation") {
      slotBadge = '<mark class="wd-bond-slot-badge">Relation</mark>';
    } else if (slotType === "npc_bond") {
      slotBadge = '<mark class="wd-bond-slot-badge">Bond</mark>';
    }

    var descSnippet = _snippet(b.description || "", 100);

    return (
      '<li class="wd-bond-item' + (isTrauma ? ' wd-bond-item--trauma' : '') + '">' +
        '<div class="wd-bond-item__header">' +
          '<a href="' + _esc(href) + '" class="wd-bond-item__link">' +
            _esc(displayName) +
          '</a>' +
          traumaBadge +
          slotBadge +
        '</div>' +
        (descSnippet
          ? '<p class="wd-bond-item__desc">' + _esc(descSnippet) + '</p>'
          : '') +
      '</li>'
    );
  }

  /**
   * Build the clocks section HTML from a list of ClockResponse items.
   * Uses ClockProgress component in detail mode.
   * @param {Array} clocks — list of ClockResponse
   * @returns {string} HTML
   */
  function _buildClocksSection(clocks) {
    if (!clocks || clocks.length === 0) {
      return '<p class="wd-empty">No associated clocks.</p>';
    }

    var html = '<ul class="wd-clock-list">';
    for (var i = 0; i < clocks.length; i++) {
      var clock = clocks[i];
      var progress = window.components.clockProgress.render({
        current: Number(clock.progress) || 0,
        total:   Number(clock.segments) || 1,
        mode:    "detail",
      });
      html +=
        '<li class="wd-clock-item">' +
          '<div class="wd-clock-item__header">' +
            '<strong class="wd-clock-item__name">' + _esc(clock.name) + '</strong>' +
          '</div>' +
          '<div class="wd-clock-item__progress">' +
            progress +
          '</div>' +
          (clock.notes
            ? '<p class="wd-clock-item__notes">' + _esc(clock.notes) + '</p>'
            : '') +
        '</li>';
    }
    html += '</ul>';
    return html;
  }

  // ---------------------------------------------------------------------------
  // Character detail
  // ---------------------------------------------------------------------------

  /**
   * Build an expandable bond card for a PC bond in the world-detail PC summary.
   * Similar to character.js _buildBondItem but read-only (no Maintain action).
   *
   * @param {object} b — BondDisplayResponse
   * @param {boolean} isGm — whether the current user is a GM
   * @returns {string} HTML
   */
  function _buildPcBondItem(b, isGm) {
    var isTrauma = !!b.is_trauma;
    var isPC = b.slot_type === "pc_bond";

    // Charge dots for PC bonds
    var dotsHtml = "";
    if (isPC && b.charges !== null && b.charges !== undefined) {
      var charges = Number(b.charges) || 0;
      var degradations = Number(b.degradations) || 0;
      var effectiveMax = 5 - degradations;

      dotsHtml = window.components.chargeDots.render({
        current: charges,
        max: 5,
        variant: "bond",
        effectiveMax: effectiveMax < 5 ? effectiveMax : undefined,
      });
    }

    // Display name
    var label = b.label || "";
    var targetName = b.target_name || "";
    var displayName = label && targetName ? label + " \u2014 " + targetName
                    : label || targetName || "Unknown";

    // Trauma badge
    var badgeHtml = isTrauma
      ? '<mark class="cs-trauma-badge">Trauma</mark>'
      : "";

    // Partner link
    var footerLinkHtml = "";
    var targetType = b.target_type || "";
    var targetId   = b.target_id   || "";
    if (targetType && targetId) {
      var typeToPath = { character: "characters", group: "groups", location: "locations" };
      var pathSeg = typeToPath[targetType] || targetType;
      var partnerHref = "#/world/" + pathSeg + "/" + encodeURIComponent(targetId);
      var partnerLabel = targetName || "partner";
      footerLinkHtml =
        '<a href="' + _esc(partnerHref) + '" class="exp-item__partner-link">' +
          'Go to ' + _esc(partnerLabel) + ' \u2192' +
        '</a>';
    }

    // Actions: GM Edit only (no Maintain — world-detail is read-only)
    var actions = [];
    if (isGm) {
      actions.push({
        label:     "Edit",
        href:      "#/gm/bonds/" + encodeURIComponent(b.id) + "/edit",
        secondary: true,
      });
    }

    return window.components.expandableItem.render({
      id:             b.id,
      name:           displayName,
      dotsHtml:       dotsHtml,
      badgeHtml:      badgeHtml,
      description:    b.description || "",
      footerLinkHtml: footerLinkHtml,
      actions:        actions,
      variant:        "bond",
      extraClass:     isTrauma ? "exp-item--trauma" : "",
    });
  }

  /**
   * Build a read-only PC summary view for characters with detail_level === "full".
   * Avoids the race condition caused by hijacking character.js.
   * Shows meters and a "View Full Sheet" link for the current user's own character.
   *
   * @param {object} c — CharacterDetailResponse (full)
   * @returns {string} HTML
   */
  function _buildPcSummary(c) {
    // Determine whether this PC is the viewing user's own character
    var isOwnCharacter = false;
    var characterHash = "#/world";
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      var store = Alpine.store("app");
      if (store.character_id && store.character_id === c.id) {
        isOwnCharacter = true;
        characterHash = "#/character";
      }
    }

    var viewLink = (
      '<a href="' + _esc(characterHash) + '" class="wd-pc-summary__view-link">' +
        (isOwnCharacter ? 'View My Sheet' : 'View Full Sheet') +
      '</a>'
    );

    var descSnippet = _snippet(c.description || "", 160);

    // Resource meters
    var STRESS_MAX         = 9;
    var FT_MAX             = 20;
    var PLOT_MAX           = 5;
    var GNOSIS_DISPLAY_MAX = 23;

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
      current: Number(c.plot) || 0,
      max: PLOT_MAX,
      color: "var(--we-plot-amber)",
    });
    var gnosisBar = window.components.meterBar.render({
      label: "Gnosis",
      current: Number(c.gnosis) || 0,
      max: GNOSIS_DISPLAY_MAX,
      color: "var(--we-gnosis-blue)",
    });

    // Determine GM status for Edit buttons
    var isGm = false;
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      isGm = Alpine.store("app").isGm();
    }

    // Active traits — expandable cards
    var activeTraits = (c.traits && c.traits.active) ? c.traits.active : [];
    var traitsHtml = "";
    if (activeTraits.length > 0) {
      traitsHtml = '<section class="wd-pc-summary__section">';
      traitsHtml += '<h3 class="wd-pc-summary__section-heading">Traits</h3>';
      traitsHtml += '<ul class="wd-trait-list">';
      for (var i = 0; i < activeTraits.length; i++) {
        var t = activeTraits[i];
        var charge = (t.charge !== null && t.charge !== undefined) ? Number(t.charge) : 0;
        var dots = window.components.chargeDots.render({ current: charge, max: 5, variant: "trait" });

        var traitActions = [];
        if (isGm) {
          traitActions.push({
            label:     "Edit",
            href:      "#/gm/traits/" + encodeURIComponent(t.id) + "/edit",
            secondary: true,
          });
        }

        traitsHtml += window.components.expandableItem.render({
          id:          t.id,
          name:        t.name,
          dotsHtml:    dots,
          description: t.description || "",
          actions:     traitActions,
          variant:     "trait",
        });
      }
      traitsHtml += '</ul></section>';
    }

    // Active bonds — expandable cards
    var activeBonds = (c.bonds && c.bonds.active) ? c.bonds.active : [];
    var bondsHtml = "";
    if (activeBonds.length > 0) {
      bondsHtml = '<section class="wd-pc-summary__section">';
      bondsHtml += '<h3 class="wd-pc-summary__section-heading">Bonds</h3>';
      bondsHtml += '<ul class="wd-bond-list">';
      for (var j = 0; j < activeBonds.length; j++) {
        bondsHtml += _buildPcBondItem(activeBonds[j], isGm);
      }
      bondsHtml += '</ul></section>';
    }

    return (
      '<div class="wd-pc-summary">' +
        '<div class="wd-pc-summary__header">' +
          '<h2 class="wd-pc-summary__name">' + _esc(c.name) + '</h2>' +
          '<mark class="wd-badge wd-badge--pc">PC</mark>' +
          viewLink +
        '</div>' +
        (descSnippet
          ? '<p class="wd-pc-summary__desc">' + _esc(descSnippet) + '</p>'
          : '') +
        '<div class="wd-pc-summary__meters">' +
          stressBar + ftBar + plotBar + gnosisBar +
        '</div>' +
        traitsHtml +
        bondsHtml +
        '<section class="cs-feed-section">' +
          '<h3 class="cs-feed-section__heading">Recent Events</h3>' +
          '<div id="wd-char-feed-container" class="cs-feed-section__container"></div>' +
        '</section>' +
      '</div>'
    );
  }

  /**
   * Build the NPC summary view (simplified characters).
   * @param {object} c — CharacterDetailResponse
   * @returns {string} HTML
   */
  function _buildNpcSummary(c) {
    var descFull = c.description || "";
    var attributes = c.attributes || null;

    var attributesHtml = "";
    if (attributes && typeof attributes === "object") {
      var keys = Object.keys(attributes);
      if (keys.length > 0) {
        attributesHtml = '<dl class="wd-npc-attrs">';
        for (var i = 0; i < keys.length; i++) {
          var key = keys[i];
          var val = attributes[key];
          var valStr = (val !== null && val !== undefined) ? String(val) : "";
          attributesHtml +=
            '<dt class="wd-npc-attrs__key">' + _esc(key) + '</dt>' +
            '<dd class="wd-npc-attrs__val">' + _esc(valStr) + '</dd>';
        }
        attributesHtml += '</dl>';
      }
    }

    // Show active bonds if present
    var activeBonds = (c.bonds && c.bonds.active) ? c.bonds.active : [];
    var bondsHtml = "";
    if (activeBonds.length > 0) {
      bondsHtml =
        '<section class="wd-section">' +
          '<h3 class="wd-section__heading">Bonds</h3>' +
          '<ul class="wd-bond-list">';
      for (var j = 0; j < activeBonds.length; j++) {
        bondsHtml += _buildBondItem(activeBonds[j]);
      }
      bondsHtml += '</ul></section>';
    }

    return (
      '<div class="wd-npc">' +
        '<div class="wd-npc__header">' +
          '<h2 class="wd-npc__name">' + _esc(c.name) + '</h2>' +
          '<mark class="wd-badge wd-badge--npc">NPC</mark>' +
        '</div>' +
        (descFull
          ? '<p class="wd-npc__desc">' + _esc(descFull) + '</p>'
          : '') +
        (attributesHtml
          ? '<section class="wd-section"><h3 class="wd-section__heading">Attributes</h3>' + attributesHtml + '</section>'
          : '') +
        bondsHtml +
      '</div>'
    );
  }

  /**
   * Render the character detail view.
   * PCs get a read-only inline summary (meters, traits, bonds).
   * NPCs get a compact attribute summary.
   *
   * The previous approach of temporarily patching store.character_id and the
   * #view element id was removed because it races with async fetches initiated
   * by character.js before the setTimeout(0) restore fires.
   *
   * @param {HTMLElement} el — #view element
   * @param {string} id — character ULID
   */
  function _renderCharacter(el, id) {
    _renderLoading(el, "character");

    api
      .get("/api/v1/characters/" + id)
      .then(function (data) {
        if (!_mounted) return;

        // Destroy any previous character feed list before replacing the DOM.
        if (_charFeedList) {
          _charFeedList.destroy();
          _charFeedList = null;
        }

        if (data.detail_level === "full") {
          // PC: render an inline read-only summary using shared components.
          el.innerHTML =
            '<div class="wd-root">' +
              _buildBackButton() +
              _buildPcSummary(data) +
            '</div>';
          // Wire expand/collapse toggle listeners for trait and bond cards
          window.components.expandableItem.attach(el);
        } else {
          // NPC: simplified summary (no feed section)
          el.innerHTML =
            '<div class="wd-root">' +
              _buildBackButton() +
              _buildNpcSummary(data) +
            '</div>';
        }
      })
      .catch(function (err) {
        if (!_mounted) return;
        _renderError(el, (err && err.message) || "Could not load character.");
      });
  }

  // ---------------------------------------------------------------------------
  // Group detail
  // ---------------------------------------------------------------------------

  /**
   * Build the group detail HTML from fetched data.
   * @param {object} group — GroupDetailResponse
   * @param {Array} clocks — list of ClockResponse
   * @returns {string} HTML
   */
  function _buildGroupDetail(group, clocks) {
    var name        = group.name        || "Untitled";
    var tier        = (group.tier !== null && group.tier !== undefined) ? group.tier : "—";
    var description = group.description || "";
    var traits      = group.traits      || [];
    var bonds       = (group.bonds && group.bonds.active) ? group.bonds.active : [];
    var members     = group.members     || [];

    // Separate bonds by slot_type for distinct display sections
    var relations = bonds.filter(function (b) { return b.slot_type === "group_relation"; });
    var holdings  = bonds.filter(function (b) { return b.slot_type === "group_holding";  });
    var otherBonds = bonds.filter(function (b) {
      return b.slot_type !== "group_relation" && b.slot_type !== "group_holding";
    });

    var html = '<div class="wd-detail wd-detail--group">';

    // Header
    html +=
      '<div class="wd-detail__header">' +
        '<h2 class="wd-detail__name">' + _esc(name) + '</h2>' +
        '<mark class="wd-badge wd-badge--tier">Tier ' + _esc(tier) + '</mark>' +
      '</div>';

    if (description) {
      html += '<p class="wd-detail__desc">' + _esc(description) + '</p>';
    }

    // Traits section
    html += '<section class="wd-section">';
    html += '<h3 class="wd-section__heading">Traits</h3>';
    if (traits.length === 0) {
      html += '<p class="wd-empty">No traits.</p>';
    } else {
      html += '<ul class="wd-trait-list">';
      for (var i = 0; i < traits.length; i++) {
        var t = traits[i];
        html +=
          '<li class="wd-trait-item">' +
            '<strong class="wd-trait-item__name">' + _esc(t.name) + '</strong>' +
            (t.description
              ? '<p class="wd-trait-item__desc">' + _esc(t.description) + '</p>'
              : '') +
          '</li>';
      }
      html += '</ul>';
    }
    html += '</section>';

    // Relations section (group_relation bonds)
    html += '<section class="wd-section">';
    html += '<h3 class="wd-section__heading">Relations</h3>';
    if (relations.length === 0 && otherBonds.length === 0) {
      html += '<p class="wd-empty">No relations.</p>';
    } else {
      html += '<ul class="wd-bond-list">';
      for (var j = 0; j < relations.length; j++) {
        html += _buildBondItem(relations[j]);
      }
      for (var k = 0; k < otherBonds.length; k++) {
        html += _buildBondItem(otherBonds[k]);
      }
      html += '</ul>';
    }
    html += '</section>';

    // Members section (characters bonded to this group)
    html += '<section class="wd-section">';
    html += '<h3 class="wd-section__heading">Members</h3>';
    if (members.length === 0) {
      html += '<p class="wd-empty">No members.</p>';
    } else {
      html += '<div class="wd-member-cards">';
      for (var m = 0; m < members.length; m++) {
        var memberData = {};
        for (var mk in members[m]) {
          if (Object.prototype.hasOwnProperty.call(members[m], mk)) {
            memberData[mk] = members[m][mk];
          }
        }
        memberData.starred = !!_starredSet["character/" + members[m].id];
        html += window.components.gameObjectCard.render({
          type: "character",
          data: memberData,
        });
      }
      html += '</div>';
    }
    html += '</section>';

    // Holdings section (group_holding bonds — locations owned/controlled by group)
    html += '<section class="wd-section">';
    html += '<h3 class="wd-section__heading">Holdings</h3>';
    if (holdings.length === 0) {
      html += '<p class="wd-empty">No holdings.</p>';
    } else {
      html += '<ul class="wd-bond-list">';
      for (var h = 0; h < holdings.length; h++) {
        html += _buildBondItem(holdings[h]);
      }
      html += '</ul>';
    }
    html += '</section>';

    // Clocks section
    html += '<section class="wd-section">';
    html += '<h3 class="wd-section__heading">Clocks</h3>';
    html += _buildClocksSection(clocks);
    html += '</section>';

    html += '</div>';
    return html;
  }

  /**
   * Render the group detail view.
   * Fetches group data and clocks in parallel.
   *
   * @param {HTMLElement} el — #view element
   * @param {string} id — group ULID
   */
  function _renderGroup(el, id) {
    _renderLoading(el, "group");

    var groupPromise  = api.get("/api/v1/groups/" + id);
    var clocksPromise = api.get("/api/v1/clocks?associated_type=group&associated_id=" + encodeURIComponent(id))
      .then(function (data) { return (data && data.items) ? data.items : []; })
      .catch(function () { return []; });

    Promise.all([groupPromise, clocksPromise])
      .then(function (results) {
        if (!_mounted) return;
        var group  = results[0];
        var clocks = results[1];
        el.innerHTML =
          '<div class="wd-root">' +
            _buildBackButton() +
            _buildGroupDetail(group, clocks) +
          '</div>';
        // Wire member card clicks and star toggles
        var memberCards = el.querySelector(".wd-member-cards");
        if (memberCards) {
          window.components.gameObjectCard.bindClicks(memberCards);
          window.components.gameObjectCard.bindStarClicks(memberCards, function (ct, cid, starred) {
            _handleStarInContainer(memberCards, ct, cid, starred);
          });
        }
      })
      .catch(function (err) {
        if (!_mounted) return;
        _renderError(el, (err && err.message) || "Could not load group.");
      });
  }

  // ---------------------------------------------------------------------------
  // Location detail
  // ---------------------------------------------------------------------------

  /**
   * Build the location detail HTML from fetched data.
   * @param {object} location    — LocationDetailResponse
   * @param {object|null} parent — LocationResponse for the parent, or null
   * @param {Array} children     — list of LocationResponse (direct children)
   * @param {Array} clocks       — list of ClockResponse
   * @returns {string} HTML
   */
  function _buildLocationDetail(location, parent, children, clocks) {
    var name        = location.name        || "Untitled";
    var description = location.description || "";
    var traits      = location.traits      || [];
    var bonds       = (location.bonds && location.bonds.active) ? location.bonds.active : [];

    var html = '<div class="wd-detail wd-detail--location">';

    // Header
    html += '<div class="wd-detail__header">';
    html += '<h2 class="wd-detail__name">' + _esc(name) + '</h2>';

    // Parent link
    if (parent) {
      var parentHref = "#/world/locations/" + encodeURIComponent(parent.id);
      html +=
        '<p class="wd-detail__parent">' +
          'Part of ' +
          '<a href="' + _esc(parentHref) + '" class="wd-parent-link">' +
            _esc(parent.name) +
          '</a>' +
        '</p>';
    } else if (location.parent_id) {
      // parent_id set but fetch failed — show the raw ID as fallback
      html +=
        '<p class="wd-detail__parent">' +
          'Part of <span class="wd-parent-link wd-parent-link--unknown">parent location</span>' +
        '</p>';
    }

    html += '</div>'; // wd-detail__header

    if (description) {
      html += '<p class="wd-detail__desc">' + _esc(description) + '</p>';
    }

    // Children section
    html += '<section class="wd-section">';
    html += '<h3 class="wd-section__heading">Sub-locations</h3>';
    if (children.length === 0) {
      html += '<p class="wd-empty">No sub-locations.</p>';
    } else {
      html += '<div class="wd-child-cards">';
      for (var c = 0; c < children.length; c++) {
        var childData = {};
        for (var ck in children[c]) {
          if (Object.prototype.hasOwnProperty.call(children[c], ck)) {
            childData[ck] = children[c][ck];
          }
        }
        childData.starred = !!_starredSet["location/" + children[c].id];
        html += window.components.gameObjectCard.render({
          type: "location",
          data: childData,
        });
      }
      html += '</div>';
    }
    html += '</section>';

    // Feature traits section
    html += '<section class="wd-section">';
    html += '<h3 class="wd-section__heading">Feature Traits</h3>';
    if (traits.length === 0) {
      html += '<p class="wd-empty">No feature traits.</p>';
    } else {
      html += '<ul class="wd-trait-list">';
      for (var i = 0; i < traits.length; i++) {
        var t = traits[i];
        html +=
          '<li class="wd-trait-item">' +
            '<strong class="wd-trait-item__name">' + _esc(t.name) + '</strong>' +
            (t.description
              ? '<p class="wd-trait-item__desc">' + _esc(t.description) + '</p>'
              : '') +
          '</li>';
      }
      html += '</ul>';
    }
    html += '</section>';

    // Bonds section
    html += '<section class="wd-section">';
    html += '<h3 class="wd-section__heading">Bonds</h3>';
    if (bonds.length === 0) {
      html += '<p class="wd-empty">No bonds.</p>';
    } else {
      html += '<ul class="wd-bond-list">';
      for (var j = 0; j < bonds.length; j++) {
        html += _buildBondItem(bonds[j]);
      }
      html += '</ul>';
    }
    html += '</section>';

    // Clocks section
    html += '<section class="wd-section">';
    html += '<h3 class="wd-section__heading">Clocks</h3>';
    html += _buildClocksSection(clocks);
    html += '</section>';

    html += '</div>';
    return html;
  }

  /**
   * Render the location detail view.
   * Fetches location data, children, parent (if any), and clocks in parallel.
   *
   * @param {HTMLElement} el — #view element
   * @param {string} id — location ULID
   */
  function _renderLocation(el, id) {
    _renderLoading(el, "location");

    var locationPromise = api.get("/api/v1/locations/" + id);
    var clocksPromise   = api.get("/api/v1/clocks?associated_type=location&associated_id=" + encodeURIComponent(id))
      .then(function (data) { return (data && data.items) ? data.items : []; })
      .catch(function () { return []; });
    var childrenPromise = api.get("/api/v1/locations?parent=" + encodeURIComponent(id))
      .then(function (data) { return (data && data.items) ? data.items : []; })
      .catch(function () { return []; });

    // Fetch location first to get parent_id, then optionally fetch parent
    Promise.all([locationPromise, clocksPromise, childrenPromise])
      .then(function (results) {
        if (!_mounted) return;
        var location = results[0];
        var clocks   = results[1];
        var children = results[2];

        if (location.parent_id) {
          return api.get("/api/v1/locations/" + location.parent_id)
            .then(function (parent) {
              return [location, parent, children, clocks];
            })
            .catch(function () {
              return [location, null, children, clocks];
            });
        }
        return [location, null, children, clocks];
      })
      .then(function (results) {
        if (!_mounted) return;
        var location = results[0];
        var parent   = results[1];
        var children = results[2];
        var clocks   = results[3];

        el.innerHTML =
          '<div class="wd-root">' +
            _buildBackButton() +
            _buildLocationDetail(location, parent, children, clocks) +
          '</div>';

        // Wire child location card clicks and star toggles
        var childCards = el.querySelector(".wd-child-cards");
        if (childCards) {
          window.components.gameObjectCard.bindClicks(childCards);
          window.components.gameObjectCard.bindStarClicks(childCards, function (ct, cid, starred) {
            _handleStarInContainer(childCards, ct, cid, starred);
          });
        }
      })
      .catch(function (err) {
        if (!_mounted) return;
        _renderError(el, (err && err.message) || "Could not load location.");
      });
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  // ---------------------------------------------------------------------------
  // Star / unstar helpers
  // ---------------------------------------------------------------------------

  /**
   * Fetch the current user's starred objects and populate _starredSet.
   * Non-blocking — does not re-render on completion.
   */
  function _fetchStarred() {
    api
      .get("/api/v1/me/starred")
      .then(function (data) {
        var items = Array.isArray(data) ? data : [];
        var set = {};
        for (var i = 0; i < items.length; i++) {
          var item = items[i];
          if (item.type && item.id) {
            set[item.type + "/" + item.id] = true;
          }
        }
        _starredSet = set;
      })
      .catch(function () {
        _starredSet = {};
      });
  }

  /**
   * Handle a star/unstar button click on a game object card in a container.
   * Applies optimistic UI immediately, then calls the API. Reverts on failure.
   *
   * @param {HTMLElement} container — container holding the clicked card
   * @param {string} cardType  — "character" | "group" | "location"
   * @param {string} cardId    — object ULID
   * @param {boolean} currentlyStarred
   */
  function _handleStarInContainer(container, cardType, cardId, currentlyStarred) {
    var key = cardType + "/" + cardId;
    var btn = container.querySelector(
      '[data-card-star][data-card-type="' + cardType + '"][data-card-id="' + cardId + '"]'
    );

    if (currentlyStarred) {
      if (btn) {
        btn.textContent = "\u2606"; // ☆
        btn.setAttribute("data-card-starred", "false");
        btn.setAttribute("aria-pressed", "false");
      }
      delete _starredSet[key];
      api
        .del("/api/v1/me/starred/" + encodeURIComponent(cardType) + "/" + encodeURIComponent(cardId))
        .catch(function () {
          _starredSet[key] = true;
          if (btn) {
            btn.textContent = "\u2605"; // ★
            btn.setAttribute("data-card-starred", "true");
            btn.setAttribute("aria-pressed", "true");
          }
        });
    } else {
      if (btn) {
        btn.textContent = "\u2605"; // ★
        btn.setAttribute("data-card-starred", "true");
        btn.setAttribute("aria-pressed", "true");
      }
      _starredSet[key] = true;
      api
        .post("/api/v1/me/starred", { type: cardType, id: cardId })
        .catch(function () {
          delete _starredSet[key];
          if (btn) {
            btn.textContent = "\u2606"; // ☆
            btn.setAttribute("data-card-starred", "false");
            btn.setAttribute("aria-pressed", "false");
          }
        });
    }
  }

  // ---------------------------------------------------------------------------
  // Mounted flag — async-safety on navigation away
  // ---------------------------------------------------------------------------

  /** Whether the view is currently mounted. Set false by the hashchange teardown. */
  var _mounted = false;

  /** FeedList instance for the character detail "Recent Events" section, or null. */
  var _charFeedList = null;

  /**
   * Teardown: mark as unmounted and remove the hashchange listener.
   */
  function _teardown() {
    _mounted = false;
    if (_charFeedList) {
      _charFeedList.destroy();
      _charFeedList = null;
    }
    window.removeEventListener("hashchange", _onHashChange);
  }

  /**
   * Hashchange listener. Tears down when the user navigates away from any
   * world-detail route (i.e. a route that is NOT /world/*).
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    // Stay mounted as long as we are on any /world/* or /gm/world/* sub-route.
    if (path.indexOf("/world/") !== 0 && path.indexOf("/gm/world/") !== 0) {
      _teardown();
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render a game object detail view.
   * Dispatched by router.js for parameterized world routes.
   *
   * @param {string} type — "characters" | "groups" | "locations"
   * @param {string} id   — ULID of the object
   */
  return function render(type, id) {
    var el = document.getElementById("view");
    if (!el) return;

    // Reset mounted flag and attach hashchange teardown for this navigation.
    _mounted = true;
    _starredSet = {};

    // Destroy any stale character feed list from a prior navigation.
    if (_charFeedList) {
      _charFeedList.destroy();
      _charFeedList = null;
    }

    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);

    // Pre-fetch starred objects so cards can render with the correct star state.
    // Non-blocking — the detail fetch proceeds immediately in parallel.
    _fetchStarred();

    switch (type) {
      case "characters":
        _renderCharacter(el, id);
        break;
      case "groups":
        _renderGroup(el, id);
        break;
      case "locations":
        _renderLocation(el, id);
        break;
      default:
        _renderError(el, "Unknown object type: " + type);
    }
  };
})();
