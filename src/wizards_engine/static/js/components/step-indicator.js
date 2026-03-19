/* Wizards Engine — Step Indicator component
 *
 * Renders a numbered step progress indicator showing which step the user
 * is currently on in a multi-step flow.
 *
 * Usage (imperative):
 *   var el = window.components.stepIndicator.render({
 *     steps: ['Choose Action', 'Fill Details', 'Review'],
 *     current: 1   // 1-based index of the active step
 *   });
 *   document.getElementById('some-container').appendChild(el);
 *
 * Registers as: window.components.stepIndicator
 */

window.components = window.components || {};

window.components.stepIndicator = (function () {
  /**
   * Build the step indicator DOM element.
   *
   * @param {object} config
   * @param {string[]} config.steps   — array of step label strings
   * @param {number}   config.current — 1-based index of the active step
   * @returns {HTMLElement}
   */
  function render(config) {
    var steps = config.steps || [];
    var current = config.current || 1;

    var nav = document.createElement("nav");
    nav.className = "step-indicator";
    nav.setAttribute("aria-label", "Progress");

    var ol = document.createElement("ol");
    ol.className = "step-indicator__list";

    for (var i = 0; i < steps.length; i++) {
      var stepNum = i + 1;
      var li = document.createElement("li");
      li.className = "step-indicator__step";

      if (stepNum < current) {
        li.classList.add("step-indicator__step--done");
        li.setAttribute("aria-label", steps[i] + " (complete)");
      } else if (stepNum === current) {
        li.classList.add("step-indicator__step--active");
        li.setAttribute("aria-current", "step");
        li.setAttribute("aria-label", steps[i] + " (current)");
      } else {
        li.setAttribute("aria-label", steps[i] + " (upcoming)");
      }

      // Number bubble
      var bubble = document.createElement("span");
      bubble.className = "step-indicator__bubble";
      bubble.setAttribute("aria-hidden", "true");
      bubble.textContent = String(stepNum);

      // Label
      var label = document.createElement("span");
      label.className = "step-indicator__label";
      label.textContent = steps[i];

      // Connector line (after all but the last step)
      var item = document.createElement("span");
      item.className = "step-indicator__item";
      item.appendChild(bubble);
      item.appendChild(label);

      li.appendChild(item);

      if (i < steps.length - 1) {
        var connector = document.createElement("span");
        connector.className = "step-indicator__connector";
        connector.setAttribute("aria-hidden", "true");
        li.appendChild(connector);
      }

      ol.appendChild(li);
    }

    nav.appendChild(ol);
    return nav;
  }

  return {
    /**
     * Render a step indicator element.
     *
     * @param {object} config
     * @param {string[]} config.steps   — step labels
     * @param {number}   config.current — 1-based active step index
     * @returns {HTMLElement}
     */
    render: render,
  };
})();
