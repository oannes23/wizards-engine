/* Wizards Engine — Hash-based router
 *
 * Listens to 'hashchange' events and renders placeholder view content
 * into the #view element. Actual view components are added in later stories.
 *
 * Route table maps hash paths to view loader functions.
 * Unknown routes fall through to the default redirect based on role.
 *
 * Parameterized routes:
 *   After checking static routes, the router checks paramRoutes — an ordered
 *   list of pattern/handler pairs. Patterns use :param syntax which is
 *   converted to a regex for matching. More specific patterns must come first.
 *   Example: "/proposals/:id/edit" must be listed before "/proposals/:id".
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
    "/":             function () { if (typeof views !== "undefined" && views.feed)          { views.feed();          } else { _placeholder("Dashboard")(); } },
    "/character":    function () { if (typeof views !== "undefined" && views.character)  { views.character();  } else { _placeholder("Character Sheet")(); } },
    "/proposals":    function () { if (typeof views !== "undefined" && views.proposalsList) { views.proposalsList(); } else { _placeholder("Proposals")(); } },
    "/proposals/new": function () { if (typeof views !== "undefined" && views.proposalSubmit) { views.proposalSubmit(); } else { _placeholder("New Proposal")(); } },
    "/world":        function () { if (typeof views !== "undefined" && views.world)   { views.world();   } else { _placeholder("World")();   } },
    "/session":      _placeholder("Session"),
    "/profile":      function () { if (typeof views !== "undefined" && views.profile) { views.profile(); } else { _placeholder("Profile")(); } },
    "/gm":           function () { if (typeof views !== "undefined" && views.gmDashboard) { views.gmDashboard(); } else { _placeholder("GM Dashboard")(); } },
    "/gm/queue":     function () { if (typeof views !== "undefined" && views.gmQueue)  { views.gmQueue();  } else { _placeholder("GM Queue")();     } },
    "/gm/sessions":      function () { if (typeof views !== "undefined" && views.gmSessions)  { views.gmSessions();  } else { _placeholder("GM Sessions")(); } },
    "/gm/sessions/new":  function () { if (typeof views !== "undefined" && views.gmSessions)  { views.gmSessions({ mode: "new" });  } else { _placeholder("New Session")(); } },
    "/gm/world":     function () { if (typeof views !== "undefined" && views.world)   { views.world();   } else { _placeholder("GM World")();   } },
    "/gm/feed":            function () { if (typeof views !== "undefined" && views.gmFeed)        { views.gmFeed();        } else { _placeholder("GM Feed")(); } },
    "/gm/feed/silent":     function () { if (typeof views !== "undefined" && views.gmFeedSilent)  { views.gmFeedSilent();  } else { _placeholder("GM Silent Feed")(); } },
    "/gm/more":            function () { window.location.replace("#/gm/players"); },
    "/gm/character":       function () { if (typeof views !== "undefined" && views.character)  { views.character();  } else { _placeholder("GM Character Sheet")(); } },
    "/gm/actions":         function () { if (typeof views !== "undefined" && views.gmActions)    { views.gmActions();    } else { _placeholder("GM Direct Actions")(); } },
    "/gm/players":         function () { if (typeof views !== "undefined" && views.gmPlayers)   { views.gmPlayers();   } else { _placeholder("Player Roster")(); } },
    "/gm/invites":         function () { if (typeof views !== "undefined" && views.gmPlayers)   { views.gmPlayers({ tab: "invites" });   } else { _placeholder("Invite Management")(); } },
    "/gm/trait-templates": function () { if (typeof views !== "undefined" && views.gmTemplates) { views.gmTemplates(); } else { _placeholder("Trait Template Catalog")(); } },
    "/gm/clocks":          function () { if (typeof views !== "undefined" && views.gmClocks)    { views.gmClocks();    } else { _placeholder("Clock Management")(); } },
    "/character/edit":     function () { if (typeof views !== "undefined" && views.characterEdit) { views.characterEdit(); } else { _placeholder("Edit Character")(); } },
    "/feed/starred":       function () { if (typeof views !== "undefined" && views.feedStarred)  { views.feedStarred();  } else { _placeholder("Starred Feed")(); } },
  };

  // ---------------------------------------------------------------------------
  // Parameterized routes
  // ---------------------------------------------------------------------------

  /**
   * Parameterized route table.
   * Order matters — more specific patterns must come before less specific ones.
   * Each entry: { pattern: "/segment/:param/...", handler: function(params) {...} }
   *
   * A pattern like "/proposals/:id/edit" converts to a regex that extracts
   * the :id segment into params.id.
   */
  var paramRoutes = [
    {
      pattern: "/gm/sessions/:id/timeline",
      handler: function (params) {
        if (typeof views !== "undefined" && views.sessionDetail) {
          views.sessionDetail(params.id, { tab: "timeline" });
        } else { _placeholder("Session Timeline")(); }
      },
    },
    {
      pattern: "/gm/sessions/:id/edit",
      handler: function (params) {
        if (typeof views !== "undefined" && views.sessionDetail) {
          views.sessionDetail(params.id, { edit: true });
        } else { _placeholder("Edit Session")(); }
      },
    },
    {
      pattern: "/gm/sessions/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.sessionDetail) {
          views.sessionDetail(params.id);
        } else { _placeholder("Session Detail")(); }
      },
    },
    {
      // More specific: /proposals/:id/edit must come before /proposals/:id
      pattern: "/proposals/:id/edit",
      handler: function (params) {
        if (typeof views !== "undefined" && views.proposalDetail) {
          views.proposalDetail(params.id, { edit: true });
        } else {
          _placeholder("Edit Proposal")();
        }
      },
    },
    {
      pattern: "/proposals/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.proposalDetail) {
          views.proposalDetail(params.id);
        } else {
          _placeholder("Proposal Detail")();
        }
      },
    },
    {
      pattern: "/world/characters/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.worldDetail) {
          views.worldDetail("characters", params.id);
        } else {
          _placeholder("Character Detail")();
        }
      },
    },
    {
      pattern: "/world/groups/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.worldDetail) {
          views.worldDetail("groups", params.id);
        } else {
          _placeholder("Group Detail")();
        }
      },
    },
    {
      pattern: "/world/locations/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.worldDetail) {
          views.worldDetail("locations", params.id);
        } else {
          _placeholder("Location Detail")();
        }
      },
    },
    {
      pattern: "/world/stories/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.storyDetail) {
          views.storyDetail(params.id);
        } else {
          _placeholder("Story Detail")();
        }
      },
    },
    {
      pattern: "/gm/world/characters/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.worldDetail) {
          views.worldDetail("characters", params.id);
        } else {
          _placeholder("Character Detail")();
        }
      },
    },
    {
      pattern: "/gm/world/groups/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.worldDetail) {
          views.worldDetail("groups", params.id);
        } else {
          _placeholder("Group Detail")();
        }
      },
    },
    {
      pattern: "/gm/world/locations/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.worldDetail) {
          views.worldDetail("locations", params.id);
        } else {
          _placeholder("Location Detail")();
        }
      },
    },
    {
      pattern: "/gm/world/stories/:id",
      handler: function (params) {
        if (typeof views !== "undefined" && views.storyDetail) {
          views.storyDetail(params.id);
        } else {
          _placeholder("Story Detail")();
        }
      },
    },
    {
      pattern: "/gm/traits/:id/edit",
      handler: function (params) {
        if (typeof views !== "undefined" && views.traitEdit) {
          views.traitEdit(params.id);
        } else {
          _placeholder("Edit Trait")();
        }
      },
    },
    {
      pattern: "/gm/bonds/:id/edit",
      handler: function (params) {
        if (typeof views !== "undefined" && views.bondEdit) {
          views.bondEdit(params.id);
        } else {
          _placeholder("Edit Bond")();
        }
      },
    },
  ];

  /**
   * Compile a pattern string into a regex and an ordered list of param names.
   * "/proposals/:id/edit" → { regex: /^\/proposals\/([^/]+)\/edit$/, params: ["id"] }
   * @param {string} pattern
   * @returns {{ regex: RegExp, params: string[] }}
   */
  function _compilePattern(pattern) {
    var paramNames = [];
    var regexStr = pattern.replace(/:([a-zA-Z_][a-zA-Z0-9_]*)/g, function (_, name) {
      paramNames.push(name);
      return "([^/]+)";
    });
    return {
      regex: new RegExp("^" + regexStr + "$"),
      params: paramNames,
    };
  }

  /**
   * Try to match a path against the parameterized route table.
   * Returns the handler bound with extracted params, or null if no match.
   * @param {string} path
   * @returns {function|null}
   */
  function _matchParamRoute(path) {
    for (var i = 0; i < paramRoutes.length; i++) {
      var route = paramRoutes[i];
      var compiled = _compilePattern(route.pattern);
      var match = compiled.regex.exec(path);
      if (match) {
        var params = {};
        for (var j = 0; j < compiled.params.length; j++) {
          params[compiled.params[j]] = decodeURIComponent(match[j + 1]);
        }
        var handler = route.handler;
        var capturedParams = params;
        return function () { handler(capturedParams); };
      }
    }
    return null;
  }

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
   * Checks static routes first, then parameterized routes.
   * Falls back to the default route for unknown paths.
   */
  function _dispatch(path) {
    // 1. Check static routes (exact match, fastest path)
    var loader = routes[path];
    if (loader) {
      loader();
      return;
    }

    // 2. Check parameterized routes (pattern match)
    var paramLoader = _matchParamRoute(path);
    if (paramLoader) {
      paramLoader();
      return;
    }

    // 3. Unknown route — redirect to role-appropriate default
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
