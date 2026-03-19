/* Wizards Engine — GameObjectCard component
 *
 * Renders a tappable card for a game object (character, group, or location)
 * in the world browser listing.
 *
 * Props:
 *   type    (string)   — "character" | "group" | "location"
 *   data    (object)   — game object data from the API
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
 * data attributes — call components.gameObjectCard.bindClicks(container, onClick)
 * after inserting the HTML.
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
     * @param {object} props
     * @param {string} props.type — "character" | "group" | "location"
     * @param {object} props.data
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
            (headerHtml ? '<div class="game-object-card__badges">' + headerHtml + '</div>' : '') +
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
     * @param {HTMLElement} container — the parent element containing the cards
     * @param {function} [onClick] — optional override; called with (type, id, data).
     *   If omitted, navigates to the card's data-card-hash.
     */
    bindClicks: function (container, onClick) {
      if (!container) return;
      var cards = container.querySelectorAll(".game-object-card");
      for (var i = 0; i < cards.length; i++) {
        (function (card) {
          function _activate() {
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
              _activate();
            }
          });
        })(cards[i]);
      }
    },
  };
})();
