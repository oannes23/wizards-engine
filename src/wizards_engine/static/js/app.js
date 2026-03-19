/* Wizards Engine — Alpine.js app initialisation
 *
 * This file is loaded last (after api.js, store.js, router.js).
 * On alpine:init the store and router are both available.
 *
 * Responsibilities:
 *   1. Call store.app.init() to check auth status via GET /api/v1/me
 *   2. Start the hash router
 *   3. Wire up the api:error event to the error toast/banner element
 *   4. Wire up the api:success event to the success toast element
 */

// ---------------------------------------------------------------------------
// Error toast wiring
// ---------------------------------------------------------------------------
// Runs immediately (not inside alpine:init) so it is active before any API
// call fires — including the /me check triggered from the store.
(function () {
  var toast = document.getElementById("api-toast");
  var toastMsg = document.getElementById("api-toast-message");
  var toastClose = document.getElementById("api-toast-close");

  if (!toast || !toastMsg || !toastClose) return;

  var hideTimer = null;

  document.addEventListener("api:error", function (event) {
    var message = (event.detail && event.detail.message) || "An error occurred.";
    toastMsg.textContent = message;
    toast.hidden = false;

    // Auto-hide after 6 seconds
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function () {
      toast.hidden = true;
    }, 6000);
  });

  toastClose.addEventListener("click", function () {
    clearTimeout(hideTimer);
    toast.hidden = true;
  });
})();

// ---------------------------------------------------------------------------
// Success toast wiring
// ---------------------------------------------------------------------------
(function () {
  var toast = document.getElementById("api-success-toast");
  var toastMsg = document.getElementById("api-success-toast-message");

  if (!toast || !toastMsg) return;

  var hideTimer = null;

  document.addEventListener("api:success", function (event) {
    var message = (event.detail && event.detail.message) || "Done.";
    toastMsg.textContent = message;
    toast.hidden = false;

    // Auto-hide after 3 seconds
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function () {
      toast.hidden = true;
    }, 3000);
  });
})();

// ---------------------------------------------------------------------------
// Alpine init — store bootstrap + router start
// ---------------------------------------------------------------------------
document.addEventListener("alpine:init", function () {
  console.log("[wizards-engine] app loaded");
});

// Start the router and trigger the store auth check after Alpine has
// initialised the store (alpine:init handlers run synchronously, then
// Alpine processes x-data attributes and calls store init hooks).
// Using 'alpine:initialized' ensures all stores are registered and reactive.
document.addEventListener("alpine:initialized", function () {
  // Kick off the /me check to populate $store.app.user / role / character_id
  if (typeof Alpine !== "undefined" && Alpine.store("app")) {
    Alpine.store("app").init();
  }

  // Start hash routing — renders the initial view and listens for changes
  if (typeof router !== "undefined") {
    router.start();
  }

  // Mount the navigation component — renders the tab bar once auth state is
  // known. nav.js listens to hashchange and nav:refresh events for updates.
  if (window.components && window.components.nav) {
    window.components.nav.mount();
  }
});
