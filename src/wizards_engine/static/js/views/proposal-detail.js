/* Wizards Engine — Proposal Detail / Edit / Revise view
 *
 * Routes:
 *   #/proposals/:id        — detail view (read-only, with Edit or Revise button)
 *   #/proposals/:id/edit   — edit/revise form (pre-populated, PATCH on submit)
 *
 * Features:
 *   - Fetches GET /api/v1/proposals/{id} on mount
 *   - Detail view shows: action type, status badge, full narrative, selections,
 *     calculated effect, timestamps
 *   - Approved proposals show GM narrative (gm_notes) and approval details
 *   - Rejected proposals show GM rejection note (gm_notes) and "Revise" button
 *   - Pending proposals show "Edit" button → navigate to #/proposals/{id}/edit
 *   - Edit/Revise form pre-populates narrative and selections, submits PATCH
 *   - On successful PATCH → redirect to #/proposals/{id}
 *
 * Registers as:  window.views.proposalDetail
 * Called by:     router.js parameterized route handler for "/proposals/:id" and
 *                "/proposals/:id/edit"
 */

window.views = window.views || {};

window.views.proposalDetail = (function () {
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
    resolve_clock:    "Resolve Clock",
    resolve_trauma:   "Resolve Trauma",
  };

  /** Skill options for the use_skill edit form. */
  var SKILLS = [
    { value: "awareness",  label: "Awareness"  },
    { value: "composure",  label: "Composure"  },
    { value: "influence",  label: "Influence"  },
    { value: "finesse",    label: "Finesse"    },
    { value: "speed",      label: "Speed"      },
    { value: "power",      label: "Power"      },
    { value: "knowledge",  label: "Knowledge"  },
    { value: "technology", label: "Technology" },
  ];

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** The #view element — stored at render time. */
  var _viewEl = null;

  /** Whether we are the currently mounted view. */
  var _mounted = false;

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  var _esc = function (str) { return window.utils.esc(str); };
  var _relativeTime = function (s) { return window.utils.relativeTime(s); };

  function _actionLabel(actionType) {
    return ACTION_LABELS[actionType] || actionType;
  }

  /**
   * Format a proposal status for display.
   * Returns { label, cssClass } where cssClass is a modifier for the badge.
   * @param {string} status
   * @returns {{ label: string, cssClass: string }}
   */
  function _statusInfo(status) {
    if (status === "pending")  return { label: "Pending",  cssClass: "proposal-status-badge--pending"  };
    if (status === "approved") return { label: "Approved", cssClass: "proposal-status-badge--approved" };
    if (status === "rejected") return { label: "Rejected", cssClass: "proposal-status-badge--rejected" };
    return { label: status, cssClass: "" };
  }

  /**
   * Format a date/ISO string for display (full date + time).
   * @param {string} isoString
   * @returns {string}
   */
  function _formatDate(isoString) {
    if (!isoString) return "";
    try {
      return new Date(isoString).toLocaleString();
    } catch (_) {
      return String(isoString);
    }
  }

  /**
   * Render key-value detail rows for the selections object.
   * Mirrors proposal-card.js _renderSelections logic (local copy to avoid
   * tight coupling to the GM-only card component).
   * @param {object} selections
   * @returns {string} HTML
   */
  function _renderSelections(selections) {
    if (!selections || typeof selections !== "object") return "";
    var keys = Object.keys(selections);
    if (keys.length === 0) return "";

    var rows = keys
      .filter(function (k) {
        if (k.slice(-3) === "_id") return false; // skip raw ID fields
        return selections[k] !== null && selections[k] !== undefined;
      })
      .map(function (k) {
        var label = k.replace(/_/g, " ");
        label = label.charAt(0).toUpperCase() + label.slice(1);
        var val = selections[k];
        if (typeof val === "boolean") val = val ? "Yes" : "No";
        return (
          '<tr><th scope="row">' + _esc(label) + '</th>' +
          '<td>' + _esc(String(val)) + '</td></tr>'
        );
      })
      .join("");

    if (!rows) return "";
    return (
      '<figure class="proposal-detail__selections">' +
        '<table role="grid">' +
          '<caption>Selections</caption>' +
          '<tbody>' + rows + '</tbody>' +
        '</table>' +
      '</figure>'
    );
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
        var val = effect[k];
        if (typeof val === "object") val = JSON.stringify(val);
        // Dice pool shorthand
        if (k === "dice_pool" || k === "dice") {
          var n = typeof effect[k] === "object" ? effect[k].dice : effect[k];
          if (typeof n === "number") val = n + "d";
        }
        return (
          '<tr><th scope="row">' + _esc(label) + '</th>' +
          '<td>' + _esc(String(val)) + '</td></tr>'
        );
      })
      .join("");

    if (!rows) return "";
    return (
      '<details class="proposal-detail__effect">' +
        '<summary>Calculated effect</summary>' +
        '<figure>' +
          '<table role="grid">' +
            '<tbody>' + rows + '</tbody>' +
          '</table>' +
        '</figure>' +
      '</details>'
    );
  }

  // ---------------------------------------------------------------------------
  // Detail view rendering
  // ---------------------------------------------------------------------------

  /**
   * Build the full HTML for the detail (read-only) view.
   * @param {object} proposal — ProposalResponse
   * @returns {string} HTML
   */
  function _buildDetailHtml(proposal) {
    var info = _statusInfo(proposal.status);

    var narrativeHtml = proposal.narrative
      ? '<p class="proposal-detail__narrative">' + _esc(proposal.narrative) + '</p>'
      : '<p class="proposal-detail__narrative proposal-detail__narrative--empty"><em>No narrative provided.</em></p>';

    // GM notes / rejection note — stored in gm_notes field
    var gmNotesHtml = "";
    if (proposal.gm_notes) {
      if (proposal.status === "rejected") {
        gmNotesHtml =
          '<div class="proposal-detail__rejection-note" role="note">' +
            '<strong>Rejection note:</strong>' +
            '<p>' + _esc(proposal.gm_notes) + '</p>' +
          '</div>';
      } else {
        gmNotesHtml =
          '<div class="proposal-detail__gm-notes" role="note">' +
            '<strong>GM notes:</strong>' +
            '<p>' + _esc(proposal.gm_notes) + '</p>' +
          '</div>';
      }
    }

    // Action button: Edit (pending) or Revise (rejected)
    var actionButtonHtml = "";
    if (proposal.status === "pending") {
      actionButtonHtml =
        '<a href="#/proposals/' + _esc(proposal.id) + '/edit" role="button" class="proposal-detail__edit-btn">' +
          'Edit' +
        '</a>';
    } else if (proposal.status === "rejected") {
      actionButtonHtml =
        '<a href="#/proposals/' + _esc(proposal.id) + '/edit" role="button" class="proposal-detail__revise-btn">' +
          'Revise and Resubmit' +
        '</a>';
    }

    return (
      '<div class="proposal-detail">' +
        '<div class="proposal-detail__back">' +
          '<a href="#/proposals">&larr; My Proposals</a>' +
        '</div>' +

        '<hgroup>' +
          '<h2>' + _esc(_actionLabel(proposal.action_type)) + '</h2>' +
          '<p>' +
            '<span class="proposal-status-badge ' + info.cssClass + '">' + info.label + '</span>' +
          '</p>' +
        '</hgroup>' +

        '<section class="proposal-detail__section">' +
          '<h3>Narrative</h3>' +
          narrativeHtml +
        '</section>' +

        _renderSelections(proposal.selections) +
        _renderEffect(proposal.calculated_effect) +

        gmNotesHtml +

        '<section class="proposal-detail__timestamps">' +
          '<dl>' +
            '<dt>Submitted</dt>' +
            '<dd>' + _esc(_formatDate(proposal.created_at)) + '</dd>' +
            '<dt>Last updated</dt>' +
            '<dd>' + _esc(_formatDate(proposal.updated_at)) + '</dd>' +
          '</dl>' +
        '</section>' +

        (actionButtonHtml
          ? '<div class="proposal-detail__actions">' + actionButtonHtml + '</div>'
          : '') +
      '</div>'
    );
  }

  // ---------------------------------------------------------------------------
  // Edit / Revise form rendering
  // ---------------------------------------------------------------------------

  /**
   * Build the skill selector HTML for use_skill edit form.
   * @param {string} currentSkill — currently selected skill value
   * @returns {string} HTML
   */
  function _buildSkillSelect(currentSkill) {
    var options = SKILLS.map(function (s) {
      var selected = (s.value === currentSkill) ? ' selected' : '';
      return '<option value="' + _esc(s.value) + '"' + selected + '>' + _esc(s.label) + '</option>';
    }).join("");

    return (
      '<label for="edit-skill">Skill <span aria-hidden="true">*</span></label>' +
      '<select id="edit-skill" name="skill" required>' +
        '<option value="" disabled' + (currentSkill ? '' : ' selected') + '>Select a skill...</option>' +
        options +
      '</select>'
    );
  }

  /**
   * Build a generic selections editor.
   * For action types without a specific form, renders the full narrative field only.
   * @param {object} proposal — ProposalResponse
   * @returns {string} HTML for the selections section
   */
  function _buildSelectionsEditor(proposal) {
    // Currently only use_skill has a richer selections form.
    // Other types just edit narrative; the selections dict is submitted unchanged.
    if (proposal.action_type === "use_skill") {
      var currentSkill = (proposal.selections && proposal.selections.skill) || "";
      return _buildSkillSelect(currentSkill);
    }
    return ""; // No extra selections UI for other types yet
  }

  /**
   * Build the full HTML for the edit/revise form.
   * @param {object} proposal — ProposalResponse
   * @param {boolean} isRevise — true if revising a rejected proposal
   * @returns {string} HTML
   */
  function _buildEditHtml(proposal, isRevise) {
    var heading = isRevise ? "Revise Proposal" : "Edit Proposal";
    var subheading = _actionLabel(proposal.action_type);
    var currentNarrative = proposal.narrative || "";
    var selectionsEditor = _buildSelectionsEditor(proposal);

    return (
      '<div class="proposal-edit">' +
        '<div class="proposal-edit__back">' +
          '<a href="#/proposals/' + _esc(proposal.id) + '">&larr; Back to proposal</a>' +
        '</div>' +

        '<hgroup>' +
          '<h2>' + _esc(heading) + '</h2>' +
          '<p>' + _esc(subheading) + '</p>' +
        '</hgroup>' +

        (isRevise && proposal.gm_notes
          ? '<div class="proposal-edit__rejection-note" role="note">' +
              '<strong>Rejection note:</strong> ' + _esc(proposal.gm_notes) +
            '</div>'
          : '') +

        '<form id="proposal-edit-form" novalidate>' +
          selectionsEditor +

          '<label for="edit-narrative">Narrative' +
            (proposal.action_type === "use_skill" ? ' <small>(optional)</small>' : ' <span aria-hidden="true">*</span>') +
          '</label>' +
          '<textarea id="edit-narrative" name="narrative" rows="5" ' +
                    'placeholder="Describe what your character does...">' +
            _esc(currentNarrative) +
          '</textarea>' +
          '<p id="edit-narrative-error" class="error-text" role="alert" hidden></p>' +

          '<div class="proposal-edit__actions">' +
            '<a href="#/proposals/' + _esc(proposal.id) + '" role="button" class="outline secondary">Cancel</a>' +
            '<button type="submit" id="proposal-edit-submit">Submit</button>' +
          '</div>' +
        '</form>' +
      '</div>'
    );
  }

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="proposal-detail">' +
        '<p aria-busy="true">Loading proposal...</p>' +
      '</div>';
  }

  function _renderError(message) {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="proposal-detail">' +
        '<div class="proposal-detail__back">' +
          '<a href="#/proposals">&larr; My Proposals</a>' +
        '</div>' +
        '<p class="error-text" role="alert">' + _esc(message || "Failed to load proposal.") + '</p>' +
      '</div>';
  }

  // ---------------------------------------------------------------------------
  // Form event attachment
  // ---------------------------------------------------------------------------

  /**
   * Attach submit handler to the edit form.
   * Reads narrative (and skill for use_skill) from the form, calls PATCH.
   *
   * @param {object} proposal — original ProposalResponse (for id, action_type, selections)
   */
  function _attachEditForm(proposal) {
    var form = document.getElementById("proposal-edit-form");
    var submitBtn = document.getElementById("proposal-edit-submit");
    var narrativeErrorEl = document.getElementById("edit-narrative-error");
    if (!form) return;

    form.addEventListener("submit", function (evt) {
      evt.preventDefault();

      var narrativeEl = form.querySelector('[name="narrative"]');
      var narrativeVal = narrativeEl ? narrativeEl.value.trim() : "";

      // Validate: downtime types require a narrative
      var downtimeTypes = ["regain_gnosis", "work_on_project", "rest", "new_trait", "new_bond"];
      var isDowntime = downtimeTypes.indexOf(proposal.action_type) !== -1;
      if (isDowntime && !narrativeVal) {
        if (narrativeErrorEl) {
          narrativeErrorEl.textContent = "Narrative is required for this action type.";
          narrativeErrorEl.hidden = false;
        }
        if (narrativeEl) narrativeEl.focus();
        return;
      }
      if (narrativeErrorEl) {
        narrativeErrorEl.hidden = true;
      }

      // Build patch body — only include changed fields
      var patchBody = {};

      // Always include narrative (it's the primary editable field)
      patchBody.narrative = narrativeVal || null;

      // For use_skill, update the skill selection
      if (proposal.action_type === "use_skill") {
        var skillEl = form.querySelector('[name="skill"]');
        var skillVal = skillEl ? skillEl.value : "";
        if (skillVal) {
          // Merge updated skill with existing selections (preserve other keys)
          var updatedSelections = {};
          if (proposal.selections && typeof proposal.selections === "object") {
            var selKeys = Object.keys(proposal.selections);
            for (var i = 0; i < selKeys.length; i++) {
              updatedSelections[selKeys[i]] = proposal.selections[selKeys[i]];
            }
          }
          updatedSelections.skill = skillVal;
          patchBody.selections = updatedSelections;
        }
      }

      // Disable submit during request
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.setAttribute("aria-busy", "true");
        submitBtn.textContent = "Submitting...";
      }

      api
        .patch("/api/v1/proposals/" + proposal.id, patchBody)
        .then(function () {
          document.dispatchEvent(
            new CustomEvent("api:success", {
              detail: { message: "Proposal updated." },
            })
          );
          window.location.hash = "#/proposals/" + proposal.id;
        })
        .catch(function () {
          // api.js already shows the error toast
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.removeAttribute("aria-busy");
            submitBtn.textContent = "Submit";
          }
        });
    });
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Fetch a single proposal and render the appropriate view.
   * @param {string} id — proposal ULID
   * @param {boolean} editMode — if true, render the edit form
   */
  function _fetchAndRender(id, editMode) {
    if (!_mounted) return;
    _renderLoading();

    api
      .get("/api/v1/proposals/" + encodeURIComponent(id))
      .then(function (proposal) {
        if (!_mounted) return;

        if (editMode) {
          // Only pending or rejected proposals can be edited/revised
          if (proposal.status !== "pending" && proposal.status !== "rejected") {
            _renderError("This proposal cannot be edited (status: " + proposal.status + ").");
            return;
          }
          var isRevise = proposal.status === "rejected";
          _viewEl.innerHTML = _buildEditHtml(proposal, isRevise);
          _attachEditForm(proposal);
        } else {
          _viewEl.innerHTML = _buildDetailHtml(proposal);
        }
      })
      .catch(function () {
        if (!_mounted) return;
        _renderError("Failed to load proposal.");
      });
  }

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  /**
   * The ID currently being viewed/edited. Used by _onHashChange to decide
   * whether the current navigation still belongs to this view.
   */
  var _currentId = null;

  /**
   * Called when navigating away.
   */
  function _teardown() {
    _mounted = false;
    _currentId = null;
  }

  /**
   * Module-level hashchange handler. Kept at module scope so it can be
   * reliably removed with removeEventListener.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    // Stay mounted if still on this proposal's detail or edit routes
    if (
      _currentId &&
      (path === "/proposals/" + _currentId || path === "/proposals/" + _currentId + "/edit")
    ) {
      return;
    }
    _teardown();
    window.removeEventListener("hashchange", _onHashChange);
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render the Proposal Detail or Edit view.
   * Called by router.js for the "/proposals/:id" and "/proposals/:id/edit" routes.
   *
   * @param {string} id — proposal ULID from the URL
   * @param {object} [opts] — options
   * @param {boolean} [opts.edit] — if true, render the edit form
   */
  return function render(id, opts) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    if (!id) {
      window.location.hash = "#/proposals";
      return;
    }

    _mounted = true;
    _currentId = id;
    var editMode = !!(opts && opts.edit);

    _fetchAndRender(id, editMode);

    // Remove any previous listener before adding the new one
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
