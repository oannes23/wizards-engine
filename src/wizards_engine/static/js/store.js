/* Wizards Engine — Alpine.js global store
 *
 * Registered as Alpine.store('app', ...) during alpine:init.
 * Provides reactive auth state consumed by views and the router.
 *
 * Properties:
 *   user         — full user object from GET /api/v1/me, or null
 *   role         — 'gm' | 'player' | null
 *   character_id — ULID of the user's linked character, or null
 *   loading      — true while the initial /me check is in flight
 *   error        — string for the toast/banner, or null
 *   _polls       — internal registry: {key → {url, intervalMs, callback, timerId}}
 *                  Not intended for direct use by views.
 *
 * Methods:
 *   init()               — called on startup; checks auth via GET /me
 *   setUser(userData)    — populate state from /me response
 *   clearUser()          — wipe all auth state (on logout or 401)
 *   isOwner(characterId) — true if character_id matches the argument
 *   registerPoll(key, {url, intervalMs, callback})
 *                        — start a named polling interval; replaces any
 *                          existing poll with the same key
 *   unregisterPoll(key)  — stop and remove a named polling interval
 *
 * Getter (Alpine-compatible computed):
 *   isGm                 — true when role === 'gm'
 *
 * Visibility-change handler (attached inside alpine:init):
 *   Pauses all polls when the browser tab is hidden, resumes when visible.
 *   Saves battery on idle phones at the game table.
 */

document.addEventListener("alpine:init", function () {
  Alpine.store("app", {
    user: null,
    role: null,
    character_id: null,
    loading: true,
    error: null,

    // Internal polling registry. Keys are arbitrary strings chosen by the
    // caller (e.g. 'character-sheet', 'gm-queue'). Values are:
    //   {url, intervalMs, callback, timerId}
    // Not reactive — Alpine does not need to observe individual timer IDs.
    _polls: {},

    /**
     * Bootstrap auth check. Called once on page load.
     * Attempts GET /api/v1/me to determine if a valid session exists.
     * Sets user state on success; leaves state cleared on 401 (api.js
     * handles the redirect to #/login via the 401 handler).
     */
    init: function () {
      var store = this;
      // api.js is loaded before store.js — safe to call immediately
      api
        .get("/api/v1/me")
        .then(function (data) {
          store.setUser(data);
          // Signal the nav component to re-render now that user is known.
          // nav.mount() runs synchronously during alpine:initialized (before
          // this async callback fires), so store.user is still null at mount
          // time and the nav is hidden. Dispatching nav:refresh here causes
          // nav._render() to run again with the populated user state.
          document.dispatchEvent(new CustomEvent("nav:refresh"));
        })
        .catch(function () {
          // 401 is handled by api.js (redirect + clearUser call).
          // Other errors leave loading = false with null user.
          store.clearUser();
        })
        .finally(function () {
          store.loading = false;
        });
    },

    /**
     * Populate store from a /me response object.
     * @param {object} userData — {id, display_name, role, character_id}
     */
    setUser: function (userData) {
      this.user = userData;
      this.role = userData.role || null;
      this.character_id = userData.character_id || null;
    },

    /**
     * Clear all auth state. Called on logout or 401 redirect.
     */
    clearUser: function () {
      this.user = null;
      this.role = null;
      this.character_id = null;
    },

    /**
     * Returns true if the given characterId matches the logged-in
     * user's linked character. Used for ownership checks in views.
     * @param {string} characterId
     */
    isOwner: function (characterId) {
      return this.character_id !== null && this.character_id === characterId;
    },

    /**
     * Computed helper — true when the current user has the GM role.
     * Alpine does not support native getters on plain store objects in v3,
     * so this is a zero-argument method; call as $store.app.isGm().
     */
    isGm: function () {
      return this.role === "gm";
    },

    /**
     * Register a named polling interval. On each tick, calls api.get(url)
     * and passes the result to callback. Errors are logged to the console
     * and do not crash the app — the next tick fires on schedule.
     *
     * If a poll with the same key already exists it is unregistered first,
     * so callers can safely call registerPoll again to update config.
     *
     * @param {string} key        — unique name for this poll (e.g. 'gm-queue')
     * @param {object} config
     * @param {string} config.url         — endpoint to fetch
     * @param {number} config.intervalMs  — polling interval in milliseconds
     * @param {function} config.callback  — called with the parsed JSON response
     */
    registerPoll: function (key, config) {
      // Remove any existing poll with this key before creating a new one.
      if (this._polls[key]) {
        this.unregisterPoll(key);
      }

      var store = this;
      var url = config.url;
      var intervalMs = config.intervalMs;
      var callback = config.callback;

      var timerId = setInterval(function () {
        api
          .get(url, { silent: true })
          .then(function (data) {
            callback(data);
          })
          .catch(function (err) {
            // Log poll errors silently — do not show a toast (would be noisy).
            // The next interval will fire on schedule.
            console.warn("[poll:" + key + "] error fetching " + url, err);
          });
      }, intervalMs);

      this._polls[key] = {
        url: url,
        intervalMs: intervalMs,
        callback: callback,
        timerId: timerId,
      };
    },

    /**
     * Stop and remove a named polling interval.
     * Safe to call if the key does not exist.
     *
     * @param {string} key — the key passed to registerPoll
     */
    unregisterPoll: function (key) {
      var entry = this._polls[key];
      if (!entry) {
        return;
      }
      clearInterval(entry.timerId);
      delete this._polls[key];
    },

    /**
     * Pause all active polling intervals without removing their configs.
     * Used internally by the visibilitychange handler. Saves battery on
     * idle phones at the game table.
     */
    _pauseAllPolls: function () {
      var polls = this._polls;
      Object.keys(polls).forEach(function (key) {
        clearInterval(polls[key].timerId);
        polls[key].timerId = null;
      });
    },

    /**
     * Resume all polling intervals that were paused by _pauseAllPolls.
     * Fires an immediate fetch for each poll (so data refreshes right when
     * the user returns to the tab), then restarts setInterval.
     */
    _resumeAllPolls: function () {
      var polls = this._polls;
      Object.keys(polls).forEach(function (key) {
        var entry = polls[key];
        if (entry.timerId !== null) {
          // Already running — skip.
          return;
        }
        var url = entry.url;
        var callback = entry.callback;
        // Immediate fetch on resume so data is fresh right away
        api
          .get(url, { silent: true })
          .then(function (data) {
            callback(data);
          })
          .catch(function (err) {
            console.warn("[poll:" + key + "] error fetching " + url, err);
          });
        // Restart the periodic interval
        entry.timerId = setInterval(function () {
          api
            .get(url, { silent: true })
            .then(function (data) {
              callback(data);
            })
            .catch(function (err) {
              console.warn("[poll:" + key + "] error fetching " + url, err);
            });
        }, entry.intervalMs);
      });
    },
  });

  // Visibility-change handler: pause all polls when the browser tab goes
  // hidden, resume them when the tab becomes visible again. This reduces
  // battery drain on idle phones at the game table.
  document.addEventListener("visibilitychange", function () {
    var store = Alpine.store("app");
    if (document.visibilityState === "hidden") {
      store._pauseAllPolls();
    } else {
      store._resumeAllPolls();
    }
  });
});
