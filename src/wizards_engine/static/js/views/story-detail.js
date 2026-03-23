/* Wizards Engine — Story Detail view
 *
 * Route:  #/world/stories/:id   and   #/gm/world/stories/:id
 * Access: All authenticated users who can see the story
 *
 * Displays:
 *   - Story header: name, status badge, summary/description
 *   - Owners: list of owner type + id badges (API returns type + id only, no name)
 *   - Tags: displayed as small chips
 *   - Entries: chronological list (oldest first) with author ID, timestamp,
 *     entry text, and an Edit button for own entries (or all entries if GM)
 *   - Add Entry form at the bottom (text area + submit)
 *
 * Entry submission calls POST /api/v1/stories/{id}/entries with { text: "..." }
 * Edit calls PATCH /api/v1/stories/{id}/entries/{entry_id} with { text: "..." }
 *
 * Registers as:  window.views.storyDetail
 * Called by:     router.js parameterized route handlers for
 *                "/world/stories/:id" and "/gm/world/stories/:id"
 */

window.views = window.views || {};

window.views.storyDetail = (function () {
  // ---------------------------------------------------------------------------
  // Private state
  // ---------------------------------------------------------------------------

  /** The #view element — stored at render time. */
  var _viewEl = null;

  /** Whether we are the currently mounted view. */
  var _mounted = false;

  /** The story ID currently being displayed. */
  var _currentId = null;

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  var _relativeTime = function (s) { return window.utils.relativeTime(s); };

  /**
   * Return true if the current user is a GM.
   * Reads from the Alpine store.
   * @returns {boolean}
   */
  function _isGm() {
    if (typeof Alpine !== "undefined") {
      var store = Alpine.store("app");
      if (store) return store.isGm();
    }
    return false;
  }

  /**
   * Return the current user's ID from the Alpine store, or null.
   * @returns {string|null}
   */
  function _currentUserId() {
    if (typeof Alpine !== "undefined") {
      var store = Alpine.store("app");
      if (store && store.user) return store.user.id || null;
    }
    return null;
  }

  /**
   * Map a story status value to a CSS modifier class and display label.
   * @param {string} status
   * @returns {{ cssClass: string, label: string }}
   */
  function _statusInfo(status) {
    var map = {
      active:    { cssClass: "world-story-card__status--active",    label: "Active"    },
      completed: { cssClass: "world-story-card__status--completed", label: "Completed" },
      abandoned: { cssClass: "world-story-card__status--abandoned", label: "Abandoned" },
    };
    return map[status] || { cssClass: "", label: window.utils.esc(status) };
  }

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  function _renderLoading() {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="story-detail">' +
        '<p aria-busy="true" class="story-detail__loading">Loading story...</p>' +
      '</div>';
  }

  function _renderError(message) {
    if (!_viewEl) return;
    _viewEl.innerHTML =
      '<div class="story-detail">' +
        '<div class="story-detail__back">' +
          '<a href="#/world">&larr; World</a>' +
        '</div>' +
        '<p class="error-text" role="alert">' + window.utils.esc(message || "Failed to load story.") + '</p>' +
      '</div>';
  }

  // ---------------------------------------------------------------------------
  // HTML builders
  // ---------------------------------------------------------------------------

  /**
   * Build the owners section HTML.
   * The API returns {type, id} for each owner; there is no name field.
   * We display the owner type as a badge alongside the (truncated) ID.
   * @param {Array} owners — list of StoryOwnerResponse objects
   * @returns {string} HTML
   */
  function _buildOwnersHtml(owners) {
    if (!owners || owners.length === 0) {
      return '<p class="story-detail__empty-state">No owners assigned.</p>';
    }

    var items = owners.map(function (o) {
      var type = o.type || "unknown";
      var id   = o.id   || "";
      // Show a type badge + the first 8 chars of the ULID as a short identifier
      var shortId = id.length > 8 ? id.slice(0, 8) + "\u2026" : id;
      return (
        '<li class="story-detail__owner">' +
          '<span class="story-detail__owner-badge story-detail__owner-badge--' + window.utils.esc(type) + '">' +
            window.utils.esc(type) +
          '</span>' +
          '<span class="story-detail__owner-id">' + window.utils.esc(shortId) + '</span>' +
        '</li>'
      );
    }).join("");

    return '<ul class="story-detail__owner-list">' + items + '</ul>';
  }

  /**
   * Build the tags section HTML.
   * @param {Array|null} tags
   * @returns {string} HTML, or empty string if no tags
   */
  function _buildTagsHtml(tags) {
    if (!tags || tags.length === 0) return "";
    var chips = tags.map(function (tag) {
      return '<span class="world-story-card__tag">' + window.utils.esc(tag) + '</span>';
    }).join("");
    return '<div class="story-detail__tags">' + chips + '</div>';
  }

  /**
   * Build HTML for a single entry row.
   * The "Edit" button is shown when:
   *   - the current user is GM (can edit any entry), or
   *   - the entry's author_id matches the current user's ID.
   *
   * @param {object} entry  — StoryEntryResponse
   * @param {string} storyId
   * @param {boolean} canEdit — pre-computed edit permission
   * @returns {string} HTML
   */
  function _buildEntryHtml(entry, storyId, canEdit) {
    var entryId   = entry.id || "";
    var text      = entry.text || "";
    var authorId  = entry.author_id || "";
    var createdAt = entry.created_at || "";
    var updatedAt = entry.updated_at || "";

    // Show a short author label (first 8 chars of author ID — full name not
    // available from the story detail endpoint without a separate users lookup)
    var shortAuthor = authorId.length > 8 ? authorId.slice(0, 8) + "\u2026" : authorId;

    var editBtnHtml = canEdit
      ? '<button class="story-detail__entry-edit-btn"' +
               ' data-entry-id="' + window.utils.esc(entryId) + '"' +
               ' data-story-id="' + window.utils.esc(storyId) + '"' +
               ' aria-label="Edit entry">' +
          'Edit' +
        '</button>'
      : '';

    // Show "edited" note if updated_at differs from created_at by more than 1s
    var editedNote = "";
    if (updatedAt && createdAt && updatedAt !== createdAt) {
      var diff = Math.abs(new Date(updatedAt).getTime() - new Date(createdAt).getTime());
      if (diff > 1000) {
        editedNote = ' <span class="story-detail__entry-edited">(edited ' + window.utils.esc(_relativeTime(updatedAt)) + ')</span>';
      }
    }

    return (
      '<li class="story-detail__entry" data-entry-id="' + window.utils.esc(entryId) + '">' +
        '<div class="story-detail__entry-meta">' +
          '<span class="story-detail__entry-author">' + window.utils.esc(shortAuthor) + '</span>' +
          '<span class="story-detail__entry-time">' + window.utils.esc(_relativeTime(createdAt)) + editedNote + '</span>' +
          editBtnHtml +
        '</div>' +
        '<div class="story-detail__entry-body">' +
          '<p class="story-detail__entry-text">' + window.utils.esc(text) + '</p>' +
        '</div>' +
      '</li>'
    );
  }

  /**
   * Build the entries list HTML.
   * @param {Array} entries — list of StoryEntryResponse (already sorted oldest-first by API)
   * @param {string} storyId
   * @param {boolean} isGm
   * @param {string|null} currentUserId
   * @returns {string} HTML
   */
  function _buildEntriesHtml(entries, storyId, isGm, currentUserId) {
    if (!entries || entries.length === 0) {
      return '<p class="story-detail__empty-state">No entries yet. Be the first to write one.</p>';
    }

    var items = entries.map(function (entry) {
      var canEdit = isGm || (currentUserId && entry.author_id === currentUserId);
      return _buildEntryHtml(entry, storyId, canEdit);
    }).join("");

    return '<ol class="story-detail__entry-list">' + items + '</ol>';
  }

  /**
   * Build the Add Entry form HTML.
   * @param {string} storyId
   * @returns {string} HTML
   */
  function _buildAddEntryFormHtml(storyId) {
    return (
      '<section class="story-detail__add-entry" aria-label="Add a narrative entry">' +
        '<h3 class="story-detail__section-heading">Add Entry</h3>' +
        '<form id="story-add-entry-form" novalidate>' +
          '<label for="story-entry-text">Entry text <span aria-hidden="true">*</span></label>' +
          '<textarea id="story-entry-text"' +
                   ' name="text"' +
                   ' rows="4"' +
                   ' placeholder="Write a narrative entry..."' +
                   ' required' +
          '></textarea>' +
          '<p id="story-entry-text-error" class="error-text" role="alert" hidden></p>' +
          '<div class="story-detail__form-actions">' +
            '<button type="submit" id="story-entry-submit">Add Entry</button>' +
          '</div>' +
        '</form>' +
      '</section>'
    );
  }

  /**
   * Build the full story detail page HTML.
   * @param {object} story — StoryDetailResponse
   * @returns {string} HTML
   */
  function _buildDetailHtml(story) {
    var storyId   = story.id || "";
    var name      = story.name || "Untitled";
    var summary   = story.summary || "";
    var status    = story.status || "active";
    var tags      = story.tags || [];
    var owners    = story.owners || [];
    var entries   = story.entries || [];

    var isGm          = _isGm();
    var currentUserId = _currentUserId();
    var statusInfo    = _statusInfo(status);

    var summaryHtml = summary
      ? '<p class="story-detail__summary">' + window.utils.esc(summary) + '</p>'
      : '';

    var tagsHtml   = _buildTagsHtml(tags);
    var ownersHtml = _buildOwnersHtml(owners);
    var entriesHtml = _buildEntriesHtml(entries, storyId, isGm, currentUserId);
    var addFormHtml = _buildAddEntryFormHtml(storyId);

    return (
      '<div class="story-detail">' +

        // Back link
        '<div class="story-detail__back">' +
          '<a href="#/world">&larr; World</a>' +
        '</div>' +

        // Header
        '<hgroup class="story-detail__hgroup">' +
          '<h2 class="story-detail__name">' + window.utils.esc(name) + '</h2>' +
          '<p>' +
            '<mark class="world-story-card__status ' + statusInfo.cssClass + '">' +
              window.utils.esc(statusInfo.label) +
            '</mark>' +
          '</p>' +
        '</hgroup>' +

        summaryHtml +
        tagsHtml +

        // Owners section
        '<section class="story-detail__section" aria-label="Story owners">' +
          '<h3 class="story-detail__section-heading">Owners</h3>' +
          ownersHtml +
        '</section>' +

        // Entries section
        '<section class="story-detail__section" aria-label="Story entries">' +
          '<h3 class="story-detail__section-heading">Entries</h3>' +
          entriesHtml +
        '</section>' +

        // Add Entry form
        addFormHtml +

      '</div>'
    );
  }

  // ---------------------------------------------------------------------------
  // Inline edit form
  // ---------------------------------------------------------------------------

  /**
   * Replace the body of an entry list item with an inline edit form.
   * Save calls PATCH; Cancel restores the original text.
   *
   * @param {HTMLElement} entryLi — the <li> element for this entry
   * @param {string} storyId
   * @param {string} entryId
   * @param {string} originalText
   */
  function _activateInlineEdit(entryLi, storyId, entryId, originalText) {
    var bodyEl = entryLi.querySelector(".story-detail__entry-body");
    if (!bodyEl) return;

    // Replace the static text with an inline form
    bodyEl.innerHTML =
      '<form class="story-detail__inline-edit-form" novalidate>' +
        '<textarea class="story-detail__inline-edit-textarea"' +
                 ' rows="4"' +
                 ' aria-label="Edit entry text"' +
                 ' required' +
        '>' + window.utils.esc(originalText) + '</textarea>' +
        '<p class="story-detail__inline-edit-error error-text" role="alert" hidden></p>' +
        '<div class="story-detail__form-actions story-detail__form-actions--inline">' +
          '<button type="submit" class="story-detail__save-btn">Save</button>' +
          '<button type="button" class="story-detail__cancel-btn outline secondary">Cancel</button>' +
        '</div>' +
      '</form>';

    // Focus the textarea immediately
    var textarea = bodyEl.querySelector("textarea");
    if (textarea) {
      textarea.focus();
      // Move cursor to end
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    }

    var form      = bodyEl.querySelector(".story-detail__inline-edit-form");
    var errorEl   = bodyEl.querySelector(".story-detail__inline-edit-error");
    var saveBtn   = bodyEl.querySelector(".story-detail__save-btn");
    var cancelBtn = bodyEl.querySelector(".story-detail__cancel-btn");

    // Cancel — restore original text
    cancelBtn.addEventListener("click", function () {
      bodyEl.innerHTML =
        '<p class="story-detail__entry-text">' + window.utils.esc(originalText) + '</p>';
    });

    // Save — PATCH the entry
    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      var newText = textarea ? textarea.value.trim() : "";
      if (!newText) {
        if (errorEl) {
          errorEl.textContent = "Entry text must not be empty.";
          errorEl.hidden = false;
        }
        if (textarea) textarea.focus();
        return;
      }
      if (errorEl) errorEl.hidden = true;

      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.setAttribute("aria-busy", "true");
        saveBtn.textContent = "Saving...";
      }

      api
        .patch(
          "/api/v1/stories/" + encodeURIComponent(storyId) +
          "/entries/" + encodeURIComponent(entryId),
          { text: newText }
        )
        .then(function (updatedEntry) {
          // Restore static display with new text
          var savedText = (updatedEntry && updatedEntry.text) ? updatedEntry.text : newText;
          bodyEl.innerHTML =
            '<p class="story-detail__entry-text">' + window.utils.esc(savedText) + '</p>';

          document.dispatchEvent(
            new CustomEvent("api:success", {
              detail: { message: "Entry updated." },
            })
          );
        })
        .catch(function () {
          // api.js already shows the error toast; re-enable the button
          if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.removeAttribute("aria-busy");
            saveBtn.textContent = "Save";
          }
        });
    });
  }

  // ---------------------------------------------------------------------------
  // Event wiring
  // ---------------------------------------------------------------------------

  /**
   * Attach click handlers to all "Edit" buttons in the entry list.
   * Delegates to _activateInlineEdit.
   * @param {HTMLElement} container — the #view element
   */
  function _bindEditButtons(container) {
    var btns = container.querySelectorAll(".story-detail__entry-edit-btn");
    for (var i = 0; i < btns.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var entryId = btn.getAttribute("data-entry-id");
          var storyId = btn.getAttribute("data-story-id");
          var entryLi = btn.closest(".story-detail__entry");
          if (!entryLi || !entryId || !storyId) return;

          var textEl  = entryLi.querySelector(".story-detail__entry-text");
          var originalText = textEl ? textEl.textContent : "";
          _activateInlineEdit(entryLi, storyId, entryId, originalText);
        });
      })(btns[i]);
    }
  }

  /**
   * Attach the submit handler to the Add Entry form.
   * On success, appends the new entry to the list and clears the form.
   * @param {HTMLElement} container — the #view element
   * @param {string} storyId
   * @param {boolean} isGm
   * @param {string|null} currentUserId
   */
  function _bindAddEntryForm(container, storyId, isGm, currentUserId) {
    var form      = container.querySelector("#story-add-entry-form");
    var submitBtn = container.querySelector("#story-entry-submit");
    var errorEl   = container.querySelector("#story-entry-text-error");
    if (!form) return;

    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      var textEl  = form.querySelector('[name="text"]');
      var textVal = textEl ? textEl.value.trim() : "";

      if (!textVal) {
        if (errorEl) {
          errorEl.textContent = "Entry text must not be empty.";
          errorEl.hidden = false;
        }
        if (textEl) textEl.focus();
        return;
      }
      if (errorEl) errorEl.hidden = true;

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.setAttribute("aria-busy", "true");
        submitBtn.textContent = "Adding...";
      }

      api
        .post("/api/v1/stories/" + encodeURIComponent(storyId) + "/entries", {
          text: textVal,
        })
        .then(function (newEntry) {
          if (!_mounted) return;

          // Clear the form
          if (textEl) textEl.value = "";

          // Append the new entry to the list (or replace the empty-state paragraph)
          var listEl = container.querySelector(".story-detail__entry-list");

          if (!listEl) {
            // There was an empty-state paragraph; replace the entries section body
            var section = container.querySelector('[aria-label="Story entries"]');
            if (section) {
              // Remove empty-state paragraph
              var emptyP = section.querySelector(".story-detail__empty-state");
              if (emptyP) emptyP.remove();
              // Create a fresh list
              listEl = document.createElement("ol");
              listEl.className = "story-detail__entry-list";
              section.appendChild(listEl);
            }
          }

          if (listEl) {
            var canEdit = isGm || (currentUserId && newEntry.author_id === currentUserId);
            var newHtml = _buildEntryHtml(newEntry, storyId, canEdit);
            var tmp = document.createElement("div");
            tmp.innerHTML = newHtml;
            var newLi = tmp.firstChild;
            listEl.appendChild(newLi);

            // Bind the edit button on the newly added entry
            var editBtn = newLi.querySelector(".story-detail__entry-edit-btn");
            if (editBtn) {
              editBtn.addEventListener("click", function () {
                var textBody = newLi.querySelector(".story-detail__entry-text");
                var originalText = textBody ? textBody.textContent : "";
                _activateInlineEdit(newLi, storyId, newEntry.id, originalText);
              });
            }

            // Scroll the new entry into view
            newLi.scrollIntoView({ behavior: "smooth", block: "nearest" });
          }

          document.dispatchEvent(
            new CustomEvent("api:success", {
              detail: { message: "Entry added." },
            })
          );
        })
        .catch(function () {
          // api.js already shows the error toast
        })
        .finally(function () {
          if (!_mounted) return;
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.removeAttribute("aria-busy");
            submitBtn.textContent = "Add Entry";
          }
        });
    });
  }

  // ---------------------------------------------------------------------------
  // Data fetching and rendering
  // ---------------------------------------------------------------------------

  /**
   * Fetch the story and render the detail view.
   * @param {string} id — story ULID
   */
  function _fetchAndRender(id) {
    if (!_mounted) return;
    _renderLoading();

    api
      .get("/api/v1/stories/" + encodeURIComponent(id))
      .then(function (story) {
        if (!_mounted) return;

        _viewEl.innerHTML = _buildDetailHtml(story);

        var isGm          = _isGm();
        var currentUserId = _currentUserId();

        _bindEditButtons(_viewEl);
        _bindAddEntryForm(_viewEl, story.id, isGm, currentUserId);
      })
      .catch(function () {
        if (!_mounted) return;
        _renderError("Story not found or you do not have access.");
      });
  }

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  /**
   * Tear down the view: clear mounted flag and stored ID.
   */
  function _teardown() {
    _mounted   = false;
    _currentId = null;
  }

  /**
   * Module-level hashchange handler.  Tears down only when navigating away
   * from this story's routes.
   */
  function _onHashChange() {
    var hash = window.location.hash;
    var path = hash ? hash.slice(1) : "/";
    if (
      _currentId &&
      (path === "/world/stories/" + _currentId ||
       path === "/gm/world/stories/" + _currentId)
    ) {
      return; // Still on this story's detail page — stay mounted
    }
    _teardown();
    window.removeEventListener("hashchange", _onHashChange);
  }

  // ---------------------------------------------------------------------------
  // Entry point
  // ---------------------------------------------------------------------------

  /**
   * Render the Story Detail view.
   * Called by router.js for "/world/stories/:id" and "/gm/world/stories/:id".
   *
   * @param {string} id — story ULID from the URL
   */
  return function render(id) {
    _viewEl = document.getElementById("view");
    if (!_viewEl) return;

    if (!id) {
      window.location.hash = "#/world";
      return;
    }

    _mounted   = true;
    _currentId = id;

    _fetchAndRender(id);

    // Remove any stale listener before registering the new one
    window.removeEventListener("hashchange", _onHashChange);
    window.addEventListener("hashchange", _onHashChange);
  };
})();
