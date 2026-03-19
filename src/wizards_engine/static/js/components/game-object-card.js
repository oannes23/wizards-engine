/* Wizards Engine — GameObjectCard component
 *
 * Renders a tappable card for a game object (character, group, or location)
 * in the world browser listing.
 *
 * Props:
 *   type    (string)   — "character" | "group" | "location"
 *   data    (object)   — game object data from the API
 *                        data.starred (boolean, optional) — whether the object
 *                        is currently starred by the viewer
 *   onClick (function, optional) — click handler; if omitted, navigates to
 *                        the detail route for this object type
 *
 * Character card: name, detail_level badge (PC/NPC), description snippet
 * Group card:     name, tier badge, member count (if available), description snippet
 * Location card:  name, parent location name (if any), description snippet
 *
 * Uses Pico CSS <article> element for card styling.
 *
 * Usage:
 *   components.gameObjectCard.render({ type: 'character', data: characterObj })
 *
 * Returns an HTML string. Click handlers are wired separately via
 * data attributes:
 *   - Call components.gameObjectCard.bindClicks(container, onClick)
 *     after inserting the HTML to wire navigation clicks.
 *   - Call components.gameObjectCard.bindStarClicks(container, onStar)
 *     to wire star/unstar button clicks. onStar receives (type, id, currentlyStarred).
 */

window.components = window.components || {};

window.components.gameObjectCard = (function () {
  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  /**
   * Delegate to shared utils (window.utils — loaded via utils.js).
   */
  var _esc = function (str) { return window.utils.esc(str); };

  /**
   * Truncate a description string to a readable snippet length.
   * @param {string} text
   * @param {number} maxLen
   * @returns {string}
   */
  function _snippet(text, maxLen) {
    if (!text) return "";
    var s = String(text);
    if (s.length <= maxLen) return s;
    return s.slice(0, maxLen).trimEnd() + "\u2026"; // …
  }

  /**
   * Build a <mark> badge with a given label.
   * @param {string} label
   * @param {string} [modifier] — additional BEM modifier class
   * @returns {string} HTML
   */
  function _badge(label, modifier) {
    var cls = "game-object-card__badge" + (modifier ? " game-object-card__badge--" + modifier : "");
    return '<mark class="' + _esc(cls) + '">' + _esc(label) + '</mark>';
  }

  /**
   * Resolve the default navigate-on-click hash for a given type + id.
   * @param {string} type
   * @param {string} id
   * @returns {string}
   */
  function _defaultHash(type, id) {
    var map = {
      character: "#/world/characters/",
      group:     "#/world/groups/",
      location:  "#/world/locations/",
    };
    var prefix = map[type] || "#/world/";
    return prefix + encodeURIComponent(id || "");
  }

  // --------------------------------------------------------------------------
  // Type-specific header builders
  // --------------------------------------------------------------------------

  /**
   * Build header content for a character card.
   * @param {object} data
   * @returns {string} HTML
   */
  function _characterHeader(data) {
    // detail_level: "full" (PC) | "simplified" (NPC) from the API
    var detailLevel = data.detail_level || "";
    var badgeLabel, badgeMod;
    if (detailLevel === "full") {
      badgeLabel = "PC";
      badgeMod   = "pc";
    } else {
      badgeLabel = "NPC";
      badgeMod   = "npc";
    }
    return _badge(badgeLabel, badgeMod);
  }

  /**
   * Build header content for a group card.
   * @param {object} data
   * @returns {string} HTML
   */
  function _groupHeader(data) {
    var parts = [];
    if (data.tier !== undefined && data.tier !== null) {
      parts.push(_badge("Tier " + data.tier, "tier"));
    }
    if (data.member_count !== undefined && data.member_count !== null) {
      parts.push(
        '<span class="game-object-card__meta">' +
          _esc(data.member_count) + " members" +
        '</span>'
      );
    }
    return parts.join(" ");
  }

  /**
   * Build header content for a location card.
   * @param {object} data
   * @returns {string} HTML
   */
  function _locationHeader(data) {
    if (data.parent_name) {
      return (
        '<span class="game-object-card__meta">' +
          "in " + _esc(data.parent_name) +
        '</span>'
      );
    }
    return "";
  }

  /**
   * Build the type-specific header line.
   * @param {string} type
   * @param {object} data
   * @returns {string} HTML
   */
  function _header(type, data) {
    switch (type) {
      case "character": return _characterHeader(data);
      case "group":     return _groupHeader(data);
      case "location":  return _locationHeader(data);
      default:          return "";
    }
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  return {
    /**
     * Render a GameObjectCard to an HTML string.
     *
     * The <article> element carries a data-card-id and data-card-type attribute
     * so that bindClicks() can wire click handlers after insertion.
     *
     * If props.data.starred is truthy, the star button renders as filled (★),
     * otherwise as empty (☆). The star button has data-card-starred="true|false"
     * so that bindStarClicks can determine current state.
     *
     * @param {object} props
     * @param {string} props.type — "character" | "group" | "location"
     * @param {object} props.data
     * @param {boolean} [props.data.starred] — whether currently starred
     * @param {function} [props.onClick] — handled via bindClicks after insertion
     * @returns {string}
     */
    render: function (props) {
      var type = String(props.type || "character");
      var data = props.data || {};
      var id   = data.id || "";
      var name = data.name || data.display_name || "Untitled";
      var description = data.description || data.summary || "";
      var snippet = _snippet(description, 120);
      var headerHtml = _header(type, data);
      var hash = _defaultHash(type, id);

      var isStarred = data.starred ? true : false;
      var starIcon = isStarred ? "\u2605" : "\u2606"; // ★ or ☆
      var starLabel = isStarred
        ? "Unstar " + name
        : "Star " + name;
      var starBtn =
        '<button class="game-object-card__star-btn"' +
            ' data-card-star="true"' +
            ' data-card-id="' + _esc(id) + '"' +
            ' data-card-type="' + _esc(type) + '"' +
            ' data-card-starred="' + (isStarred ? "true" : "false") + '"' +
            ' aria-label="' + _esc(starLabel) + '"' +
            ' aria-pressed="' + (isStarred ? "true" : "false") + '"' +
            ' title="' + _esc(starLabel) + '">' +
          starIcon +
        '</button>';

      return (
        '<article class="game-object-card game-object-card--' + _esc(type) + '"' +
                ' data-card-id="' + _esc(id) + '"' +
                ' data-card-type="' + _esc(type) + '"' +
                ' data-card-hash="' + _esc(hash) + '"' +
                ' role="button"' +
                ' tabindex="0"' +
                ' aria-label="' + _esc(name) + '">' +
          '<header class="game-object-card__header">' +
            '<strong class="game-object-card__name">' + _esc(name) + '</strong>' +
            '<div class="game-object-card__header-actions">' +
              (headerHtml ? '<div class="game-object-card__badges">' + headerHtml + '</div>' : '') +
              starBtn +
            '</div>' +
          '</header>' +
          (snippet
            ? '<p class="game-object-card__snippet">' + _esc(snippet) + '</p>'
            : '') +
        '</article>'
      );
    },

    /**
     * Wire click (and keyboard Enter/Space) handlers for all .game-object-card
     * elements within a container. Call after inserting rendered HTML.
     *
     * The star button clicks are excluded from navigation — they stop propagation
     * to prevent triggering the card's navigate handler.
     *
     * @param {HTMLElement} container — the parent element containing the cards
     * @param {function} [onClick] — optional override; called with (type, id).
     *   If omitted, navigates to the card's data-card-hash.
     */
    bindClicks: function (container, onClick) {
      if (!container) return;
      var cards = container.querySelectorAll(".game-object-card");
      for (var i = 0; i < cards.length; i++) {
        (function (card) {
          function _activate(evt) {
            // Do not navigate when the star button was clicked.
            if (evt && evt.target && evt.target.closest &&
                evt.target.closest("[data-card-star]")) {
              return;
            }
            var type = card.getAttribute("data-card-type");
            var id   = card.getAttribute("data-card-id");
            var hash = card.getAttribute("data-card-hash");
            if (typeof onClick === "function") {
              onClick(type, id);
            } else if (typeof router !== "undefined") {
              router.navigate(hash);
            } else {
              window.location.hash = hash;
            }
          }

          card.addEventListener("click", _activate);
          card.addEventListener("keydown", function (evt) {
            if (evt.key === "Enter" || evt.key === " ") {
              evt.preventDefault();
              _activate(evt);
            }
          });
        })(cards[i]);
      }
    },

    /**
     * Wire star/unstar click handlers for all .game-object-card__star-btn
     * elements within a container. Call after inserting rendered HTML and
     * after bindClicks().
     *
     * The star button stops click propagation so the card navigation is not
     * triggered when starring.
     *
     * @param {HTMLElement} container — parent element containing the cards
     * @param {function} onStar — callback(type, id, currentlyStarred)
     *   type            — "character" | "group" | "location"
     *   id              — object ULID
     *   currentlyStarred — true if the button currently shows ★ (will unstar)
     */
    bindStarClicks: function (container, onStar) {
      if (!container || typeof onStar !== "function") return;
      var starBtns = container.querySelectorAll("[data-card-star]");
      for (var i = 0; i < starBtns.length; i++) {
        (function (btn) {
          btn.addEventListener("click", function (evt) {
            evt.stopPropagation();
            var type = btn.getAttribute("data-card-type");
            var id   = btn.getAttribute("data-card-id");
            var currentlyStarred = btn.getAttribute("data-card-starred") === "true";
            if (type && id) {
              onStar(type, id, currentlyStarred);
            }
          });
        })(starBtns[i]);
      }
    },
  };
})();
