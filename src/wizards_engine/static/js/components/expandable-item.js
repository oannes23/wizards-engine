/* Wizards Engine — ExpandableItem component
 *
 * Renders an expand/collapse card for trait and bond items.
 *
 * Props:
 *   id          (string)  — unique identifier for ARIA (e.g. slot ULID)
 *   name        (string)  — display name shown in collapsed header
 *   dotsHtml    (string)  — pre-rendered ChargeDots HTML (or empty string)
 *   badgeHtml   (string)  — optional HTML for badges (e.g. trauma indicator)
 *   description (string)  — full text shown in expanded body
 *   actions     (Array)   — list of action descriptors:
 *                           { label, href?, dataAttrs?, secondary? }
 *                           href: renders as <a role="button">
 *                           dataAttrs: object of data-* attrs rendered on <button>
 *   footerLinkHtml (string) — optional HTML for a footer link (e.g. partner link)
 *   variant     (string)  — "trait" | "bond" — controls accent class
 *   extraClass  (string)  — optional additional CSS class(es) for the root <li>
 *
 * Usage:
 *   var html = window.components.expandableItem.render(props);
 *   // Insert html into DOM...
 *   window.components.expandableItem.attach(containerEl);
 *
 * render() returns an HTML string.
 * attach() wires click (and keyboard) toggle listeners to all .exp-item
 * elements inside the given container.
 *
 * Multiple calls to attach() on the same container are safe — uses a
 * data-exp-attached flag to avoid double-binding.
 */

window.components = window.components || {};

window.components.expandableItem = (function () {
  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  var _esc = function (str) { return window.utils.esc(str); };

  /**
   * Build the data-* attribute string from a plain object.
   * @param {object} attrs — e.g. { "data-action": "recharge-trait", "data-trait-id": "..." }
   * @returns {string}
   */
  function _dataAttrs(attrs) {
    if (!attrs || typeof attrs !== "object") return "";
    var parts = [];
    var keys = Object.keys(attrs);
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      parts.push(_esc(k) + '="' + _esc(attrs[k]) + '"');
    }
    return parts.length ? " " + parts.join(" ") : "";
  }

  /**
   * Build a single action button or link.
   * @param {object} action — { label, href?, dataAttrs?, secondary? }
   * @returns {string} HTML
   */
  function _buildAction(action) {
    var cls = "exp-item__action-btn" + (action.secondary ? " exp-item__action-btn--secondary" : "");
    if (action.href) {
      return (
        '<a href="' + _esc(action.href) + '"' +
        '   class="' + cls + '"' +
        '   role="button">' +
          _esc(action.label) +
        '</a>'
      );
    }
    return (
      '<button class="' + cls + '"' +
      _dataAttrs(action.dataAttrs) +
      '>' +
        _esc(action.label) +
      '</button>'
    );
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  return {
    /**
     * Render an expandable item to an HTML string.
     *
     * @param {object} props
     * @param {string} props.id
     * @param {string} props.name
     * @param {string} [props.dotsHtml]
     * @param {string} [props.badgeHtml]
     * @param {string} [props.description]
     * @param {Array}  [props.actions]
     * @param {string} [props.footerLinkHtml]
     * @param {string} [props.variant] — "trait" | "bond"
     * @returns {string}
     */
    render: function (props) {
      var id          = props.id          || "";
      var name        = props.name        || "";
      var dotsHtml    = props.dotsHtml    || "";
      var badgeHtml   = props.badgeHtml   || "";
      var description = props.description || "";
      var actions     = props.actions     || [];
      var footerLink  = props.footerLinkHtml || "";
      var variant     = props.variant === "bond" ? "bond" : "trait";
      var extraClass  = props.extraClass  || "";

      var triggerId = "exp-trigger-" + _esc(id);
      var bodyId    = "exp-body-"    + _esc(id);

      // Action buttons
      var actionsHtml = "";
      if (actions.length > 0) {
        actionsHtml = '<div class="exp-item__actions">';
        for (var i = 0; i < actions.length; i++) {
          actionsHtml += _buildAction(actions[i]);
        }
        actionsHtml += '</div>';
      }

      var rootClass = "exp-item exp-item--" + variant + (extraClass ? " " + extraClass : "");

      return (
        '<li class="' + rootClass + '"' +
        '    data-exp-id="' + _esc(id) + '">' +
          '<button class="exp-item__trigger"' +
          '        id="' + triggerId + '"' +
          '        aria-expanded="false"' +
          '        aria-controls="' + bodyId + '">' +
            '<span class="exp-item__header">' +
              '<span class="exp-item__name">' + _esc(name) + '</span>' +
              (badgeHtml ? '<span class="exp-item__badge">' + badgeHtml + '</span>' : '') +
              (dotsHtml  ? '<span class="exp-item__dots">'  + dotsHtml  + '</span>' : '') +
            '</span>' +
            '<span class="exp-item__chevron" aria-hidden="true">\u203a</span>' +
          '</button>' +
          '<div class="exp-item__body"' +
          '     id="' + bodyId + '"' +
          '     role="region"' +
          '     aria-labelledby="' + triggerId + '"' +
          '     hidden>' +
            (description
              ? '<p class="exp-item__desc">' + _esc(description) + '</p>'
              : '') +
            (footerLink ? '<div class="exp-item__footer-link">' + footerLink + '</div>' : '') +
            actionsHtml +
          '</div>' +
        '</li>'
      );
    },

    /**
     * Wire expand/collapse toggle listeners to all .exp-item elements inside
     * container. Safe to call multiple times — uses data-exp-attached flag.
     *
     * @param {HTMLElement} container
     */
    attach: function (container) {
      if (!container) return;
      var items = container.querySelectorAll(".exp-item");
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (item.getAttribute("data-exp-attached")) continue;
        item.setAttribute("data-exp-attached", "1");

        (function (li) {
          var trigger = li.querySelector(".exp-item__trigger");
          var body    = li.querySelector(".exp-item__body");
          if (!trigger || !body) return;

          function toggle() {
            var expanded = trigger.getAttribute("aria-expanded") === "true";
            if (expanded) {
              trigger.setAttribute("aria-expanded", "false");
              body.hidden = true;
              li.classList.remove("exp-item--open");
            } else {
              trigger.setAttribute("aria-expanded", "true");
              body.hidden = false;
              li.classList.add("exp-item--open");
            }
          }

          trigger.addEventListener("click", toggle);

          trigger.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              toggle();
            }
          });
        })(item);
      }
    },
  };
})();
