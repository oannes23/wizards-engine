/* Wizards Engine — Proposal Card component
 *
 * Renders a single proposal as an expandable <article> card (Pico CSS styled).
 * Handles both collapsed (summary) and expanded (full details + actions) views.
 *
 * Props passed to render():
 *   proposal  (object)   — ProposalResponse from GET /api/v1/proposals
 *   expanded  (boolean)  — whether this card is currently expanded
 *   inflight  (boolean)  — true while an approve/reject request is in-flight
 *   onApprove (function) — called with (id, overrides) on approve submit
 *   onReject  (function) — called with (id, { rejection_note }) on reject submit
 *   onToggle  (function) — called with (id) when the header is clicked
 *
 * Usage:
 *   var html = components.proposalCard.render(props);
 *   el.innerHTML = html;
 *   components.proposalCard.attach(el, props);
 *
 * render() returns HTML; attach() wires up event listeners. Both must be
 * called — render first, then attach after the HTML is in the DOM.
 *
 * No Alpine x-data here; state is managed by the parent gm-queue view.
 *
 * Registers as:  window.components.proposalCard
 */

window.components = window.components || {};

window.components.proposalCard = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  /** Human-readable action type labels. */
  var ACTION_LABELS = {
    use_skill:        "Use Skill",
    use_magic:        "Use Magic",
    charge_magic:     "Charge Magic",
    regain_gnosis:    "Regain Gnosis",
    work_on_project:  "Work on Project",
    rest:             "Rest",
    new_trait:        "New Trait",
    new_bond:         "New Bond",
    recharge_trait:   "Recharge Trait",
    maintain_bond:    "Maintain Bond",
    resolve_clock:    "Resolve Clock",
    resolve_trauma:   "Resolve Trauma",
  };

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /**
   * Delegate to shared utils (window.utils — loaded via utils.js).
   */
  var _esc = function (str) { return window.utils.esc(str); };
  var _relativeTime = function (s) { return window.utils.relativeTime(s); };

  /**
   * Return a human-readable label for an action type.
   * @param {string} actionType
   * @returns {string}
   */
  function _actionLabel(actionType) {
    return ACTION_LABELS[actionType] || actionType;
  }

  /**
   * Truncate a string to maxLen characters, appending "..." if truncated.
   * @param {string} str
   * @param {number} maxLen
   * @returns {string}
   */
  function _truncate(str, maxLen) {
    if (!str) return "";
    if (str.length <= maxLen) return str;
    return str.slice(0, maxLen) + "...";
  }

  /**
   * Format a value for display in a detail table.
   * Nested objects are flattened to "key: value" pairs on separate lines.
   * Raw IDs (strings that look like ULIDs — 26 uppercase alphanumeric chars)
   * are shown truncated with an ellipsis so they don't dominate the display.
   * @param {*} value
   * @returns {string} safe plain text
   */
  function _formatValue(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (typeof value === "object" && !Array.isArray(value)) {
      // Flatten one level: "key: val, key: val"
      var pairs = Object.keys(value)
        .filter(function (k) { return value[k] !== null && value[k] !== undefined; })
        .map(function (k) {
          var label = k.replace(/_/g, " ");
          label = label.charAt(0).toUpperCase() + label.slice(1);
          return label + ": " + _formatValue(value[k]);
        });
      return pairs.join(", ") || "(empty)";
    }
    if (Array.isArray(value)) {
      return value.map(_formatValue).join(", ") || "(none)";
    }
    var str = String(value);
    // Truncate bare ULID-like IDs (26 chars, all caps/digits) to avoid clutter
    if (/^[0-9A-Z]{26}$/.test(str)) {
      return str.slice(0, 8) + "...";
    }
    return str;
  }

  /**
   * Render key-value detail rows for the selections object.
   * Only outputs entries with non-null, non-undefined values.
   * Fields ending in _id are skipped — raw IDs are not useful to display.
   * @param {object} selections
   * @returns {string} HTML rows
   */
  function _renderSelections(selections) {
    if (!selections || typeof selections !== "object") return "";
    var keys = Object.keys(selections);
    if (keys.length === 0) return "";

    var rows = keys
      .filter(function (k) {
        // Skip raw ID fields — not meaningful for human readers
        if (k.slice(-3) === "_id") return false;
        return selections[k] !== null && selections[k] !== undefined;
      })
      .map(function (k) {
        var label = k.replace(/_/g, " ");
        label = label.charAt(0).toUpperCase() + label.slice(1);
        return (
          '<tr><th scope="row">' + _esc(label) + '</th>' +
          '<td>' + _esc(_formatValue(selections[k])) + '</td></tr>'
        );
      })
      .join("");

    if (!rows) return "";
    return (
      '<figure>' +
        '<table role="grid">' +
          '<tbody>' + rows + '</tbody>' +
        '</table>' +
      '</figure>'
    );
  }

  /**
   * Format a calculated_effect value with domain-specific readable labels.
   * Handles common cost/dice-pool shapes produced by the proposal service.
   * @param {string} key
   * @param {*} value
   * @returns {string} safe plain text
   */
  function _formatEffectValue(key, value) {
    if (value === null || value === undefined) return "";
    // Dice pool: { dice: N } or number
    if (key === "dice_pool" || key === "dice") {
      var n = typeof value === "object" ? value.dice : value;
      if (typeof n === "number") return n + "d";
    }
    // Costs object: { free_time: N, gnosis: N, ... }
    if (key === "costs" && typeof value === "object") {
      var parts = [];
      if (value.free_time) parts.push(value.free_time + " FT");
      if (value.gnosis)    parts.push(value.gnosis + " Gnosis");
      if (value.plot)      parts.push(value.plot + " Plot");
      if (value.stress)    parts.push(value.stress + " Stress");
      return parts.length > 0 ? "Costs: " + parts.join(", ") : _formatValue(value);
    }
    return _formatValue(value);
  }

  /**
   * Render key-value detail rows for the calculated_effect object.
   * @param {object} effect
   * @returns {string} HTML
   */
  function _renderEffect(effect) {
    if (!effect || typeof effect !== "object") return "";
    var keys = Object.keys(effect);
    if (keys.length === 0) return "";

    var rows = keys
      .filter(function (k) {
        return effect[k] !== null && effect[k] !== undefined;
      })
      .map(function (k) {
        var label = k.replace(/_/g, " ");
        label = label.charAt(0).toUpperCase() + label.slice(1);
        return (
          '<tr><th scope="row">' + _esc(label) + '</th>' +
          '<td>' + _esc(_formatEffectValue(k, effect[k])) + '</td></tr>'
        );
      })
      .join("");

    if (!rows) return "";
    return (
      '<details class="proposal-card__effect">' +
        '<summary>Calculated effect</summary>' +
        '<figure>' +
          '<table role="grid">' +
            '<tbody>' + rows + '</tbody>' +
          '</table>' +
        '</figure>' +
      '</details>'
    );
  }

  /**
   * Render the advanced approval fields for a use_skill proposal.
   * Shows: bond strained checkbox only. GM narrative and force are in
   * the shared section outside the Advanced panel.
   * @param {string} id — proposal id, used for field ids
   * @returns {string} HTML
   */
  function _renderUseSkillAdvanced(id) {
    void id; // id unused here; kept for consistent signature
    return (
      '<div class="proposal-card__advanced-fields">' +
        '<label>' +
          '<input type="checkbox" name="bond_strained" /> ' +
          'Bond strained' +
        '</label>' +
      '</div>'
    );
  }

  /**
   * Render the advanced approval fields for a resolve_clock proposal.
   * @param {string} id — proposal id
   * @returns {string} HTML
   */
  function _renderResolveClockAdvanced(id) {
    return (
      '<div class="proposal-card__advanced-fields">' +
        '<label for="adv-narrative-' + _esc(id) + '">Resolution narrative (required)' +
          '<textarea id="adv-narrative-' + _esc(id) + '" name="gm_narrative" ' +
                    'rows="3" placeholder="Describe what happens when this clock resolves..." required></textarea>' +
        '</label>' +
        '<label for="adv-rider-' + _esc(id) + '">Rider event narrative (optional)' +
          '<input type="text" id="adv-rider-' + _esc(id) + '" name="rider_event" ' +
                 'placeholder="Narrative for any follow-on consequence..." />' +
        '</label>' +
      '</div>'
    );
  }

  /**
   * Render the advanced approval fields for a resolve_trauma proposal.
   * Includes a bond selector (placeholder — bond IDs would come from context).
   * @param {string} id — proposal id
   * @param {object} proposal — full ProposalResponse (for calculated_effect)
   * @returns {string} HTML
   */
  function _renderResolveTraumaAdvanced(id, proposal) {
    var stressInfo = "";
    if (proposal.calculated_effect && proposal.calculated_effect.current_stress !== undefined) {
      stressInfo = (
        '<p class="proposal-card__stress-state">' +
          '<strong>Stress state:</strong> ' +
          _esc(String(proposal.calculated_effect.current_stress)) +
          ' / ' +
          _esc(String(proposal.calculated_effect.max_stress || "?")) +
        '</p>'
      );
    }

    return (
      '<div class="proposal-card__advanced-fields">' +
        stressInfo +
        '<label for="adv-bond-' + _esc(id) + '">Bond that becomes trauma' +
          '<input type="text" id="adv-bond-' + _esc(id) + '" name="bond_id" ' +
                 'placeholder="Bond ID or name..." />' +
        '</label>' +
        '<label for="adv-trauma-name-' + _esc(id) + '">Trauma name' +
          '<input type="text" id="adv-trauma-name-' + _esc(id) + '" name="trauma_name" ' +
                 'placeholder="e.g. Cursed Mark" />' +
        '</label>' +
        '<label for="adv-trauma-desc-' + _esc(id) + '">Trauma description' +
          '<textarea id="adv-trauma-desc-' + _esc(id) + '" name="trauma_description" ' +
                    'rows="2" placeholder="Describe the trauma condition..."></textarea>' +
        '</label>' +
      '</div>'
    );
  }

  /**
   * Render the advanced approval fields for a generic proposal.
   * @returns {string} HTML
   */
  function _renderGenericAdvanced() {
    return (
      '<div class="proposal-card__advanced-fields">' +
        '<label>' +
          '<input type="checkbox" name="bond_strained" /> ' +
          'Bond strained' +
        '</label>' +
      '</div>'
    );
  }

  /**
   * Render the type-specific advanced fields based on action_type.
   * @param {object} proposal
   * @returns {string} HTML
   */
  function _renderAdvancedFields(proposal) {
    var id = proposal.id;
    switch (proposal.action_type) {
      case "use_skill":
        return _renderUseSkillAdvanced(id);
      case "resolve_clock":
        return _renderResolveClockAdvanced(id);
      case "resolve_trauma":
        return _renderResolveTraumaAdvanced(id, proposal);
      default:
        return _renderGenericAdvanced();
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  /**
   * Render the proposal card HTML string.
   * Must call attach() after this HTML is inserted into the DOM.
   *
   * @param {object} props
   * @param {object}   props.proposal
   * @param {boolean}  props.expanded
   * @param {boolean}  props.inflight
   * @param {function} props.onApprove
   * @param {function} props.onReject
   * @param {function} props.onToggle
   * @returns {string} HTML
   */
  function render(props) {
    var p = props.proposal;
    var expanded = !!props.expanded;
    var inflight = !!props.inflight;
    var isSystem = p.origin === "system";

    var cardClasses = "proposal-card";
    if (isSystem) cardClasses += " proposal-card--system";

    var systemBadge = isSystem
      ? '<span class="proposal-card__badge proposal-card__badge--system">System</span>'
      : "";

    var actionBadge =
      '<span class="proposal-card__badge proposal-card__badge--action">' +
        _esc(_actionLabel(p.action_type)) +
      '</span>';

    var narrativePreview = _esc(_truncate(p.narrative, 80));

    var collapsedContent =
      '<div class="proposal-card__header" role="button" tabindex="0" ' +
           'aria-expanded="' + (expanded ? "true" : "false") + '" ' +
           'data-toggle-id="' + _esc(p.id) + '">' +
        '<div class="proposal-card__meta">' +
          '<strong class="proposal-card__character">' + _esc(p.character_name) + '</strong>' +
          '<div class="proposal-card__badges">' + systemBadge + actionBadge + '</div>' +
        '</div>' +
        '<div class="proposal-card__preview">' +
          (narrativePreview
            ? '<span class="proposal-card__narrative-preview">' + narrativePreview + '</span>'
            : '<span class="proposal-card__narrative-preview proposal-card__narrative-preview--empty">(no narrative)</span>') +
          '<span class="proposal-card__time">' + _esc(_relativeTime(p.created_at)) + '</span>' +
        '</div>' +
      '</div>';

    var expandedContent = "";
    if (expanded) {
      // Resolve-clock and resolve-trauma get special stress/clock details above selections
      var specialDetails = "";
      if (p.action_type === "resolve_clock" && p.selections && p.selections.clock_id) {
        specialDetails = (
          '<div class="proposal-card__special-details">' +
            '<p><strong>Clock:</strong> ' + _esc(String(p.selections.clock_id)) + '</p>' +
          '</div>'
        );
      } else if (p.action_type === "resolve_trauma" && p.calculated_effect) {
        var stress = p.calculated_effect.current_stress;
        var maxStress = p.calculated_effect.max_stress;
        if (stress !== undefined && maxStress !== undefined) {
          specialDetails = (
            '<div class="proposal-card__special-details">' +
              '<p><strong>Stress:</strong> ' +
                _esc(String(stress)) + ' / ' + _esc(String(maxStress)) +
              '</p>' +
            '</div>'
          );
        }
      }

      var fullNarrative = p.narrative
        ? '<p class="proposal-card__narrative">' + _esc(p.narrative) + '</p>'
        : '<p class="proposal-card__narrative proposal-card__narrative--empty"><em>No narrative provided.</em></p>';

      expandedContent = (
        '<div class="proposal-card__expanded" id="expanded-' + _esc(p.id) + '">' +
          fullNarrative +
          specialDetails +
          _renderSelections(p.selections) +
          _renderEffect(p.calculated_effect) +

          // GM narrative override (shared across all types)
          '<label for="gm-narrative-' + _esc(p.id) + '" class="proposal-card__gm-narrative-label">' +
            'GM narrative (optional)' +
            '<textarea id="gm-narrative-' + _esc(p.id) + '" name="gm_narrative" ' +
                      'rows="2" placeholder="Add a GM narrative..."></textarea>' +
          '</label>' +

          // Advanced section
          '<details class="proposal-card__advanced" id="advanced-' + _esc(p.id) + '">' +
            '<summary>Advanced options</summary>' +
            _renderAdvancedFields(p) +
            '<label>' +
              '<input type="checkbox" name="force_approve" /> ' +
              'Force approve (bypass cost check)' +
            '</label>' +
          '</details>' +

          // Reject section
          '<details class="proposal-card__reject-section" id="reject-' + _esc(p.id) + '">' +
            '<summary class="proposal-card__reject-toggle">Reject...</summary>' +
            '<label for="reject-note-' + _esc(p.id) + '">' +
              'Rejection note (optional)' +
              '<input type="text" id="reject-note-' + _esc(p.id) + '" name="reject_note" ' +
                     'placeholder="Reason for rejection..." />' +
            '</label>' +
            '<button type="button" class="outline contrast proposal-card__reject-btn" ' +
                    'data-action="reject" data-id="' + _esc(p.id) + '" ' +
                    (inflight ? "disabled" : "") + '>' +
              'Reject proposal' +
            '</button>' +
          '</details>' +

          // Primary approve button
          '<button type="button" class="proposal-card__approve-btn" ' +
                  'data-action="approve" data-id="' + _esc(p.id) + '" ' +
                  (inflight ? "disabled" : "") + '>' +
            (inflight ? '<span aria-busy="true"></span> Processing...' : 'Approve') +
          '</button>' +
        '</div>'
      );
    }

    return (
      '<article class="' + _esc(cardClasses) + '" id="card-' + _esc(p.id) + '" ' +
               'data-proposal-id="' + _esc(p.id) + '">' +
        collapsedContent +
        expandedContent +
      '</article>'
    );
  }

  /**
   * Attach event listeners to a rendered proposal card.
   * Call after inserting render() output into the DOM.
   *
   * @param {HTMLElement} container — element containing the rendered card
   * @param {object} props — same props object passed to render()
   */
  function attach(container, props) {
    var p = props.proposal;
    var cardEl = container.querySelector("#card-" + p.id);
    if (!cardEl) return;

    // Toggle expand/collapse on header click or Enter/Space keydown
    var headerEl = cardEl.querySelector('[data-toggle-id="' + p.id + '"]');
    if (headerEl) {
      headerEl.addEventListener("click", function () {
        if (props.onToggle) props.onToggle(p.id);
      });
      headerEl.addEventListener("keydown", function (evt) {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          if (props.onToggle) props.onToggle(p.id);
        }
      });
    }

    if (!props.expanded) return;

    // Approve button — reads GM narrative and advanced fields from the DOM
    var approveBtn = cardEl.querySelector('[data-action="approve"][data-id="' + p.id + '"]');
    if (approveBtn) {
      approveBtn.addEventListener("click", function () {
        if (props.inflight) return;

        var gmNarrativeEl = cardEl.querySelector('[name="gm_narrative"]');
        var forceEl = cardEl.querySelector('[name="force_approve"]');
        var bondStrainedEl = cardEl.querySelector('[name="bond_strained"]');

        var gmNarrative = gmNarrativeEl ? gmNarrativeEl.value.trim() || null : null;
        var force = forceEl ? forceEl.checked : false;

        var gmOverrides = {};

        if (p.action_type === "resolve_clock") {
          var riderEventEl = cardEl.querySelector('[name="rider_event"]');
          if (riderEventEl && riderEventEl.value.trim()) {
            gmOverrides.rider_event = riderEventEl.value.trim();
          }
        }

        if (p.action_type === "resolve_trauma") {
          var bondIdEl = cardEl.querySelector('[name="bond_id"]');
          var traumaNameEl = cardEl.querySelector('[name="trauma_name"]');
          var traumaDescEl = cardEl.querySelector('[name="trauma_description"]');
          if (bondIdEl && bondIdEl.value.trim()) {
            gmOverrides.bond_id = bondIdEl.value.trim();
          }
          if (traumaNameEl && traumaNameEl.value.trim()) {
            gmOverrides.trauma_name = traumaNameEl.value.trim();
          }
          if (traumaDescEl && traumaDescEl.value.trim()) {
            gmOverrides.trauma_description = traumaDescEl.value.trim();
          }
        }

        if (bondStrainedEl && bondStrainedEl.checked) {
          gmOverrides.bond_strained = true;
        }

        var overridesPayload = Object.keys(gmOverrides).length > 0 ? gmOverrides : null;

        if (props.onApprove) {
          props.onApprove(p.id, {
            narrative: gmNarrative,
            gm_overrides: overridesPayload,
            force: force,
          });
        }
      });
    }

    // Reject button — reads rejection note from the DOM
    var rejectBtn = cardEl.querySelector('[data-action="reject"][data-id="' + p.id + '"]');
    if (rejectBtn) {
      rejectBtn.addEventListener("click", function () {
        if (props.inflight) return;
        var noteEl = cardEl.querySelector('[name="reject_note"]');
        var note = noteEl ? noteEl.value.trim() || null : null;
        if (props.onReject) {
          props.onReject(p.id, { rejection_note: note });
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Render the proposal card to an HTML string.
     * Call attach() after inserting into the DOM.
     *
     * @param {object} props
     * @returns {string} HTML
     */
    render: render,

    /**
     * Attach event listeners to a rendered card.
     * Must be called after render() output is in the DOM.
     *
     * @param {HTMLElement} container — element containing the rendered card HTML
     * @param {object} props
     */
    attach: attach,
  };
})();
