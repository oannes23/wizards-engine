/* Wizards Engine — GM Trait Template Catalog view
 *
 * Route:  #/gm/trait-templates
 * Access: GM only
 *
 * Displays the full list of trait templates, filterable by type (core/role).
 * Supports create, edit (name+description), and soft-delete with confirmation.
 *
 * Features:
 *   - Fetches GET /api/v1/trait-templates on mount (cursor-paginated, "Load more")
 *   - Filter tabs: All | Core | Role
 *   - Create form: name (required), description (required), type dropdown
 *   - Edit modal: name and description editable; type shown as disabled badge
 *   - Delete: confirmation dialog with soft-delete warning
 *   - Usage count: shown as "N uses" placeholder (API does not provide count)
 *
 * Registers as:  window.views.gmTemplates
 * Called by:     router.js route entry for "/gm/trait-templates"
 */

window.views = window.views || {};

window.views.gmTemplates = (function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var BASE_URL = "/api/v1/trait-templates";
  var PAGE_LIMIT = 50;

  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** List of loaded template objects. */
  var _templates = [];

  /** Active filter: "all" | "core" | "role" */
  var _activeFilter = "all";

  /** Cursor for the next page of results, or null when exhausted. */
  var _nextCursor = null;

  /** Whether a page fetch is currently in flight. */
  var _loading = false;

  /** The #view element — stored at render time. */
  var _viewEl = null;

  /** Whether we are the currently mounted view. */
  var _mounted = false;

  /** Template currently being edited; null when no edit is open. */
  var _editingTemplate = null;

  /** Template pending deletion confirmation; null otherwise. */
  var _deletingTemplate = null;

  /** Whether the create form is visible. */
  var _showCreateForm = false;

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /**
   * HTML-escape a value for safe use in text content and attribute values.
   * @param {*} str
   * @returns {string}
   */
  function _esc(str) {
    return window.utils.esc(str);
  }

  /**
   * Dispatch an api:success toast event.
   * @param {string} message
   */
  function _showSuccess(message) {
    document.dispatchEvent(
      new CustomEvent("api:success", {
        detail: { message: message },
        bubbles: true,
      })
    );
  }

  /**
   * Return templates filtered by _activeFilter.
   * @returns {Array}
   */
  function _filteredTemplates() {
    if (_activeFilter === "core") {
      return _templates.filter(function (t) { return t.type === "core"; });
    }
    if (_activeFilter === "role") {
      return _templates.filter(function (t) { return t.type === "role"; });
    }
    return _templates;
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  /**
   * Full re-render of the view into _viewEl.
   */
  function _render() {
    if (!_viewEl || !_mounted) return;

    var filtered = _filteredTemplates();

    var html =
      '<div class="gm-templates">' +
        '<hgroup>' +
          '<h2>Trait Template Catalog</h2>' +
          '<p>' + _templates.length + ' template' + (_templates.length === 1 ? '' : 's') + ' total</p>' +
        '</hgroup>' +

        // Action bar
        '<div class="gm-templates__actions">' +
          '<button id="gm-templates-create-btn" class="gm-templates__create-btn"' +
                  ' aria-expanded="' + (_showCreateForm ? 'true' : 'false') + '">' +
            (_showCreateForm ? 'Cancel' : '+ New Template') +
          '</button>' +
        '</div>' +

        // Create form
        (_showCreateForm ? _renderCreateForm() : '') +

        // Filter tabs
        '<nav class="gm-templates__tabs" role="tablist" aria-label="Filter by type">' +
          _renderTab('all', 'All') +
          _renderTab('core', 'Core') +
          _renderTab('role', 'Role') +
        '</nav>';

    // Template list
    if (filtered.length === 0) {
      html +=
        '<p class="gm-templates__empty" role="status">' +
          ((_activeFilter === 'all' && _templates.length === 0)
            ? 'No templates yet. Create the first one above.'
            : 'No ' + _esc(_activeFilter) + ' templates.') +
        '</p>';
    } else {
      html += '<div class="gm-templates__list" role="list">';
      for (var i = 0; i < filtered.length; i++) {
        html += _renderTemplateCard(filtered[i]);
      }
      html += '</div>';
    }

    // Load more
    if (_nextCursor) {
      html +=
        '<div class="gm-templates__load-more">' +
          '<button id="gm-templates-load-more"' +
                  (_loading ? ' aria-busy="true" disabled' : '') + '>' +
            (_loading ? 'Loading...' : 'Load more') +
          '</button>' +
        '</div>';
    }

    // Edit modal
    if (_editingTemplate) {
      html += _renderEditModal(_editingTemplate);
    }

    // Delete confirmation dialog
    if (_deletingTemplate) {
      html += _renderDeleteDialog(_deletingTemplate);
    }

    html += '</div>'; // end .gm-templates

    _viewEl.innerHTML = html;
    _attachEventListeners();
  }

  /**
   * Render a single filter tab button.
   * @param {string} key
   * @param {string} label
   * @returns {string} HTML
   */
  function _renderTab(key, label) {
    var active = _activeFilter === key;
    return (
      '<button class="gm-templates__tab' + (active ? ' gm-templates__tab--active' : '') + '"' +
              ' data-filter="' + _esc(key) + '"' +
              ' role="tab"' +
              ' aria-selected="' + (active ? 'true' : 'false') + '">' +
        _esc(label) +
      '</button>'
    );
  }

  /**
   * Render a template card.
   * @param {object} template
   * @returns {string} HTML
   */
  function _renderTemplateCard(template) {
    var typeBadge =
      '<span class="gm-templates__type-badge gm-templates__type-badge--' + _esc(template.type) + '">' +
        _esc(template.type) +
      '</span>';

    return (
      '<article class="gm-templates__card" role="listitem" data-template-id="' + _esc(template.id) + '">' +
        '<header class="gm-templates__card-header">' +
          '<strong class="gm-templates__card-name">' + _esc(template.name) + '</strong>' +
          typeBadge +
        '</header>' +
        '<p class="gm-templates__card-desc">' + _esc(template.description || '') + '</p>' +
        '<footer class="gm-templates__card-footer">' +
          '<button class="gm-templates__edit-btn secondary outline"' +
                  ' data-edit-id="' + _esc(template.id) + '"' +
                  ' aria-label="Edit ' + _esc(template.name) + '">' +
            'Edit' +
          '</button>' +
          '<button class="gm-templates__delete-btn contrast outline"' +
                  ' data-delete-id="' + _esc(template.id) + '"' +
                  ' aria-label="Delete ' + _esc(template.name) + '">' +
            'Delete' +
          '</button>' +
        '</footer>' +
      '</article>'
    );
  }

  /**
   * Render the inline create form.
   * @returns {string} HTML
   */
  function _renderCreateForm() {
    return (
      '<form id="gm-templates-create-form" class="gm-templates__create-form" novalidate>' +
        '<fieldset>' +
          '<legend>New Template</legend>' +
          '<label>' +
            'Name <span aria-hidden="true">*</span>' +
            '<input type="text" id="tpl-create-name" name="name"' +
                   ' required maxlength="100" autocomplete="off"' +
                   ' placeholder="Template name" />' +
          '</label>' +
          '<label>' +
            'Description <span aria-hidden="true">*</span>' +
            '<textarea id="tpl-create-desc" name="description"' +
                      ' required maxlength="500" rows="3"' +
                      ' placeholder="What does this trait represent?"></textarea>' +
          '</label>' +
          '<label>' +
            'Type <span aria-hidden="true">*</span>' +
            '<select id="tpl-create-type" name="type" required>' +
              '<option value="">Select type...</option>' +
              '<option value="core">Core</option>' +
              '<option value="role">Role</option>' +
            '</select>' +
          '</label>' +
          '<div class="gm-templates__form-actions">' +
            '<button type="submit" id="tpl-create-submit">Create Template</button>' +
          '</div>' +
        '</fieldset>' +
      '</form>'
    );
  }

  /**
   * Render the edit modal for a template.
   * @param {object} template
   * @returns {string} HTML
   */
  function _renderEditModal(template) {
    return (
      '<dialog id="gm-templates-edit-modal" open aria-modal="true"' +
              ' aria-label="Edit template: ' + _esc(template.name) + '">' +
        '<article>' +
          '<header>' +
            '<h3>Edit Template</h3>' +
            '<button id="tpl-edit-close" class="gm-templates__modal-close"' +
                    ' aria-label="Close">' +
              '&#x2715;' +
            '</button>' +
          '</header>' +
          '<form id="gm-templates-edit-form" novalidate>' +
            '<input type="hidden" id="tpl-edit-id" value="' + _esc(template.id) + '" />' +
            '<label>' +
              'Type' +
              '<input type="text" value="' + _esc(template.type) + '"' +
                     ' disabled aria-readonly="true" />' +
            '</label>' +
            '<label>' +
              'Name <span aria-hidden="true">*</span>' +
              '<input type="text" id="tpl-edit-name" name="name"' +
                     ' required maxlength="100" autocomplete="off"' +
                     ' value="' + _esc(template.name) + '" />' +
            '</label>' +
            '<label>' +
              'Description <span aria-hidden="true">*</span>' +
              '<textarea id="tpl-edit-desc" name="description"' +
                        ' required maxlength="500" rows="3">' + _esc(template.description || '') + '</textarea>' +
            '</label>' +
            '<div class="gm-templates__form-actions">' +
              '<button type="submit" id="tpl-edit-submit">Save Changes</button>' +
              '<button type="button" id="tpl-edit-cancel" class="secondary">Cancel</button>' +
            '</div>' +
          '</form>' +
        '</article>' +
      '</dialog>'
    );
  }

  /**
   * Render the delete confirmation dialog.
   * @param {object} template
   * @returns {string} HTML
   */
  function _renderDeleteDialog(template) {
    return (
      '<dialog id="gm-templates-delete-dialog" open aria-modal="true"' +
              ' role="alertdialog"' +
              ' aria-label="Confirm deletion: ' + _esc(template.name) + '">' +
        '<article>' +
          '<header>' +
            '<h3>Delete Template?</h3>' +
          '</header>' +
          '<p>Delete <strong>' + _esc(template.name) + '</strong>?</p>' +
          '<p class="gm-templates__delete-warning">' +
            'This will hide the template from the catalog. ' +
            'Existing traits using it are not affected.' +
          '</p>' +
          '<div class="gm-templates__form-actions">' +
            '<button id="tpl-delete-confirm" class="contrast"' +
                    ' data-delete-id="' + _esc(template.id) + '">' +
              'Delete' +
            '</button>' +
            '<button id="tpl-delete-cancel" class="secondary">Cancel</button>' +
          '</div>' +
        '</article>' +
      '</dialog>'
    );
  }

  /**
   * Render a loading state.
   */
  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-templates">' +
        '<hgroup><h2>Trait Template Catalog</h2></hgroup>' +
        '<p aria-busy="true">Loading templates...</p>' +
      '</div>';
  }

  /**
   * Render an error state with a retry button.
   */
  function _renderError() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="gm-templates">' +
        '<hgroup><h2>Trait Template Catalog</h2></hgroup>' +
        '<p class="error-text" role="alert">Failed to load templates.</p>' +
        '<button id="gm-templates-retry">Retry</button>' +
      '</div>';

    var retryBtn = document.getElementById("gm-templates-retry");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () { _fetchPage(true); });
    }
  }

  // ---------------------------------------------------------------------------
  // Event wiring
  // ---------------------------------------------------------------------------

  /**
   * Attach all DOM event listeners after a render pass.
   */
  function _attachEventListeners() {
    // Toggle create form
    var createBtn = document.getElementById("gm-templates-create-btn");
    if (createBtn) {
      createBtn.addEventListener("click", function () {
        _showCreateForm = !_showCreateForm;
        _render();
        // Focus first field if form just opened
        if (_showCreateForm) {
          var nameInput = document.getElementById("tpl-create-name");
          if (nameInput) nameInput.focus();
        }
      });
    }

    // Create form submit
    var createForm = document.getElementById("gm-templates-create-form");
    if (createForm) {
      createForm.addEventListener("submit", function (evt) {
        evt.preventDefault();
        _handleCreate(createForm);
      });
    }

    // Filter tabs
    var tabs = _viewEl.querySelectorAll(".gm-templates__tab");
    for (var i = 0; i < tabs.length; i++) {
      (function (tab) {
        tab.addEventListener("click", function () {
          var filter = tab.getAttribute("data-filter");
          if (filter && filter !== _activeFilter) {
            _activeFilter = filter;
            _render();
          }
        });
      })(tabs[i]);
    }

    // Edit buttons on cards
    var editBtns = _viewEl.querySelectorAll("[data-edit-id]");
    for (var j = 0; j < editBtns.length; j++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var id = btn.getAttribute("data-edit-id");
          var template = _findById(id);
          if (template) {
            _editingTemplate = template;
            _render();
            var nameInput = document.getElementById("tpl-edit-name");
            if (nameInput) nameInput.focus();
          }
        });
      })(editBtns[j]);
    }

    // Delete buttons on cards
    var deleteBtns = _viewEl.querySelectorAll("[data-delete-id]:not(#tpl-delete-confirm)");
    for (var k = 0; k < deleteBtns.length; k++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var id = btn.getAttribute("data-delete-id");
          var template = _findById(id);
          if (template) {
            _deletingTemplate = template;
            _render();
          }
        });
      })(deleteBtns[k]);
    }

    // Edit modal: close / cancel
    var editClose = document.getElementById("tpl-edit-close");
    if (editClose) {
      editClose.addEventListener("click", function () {
        _editingTemplate = null;
        _render();
      });
    }
    var editCancel = document.getElementById("tpl-edit-cancel");
    if (editCancel) {
      editCancel.addEventListener("click", function () {
        _editingTemplate = null;
        _render();
      });
    }

    // Edit form submit
    var editForm = document.getElementById("gm-templates-edit-form");
    if (editForm) {
      editForm.addEventListener("submit", function (evt) {
        evt.preventDefault();
        _handleEdit(editForm);
      });
    }

    // Delete confirm
    var deleteConfirm = document.getElementById("tpl-delete-confirm");
    if (deleteConfirm) {
      deleteConfirm.addEventListener("click", function () {
        var id = deleteConfirm.getAttribute("data-delete-id");
        if (id) _handleDelete(id);
      });
    }

    // Delete cancel
    var deleteCancel = document.getElementById("tpl-delete-cancel");
    if (deleteCancel) {
      deleteCancel.addEventListener("click", function () {
        _deletingTemplate = null;
        _render();
      });
    }

    // Load more
    var loadMoreBtn = document.getElementById("gm-templates-load-more");
    if (loadMoreBtn) {
      loadMoreBtn.addEventListener("click", function () {
        _fetchPage(false);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Data helpers
  // ---------------------------------------------------------------------------

  /**
   * Find a template by ID from the in-memory list.
   * @param {string} id
   * @returns {object|null}
   */
  function _findById(id) {
    for (var i = 0; i < _templates.length; i++) {
      if (_templates[i].id === id) return _templates[i];
    }
    return null;
  }

  /**
   * Replace an in-memory template with an updated copy.
   * @param {object} updated
   */
  function _updateInList(updated) {
    for (var i = 0; i < _templates.length; i++) {
      if (_templates[i].id === updated.id) {
        _templates[i] = updated;
        return;
      }
    }
  }

  /**
   * Remove a template from the in-memory list by ID.
   * @param {string} id
   */
  function _removeFromList(id) {
    _templates = _templates.filter(function (t) { return t.id !== id; });
  }

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  /**
   * Fetch one page of templates.
   * @param {boolean} isInitial — if true, clears list and shows loading state first
   */
  function _fetchPage(isInitial) {
    if (!_mounted || _loading) return;

    _loading = true;

    if (isInitial) {
      _templates = [];
      _nextCursor = null;
      _renderLoading();
    }

    var url = BASE_URL + "?limit=" + PAGE_LIMIT;
    if (_nextCursor) {
      url += "&after=" + encodeURIComponent(_nextCursor);
    }

    api
      .get(url)
      .then(function (data) {
        if (!_mounted) return;
        var items = (data && data.items) ? data.items : [];
        _templates = _templates.concat(items);
        _nextCursor = (data && data.has_more && data.next_cursor) ? data.next_cursor : null;
        _loading = false;
        _render();
      })
      .catch(function () {
        if (!_mounted) return;
        _loading = false;
        if (isInitial) {
          _renderError();
        } else {
          _render();
        }
      });
  }

  // ---------------------------------------------------------------------------
  // Action handlers
  // ---------------------------------------------------------------------------

  /**
   * Handle the create form submission.
   * @param {HTMLFormElement} form
   */
  function _handleCreate(form) {
    var name = (form.elements["name"] ? form.elements["name"].value : "").trim();
    var description = (form.elements["description"] ? form.elements["description"].value : "").trim();
    var type = form.elements["type"] ? form.elements["type"].value : "";

    if (!name || !description || !type) {
      return;
    }

    var submitBtn = document.getElementById("tpl-create-submit");
    if (submitBtn) submitBtn.disabled = true;

    api
      .post(BASE_URL, { name: name, description: description, type: type })
      .then(function (created) {
        if (!_mounted) return;
        _templates.unshift(created);
        _showCreateForm = false;
        _render();
        _showSuccess('Template "' + created.name + '" created.');
      })
      .catch(function () {
        if (!_mounted) return;
        if (submitBtn) submitBtn.disabled = false;
      });
  }

  /**
   * Handle the edit form submission.
   * @param {HTMLFormElement} form
   */
  function _handleEdit(form) {
    var id = document.getElementById("tpl-edit-id") ? document.getElementById("tpl-edit-id").value : "";
    var name = (form.elements["name"] ? form.elements["name"].value : "").trim();
    var description = (form.elements["description"] ? form.elements["description"].value : "").trim();

    if (!id || !name || !description) return;

    var submitBtn = document.getElementById("tpl-edit-submit");
    if (submitBtn) submitBtn.disabled = true;

    api
      .patch(BASE_URL + "/" + encodeURIComponent(id), { name: name, description: description })
      .then(function (updated) {
        if (!_mounted) return;
        _updateInList(updated);
        _editingTemplate = null;
        _render();
        _showSuccess('Template "' + updated.name + '" updated.');
      })
      .catch(function () {
        if (!_mounted) return;
        if (submitBtn) submitBtn.disabled = false;
      });
  }

  /**
   * Handle soft-delete confirmation.
   * @param {string} id
   */
  function _handleDelete(id) {
    var confirmBtn = document.getElementById("tpl-delete-confirm");
    if (confirmBtn) confirmBtn.disabled = true;

    var template = _findById(id);
    var name = template ? template.name : "template";

    api
      .del(BASE_URL + "/" + encodeURIComponent(id))
      .then(function () {
        if (!_mounted) return;
        _removeFromList(id);
        _deletingTemplate = null;
        _render();
        _showSuccess('"' + name + '" deleted.');
      })
      .catch(function () {
        if (!_mounted) return;
        if (confirmBtn) confirmBtn.disabled = false;
      });
  }

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  /**
   * Reset all state when navigating away from this view.
   */
  function _teardown() {
    _mounted = false;
    _templates = [];
    _nextCursor = null;
    _loading = false;
    _editingTemplate = null;
    _deletingTemplate = null;
    _showCreateForm = false;
  }

  /**
   * One-time hashchange listener — tears down when navigating away.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (path !== "/gm/trait-templates") {
      _teardown();
      window.removeEventListener("hashchange", _onHashChange);
    }
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Mount the Trait Template Catalog view.
   * Called by router.js for the "/gm/trait-templates" route.
   */
  return function render() {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    // Guard: GM only
    if (typeof Alpine !== "undefined" && Alpine.store("app")) {
      if (!Alpine.store("app").isGm()) {
        _viewEl.innerHTML =
          '<div class="gm-templates">' +
            '<p class="error-text" role="alert">Access denied — GM only.</p>' +
          '</div>';
        return;
      }
    }

    // Reset state for a fresh mount
    _mounted = true;
    _templates = [];
    _nextCursor = null;
    _loading = false;
    _activeFilter = "all";
    _editingTemplate = null;
    _deletingTemplate = null;
    _showCreateForm = false;

    // Initial fetch
    _fetchPage(true);

    // Teardown when navigating away
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
