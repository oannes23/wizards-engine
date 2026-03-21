/* Wizards Engine — API client
 *
 * Wraps fetch() with:
 *   - credentials: 'same-origin' on every request (cookie auth)
 *   - JSON request/response handling
 *   - Error envelope parsing: {error: {code, message}} from the server
 *   - Toast dispatch on error
 *   - 401 → clears store state, redirects to #/login
 *
 * Usage (plain globals, no ES module syntax):
 *   api.get('/api/v1/me')
 *   api.post('/api/v1/auth/login', {code: '...'})
 *   api.patch('/api/v1/me', {display_name: '...'})
 *   api.del('/api/v1/game/invites/01ABC...')
 */

var api = (function () {
  /**
   * Extract a human-readable message from an error response body.
   * The server wraps errors as {error: {code, message}} per api-conventions spec.
   */
  function _extractErrorMessage(body) {
    if (body && body.error) {
      return body.error.message || body.error.code || "An error occurred.";
    }
    if (body && body.detail) {
      // Fall back to FastAPI plain-string detail
      return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
    return "An unexpected error occurred.";
  }

  /**
   * Dispatch the custom 'api:error' event so any mounted toast/banner
   * can react without tight coupling to a specific DOM element.
   */
  function _dispatchError(message, status) {
    var event = new CustomEvent("api:error", {
      detail: { message: message, status: status },
      bubbles: true,
    });
    document.dispatchEvent(event);
  }

  /**
   * Handle a non-ok response. Parses the body, dispatches an error event
   * (unless silent), and handles 401 by redirecting to #/login.
   *
   * Returns a rejected Promise so callers can optionally catch further.
   */
  async function _handleError(response, silent) {
    var body = null;
    try {
      body = await response.json();
    } catch (_) {
      // Response body is not JSON — treat as opaque error
    }

    var message = _extractErrorMessage(body);

    if (response.status === 401) {
      // Clear Alpine store state if Alpine is available
      if (typeof Alpine !== "undefined" && Alpine.store("app")) {
        Alpine.store("app").clearUser();
      }
      // Don't redirect away from public routes that don't require auth
      var hash = window.location.hash;
      var isPublic = hash === "#/setup" || hash === "#/login" || hash === "#/join";
      if (!isPublic) {
        // Redirect to login — use replace so back-button does not loop
        window.location.replace("#/login");
      }
      // Don't show toast for 401 — the redirect itself communicates session expiry
    } else if (!silent) {
      _dispatchError(message, response.status);
    }
    var err = new Error(message);
    err.status = response.status;
    err.body = body;
    return Promise.reject(err);
  }

  /**
   * Core request helper.
   * @param {object} [opts] — optional: { silent: true } suppresses toast on error
   */
  async function _request(method, url, body, opts) {
    var options = {
      method: method,
      credentials: "same-origin",
      headers: {},
    };

    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    var response;
    try {
      response = await fetch(url, options);
    } catch (networkError) {
      var message = "Network error — is the server reachable?";
      if (!(opts && opts.silent)) {
        _dispatchError(message, null);
      }
      return Promise.reject(new Error(message));
    }

    if (!response.ok) {
      return _handleError(response, opts && opts.silent);
    }

    // 204 No Content and similar responses have no body
    if (response.status === 204) {
      return null;
    }

    try {
      return await response.json();
    } catch (_) {
      // Response was ok but had no parseable body
      return null;
    }
  }

  return {
    /**
     * GET request. Returns parsed JSON on success.
     * @param {string} url
     * @param {object} [opts] — optional: { silent: true } suppresses toast on error
     */
    get: function (url, opts) {
      return _request("GET", url, undefined, opts);
    },

    /**
     * POST request with JSON body. Returns parsed JSON on success.
     * @param {string} url
     * @param {object} body
     */
    post: function (url, body) {
      return _request("POST", url, body);
    },

    /**
     * PATCH request with JSON body. Returns parsed JSON on success.
     * @param {string} url
     * @param {object} body
     */
    patch: function (url, body) {
      return _request("PATCH", url, body);
    },

    /**
     * DELETE request. Returns null on 204, parsed JSON otherwise.
     * @param {string} url
     */
    del: function (url) {
      return _request("DELETE", url);
    },
  };
})();
