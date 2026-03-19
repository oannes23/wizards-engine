/* Wizards Engine — Hash-based router
 *
 * Listens to 'hashchange' events and renders placeholder view content
 * into the #view element. Actual view components are added in later stories.
 *
 * Route table maps hash paths to view loader functions.
 * Unknown routes fall through to the default redirect based on role.
 *
 * Public API (via window.router):
 *   router.navigate(hash) — programmatic navigation, e.g. router.navigate('#/gm')
 *   router.start()        — begin listening for hashchange events + render current hash
 */

var router = (function () {
  // ---------------------------------------------------------------------------
  // View placeholder helpers
  // ---------------------------------------------------------------------------

  /**
   * Render a titled placeholder into the #view container.
   * Later stories replace these with real view components.
   */
  function _placeholder(title) {
    return function () {
      var el = document.getElementById("view");
      if (!el) return;
      el.textContent = "";
      var h2 = document.createElement("h2");
      h2.textContent = title;
      el.appendChild(h2);
    };
  }

  // ---------------------------------------------------------------------------
  // Route table
  // ---------------------------------------------------------------------------

  // Keys are the path portion of the hash (without the leading '#').
  // Values are view loader functions; () => void.
  var routes = {
    "/login":        function () { if (typeof views !== "undefined" && views.login)  { views.login();  } else { _placeholder("Login")();  } },
    "/setup":        function () { if (typeof views !== "undefined" && views.setup)  { views.setup();  } else { _placeholder("Setup")();  } },
    "/join":         function () { if (typeof views !== "undefined" && views.join)   { views.join();   } else { _placeholder("Join")();   } },
    "/":             _placeholder("Dashboard"),
    "/character":    _placeholder("Character Sheet"),
    "/proposals":    _placeholder("Proposals"),
    "/world":        _placeholder("World"),
    "/session":      _placeholder("Session"),
    "/profile":      _placeholder("Profile"),
    "/gm":           _placeholder("GM Dashboard"),
    "/gm/queue":     _placeholder("GM Queue"),
    "/gm/sessions":      _placeholder("GM Sessions"),
    "/gm/sessions/new":  _placeholder("New Session"),
    "/gm/world":     _placeholder("GM World"),
    "/gm/feed":            _placeholder("GM Feed"),
    "/gm/feed/silent":     _placeholder("GM Silent Feed"),
    "/gm/more":            _placeholder("GM More"),
    "/gm/character":       _placeholder("GM Character Sheet"),
    "/gm/actions":         _placeholder("GM Direct Actions"),
    "/gm/players":         _placeholder("Player Roster"),
    "/gm/invites":         _placeholder("Invite Management"),
    "/gm/trait-templates": _placeholder("Trait Template Catalog"),
    "/gm/clocks":          _placeholder("Clock Management"),
    "/character/edit":     _placeholder("Edit Character"),
    "/feed/starred":       _placeholder("Starred Feed"),
  };

  // ---------------------------------------------------------------------------
  // Routing logic
  // ---------------------------------------------------------------------------

  /**
   * Parse window.location.hash into a normalised path string.
   * '' or '#' → '/'
   * '#/character' → '/character'
   */
  function _currentPath() {
    var hash = window.location.hash;
    if (!hash || hash === "#") return "/";
    // Strip the leading '#'
    return hash.slice(1) || "/";
  }

  /**
   * Determine the role-appropriate default hash for unknown or empty routes.
   * Reads from the Alpine store if available; falls back to '#/login'.
   */
  function _defaultHash() {
    if (typeof Alpine !== "undefined") {
      var store = Alpine.store("app");
      if (store) {
        if (store.role === "gm") return "#/gm";
        if (store.role === "player") return "#/";
      }
    }
    return "#/login";
  }

  /**
   * Resolve and execute the loader for a given path.
   * Falls back to the default route for unknown paths.
   */
  function _dispatch(path) {
    var loader = routes[path];
    if (loader) {
      loader();
      return;
    }

    // Unknown route — redirect to role-appropriate default
    var dest = _defaultHash();
    // Avoid an infinite redirect loop if the default itself is unknown
    var destPath = dest.slice(1) || "/";
    if (destPath !== path) {
      window.location.replace(dest);
    }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  return {
    /**
     * Navigate programmatically to a given hash.
     * @param {string} hash — e.g. '#/character'
     */
    navigate: function (hash) {
      window.location.hash = hash;
    },

    /**
     * Start the router: attach hashchange listener and dispatch the
     * current hash immediately so the initial view is rendered.
     */
    start: function () {
      window.addEventListener("hashchange", function () {
        _dispatch(_currentPath());
      });

      // Render the current hash on startup
      _dispatch(_currentPath());
    },
  };
})();
