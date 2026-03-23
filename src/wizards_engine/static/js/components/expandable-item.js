/* Wizards Engine — ExpandableItem component
 *
 * Renders an expand/collapse card for a trait or bond in character detail views.
 * Used by Epic 8.5 (Character Detail).
 *
 * Props:
 *   id           (string)           — unique identifier for this item (used in aria)
 *   name         (string)           — display name of the trait or bond
 *   dotsHtml     (string)           — pre-rendered HTML for charge dots (from chargeDots.render)
 *   badgeHtml    (string, optional) — pre-rendered HTML for an optional badge
 *                                     (e.g. trauma indicator, degraded marker)
 *   description  (string, optional) — full description text shown when expanded
 *   actions      (Array, optional)  — action buttons shown when expanded
 *                  Each action: { label, href?, dataAttrs? }
 *                  - href: if present, renders an <a> instead of <button>
 *                  - dataAttrs: object of data-* attribute key/value pairs
 *   footerLinkHtml (string, optional) — pre-rendered HTML for a footer link
 *                                     (e.g. "Go to [partner] →" for bonds)
 *   variant      (string)           — "trait" | "bond" — controls accent colour
 *
 * Usage:
 *   var html = components.expandableItem.render({ ... });
 *   container.innerHTML = html;
 *   components.expandableItem.attach(container);
 *
 * render() returns an HTML string. attach() wires click/keyboard listeners
 * via event delegation on the container — safe to call once even if multiple
 * items are rendered inside the same container.
 *
 * Toggle behaviour:
 *   - Click on .exp-item__trigger toggles the .exp-item--open class on .exp-item
 *   - aria-expanded attribute on the trigger reflects open/closed state
 *   - .exp-item__body has hidden attribute when collapsed, removed when expanded
 *   - Chevron rotates 90deg on expand via CSS transition
 *   - Keyboard: Enter or Space on trigger triggers toggle
 */

window.components = window.components || {};

window.components.expandableItem = (function () {
  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  /**
   * Delegate to shared utils (window.utils — loaded via utils.js).
   */
  var _esc = function (str) { return window.utils.esc(str); };

  /**
   * Build a data-attribute string from a plain object.
   * Each key becomes a data-<key> attribute. Values are escaped.
   * @param {object} dataAttrs
   * @returns {string}
   */
  function _dataAttrStr(dataAttrs) {
    if (!dataAttrs || typeof dataAttrs !== "object") return "";
    var parts = [];
    var keys = Object.keys(dataAttrs);
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      parts.push('data-' + _esc(key) + '="' + _esc(String(dataAttrs[key])) + '"');
    }
    return parts.length ? " " + parts.join(" ") : "";
  }

  /**
   * Build the action buttons / links shown in the expanded body.
   * @param {Array} actions — [{label, href?, dataAttrs?}]
   * @returns {string} HTML
   */
  function _renderActions(actions) {
    if (!actions || !actions.length) return "";
    var parts = [];
    for (var i = 0; i < actions.length; i++) {
      var a = actions[i];
      if (!a || !a.label) continue;
      var label = _esc(a.label);
      var dataStr = _dataAttrStr(a.dataAttrs);
      if (a.href) {
        parts.push(
          '<a class="exp-item__action-btn" href="' + _esc(a.href) + '"' + dataStr + '>' +
            label +
          '</a>'
        );
      } else {
        parts.push(
          '<button class="exp-item__action-btn"' + dataStr + '>' +
            label +
          '</button>'
        );
      }
    }
    if (!parts.length) return "";
    return '<div class="exp-item__actions">' + parts.join("") + '</div>';
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  return {
    /**
     * Render an ExpandableItem to an HTML string.
     *
     * The returned HTML must be inserted into the DOM before calling attach().
     * IDs are used for aria-controls / aria-labelledby wiring.
     *
     * @param {object} props
     * @param {string} props.id          — unique id for this item
     * @param {string} props.name        — display name
     * @param {string} props.dotsHtml    — charge dots HTML string
     * @param {string} [props.badgeHtml] — optional badge HTML string
     * @param {string} [props.description] — full description text
     * @param {Array}  [props.actions]   — action config objects
     * @param {string} [props.footerLinkHtml] — optional footer link HTML
     * @param {string} [props.variant]   — "trait" | "bond"
     * @returns {string}
     */
    render: function (props) {
      var id          = String(props.id || "exp-item-" + Math.random().toString(36).slice(2));
      var name        = String(props.name || "");
      var dotsHtml    = props.dotsHtml || "";
      var badgeHtml   = props.badgeHtml || "";
      var description = String(props.description || "");
      var actions     = props.actions || [];
      var footerLinkHtml = props.footerLinkHtml || "";
      var variant     = props.variant === "bond" ? "bond" : "trait";

      var triggerId   = "exp-trig-" + id;
      var bodyId      = "exp-body-" + id;

      // Trigger: always visible row — name, dots, optional badge, chevron
      var triggerHtml = (
        '<button class="exp-item__trigger"' +
                ' id="' + _esc(triggerId) + '"' +
                ' aria-expanded="false"' +
                ' aria-controls="' + _esc(bodyId) + '">' +
          '<span class="exp-item__trigger-left">' +
            '<span class="exp-item__name">' + _esc(name) + '</span>' +
            (dotsHtml ? '<span class="exp-item__dots">' + dotsHtml + '</span>' : '') +
            (badgeHtml ? '<span class="exp-item__badge">' + badgeHtml + '</span>' : '') +
          '</span>' +
          '<span class="exp-item__chevron" aria-hidden="true">&#x276F;</span>' +
        '</button>'
      );

      // Body: hidden by default, shown on expand
      var actionsHtml = _renderActions(actions);

      var descHtml = description
        ? '<p class="exp-item__desc">' + _esc(description) + '</p>'
        : "";

      var footerHtml = footerLinkHtml
        ? '<div class="exp-item__footer">' + footerLinkHtml + '</div>'
        : "";

      var bodyHtml = (
        '<div class="exp-item__body"' +
             ' id="' + _esc(bodyId) + '"' +
             ' role="region"' +
             ' aria-labelledby="' + _esc(triggerId) + '"' +
             ' hidden>' +
          descHtml +
          actionsHtml +
          footerHtml +
        '</div>'
      );

      return (
        '<div class="exp-item exp-item--' + _esc(variant) + '"' +
             ' data-exp-id="' + _esc(id) + '">' +
          triggerHtml +
          bodyHtml +
        '</div>'
      );
    },

    /**
     * Wire expand/collapse toggle listeners on all .exp-item elements inside
     * a container. Uses event delegation — call once per container regardless
     * of how many items it holds.
     *
     * Safe to call multiple times: checks for a sentinel attribute to avoid
     * double-binding.
     *
     * @param {HTMLElement} container — the parent element containing exp-items
     */
    attach: function (container) {
      if (!container) return;
      // Guard against double-binding the same container.
      if (container.dataset.expAttached) return;
      container.dataset.expAttached = "1";

      container.addEventListener("click", function (evt) {
        var trigger = evt.target && evt.target.closest
          ? evt.target.closest(".exp-item__trigger")
          : null;
        if (!trigger) return;
        _toggleItem(trigger);
      });

      container.addEventListener("keydown", function (evt) {
        if (evt.key !== "Enter" && evt.key !== " ") return;
        var trigger = evt.target && evt.target.closest
          ? evt.target.closest(".exp-item__trigger")
          : null;
        if (!trigger) return;
        evt.preventDefault();
        _toggleItem(trigger);
      });
    },
  };

  // --------------------------------------------------------------------------
  // Private toggle logic (defined after the return for clarity; hoisted by JS)
  // --------------------------------------------------------------------------

  /**
   * Toggle the open state of the .exp-item that owns a given trigger element.
   * @param {HTMLElement} trigger — the .exp-item__trigger button
   */
  function _toggleItem(trigger) {
    var item = trigger.closest(".exp-item");
    if (!item) return;

    var isOpen = item.classList.contains("exp-item--open");
    var bodyId = trigger.getAttribute("aria-controls");
    var body   = bodyId ? document.getElementById(bodyId) : null;

    if (isOpen) {
      item.classList.remove("exp-item--open");
      trigger.setAttribute("aria-expanded", "false");
      if (body) body.setAttribute("hidden", "");
    } else {
      item.classList.add("exp-item--open");
      trigger.setAttribute("aria-expanded", "true");
      if (body) body.removeAttribute("hidden");
    }
  }
})();
