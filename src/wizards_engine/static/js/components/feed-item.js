/* Wizards Engine — FeedItem component
 *
 * Renders a single item in the event/story feed.
 * Discriminated union on `type`: "event" | "story_entry"
 *
 * Props:
 *   item (object) — feed item from the API
 *   type (string) — "event" | "story_entry"
 *
 * Event items:
 *   - actor name, event type label (human-readable), narrative, targets,
 *     relative timestamp
 *   - Color coding by actor_type: player (default), gm (accent), system (muted)
 *
 * Story entry items:
 *   - author name, story name, entry text, timestamp
 *
 * Relative timestamps: "just now", "2m ago", "1h ago", "3d ago"
 *
 * Usage:
 *   components.feedItem.render({ item: eventObj, type: 'event' })
 *
 * Returns an HTML string. No interactive state — purely presentational.
 */

window.components = window.components || {};

window.components.feedItem = (function () {
  // --------------------------------------------------------------------------
  // Constants
  // --------------------------------------------------------------------------

  // Human-readable labels for event type codes from the API.
  // Keys use the actual {domain}.{action} convention emitted by the backend.
  var EVENT_TYPE_LABELS = {
    // Proposal lifecycle
    "proposal.approved":                  "proposal approved",
    "proposal.rejected":                  "proposal rejected",
    "proposal.revised":                   "proposal revised",
    // Character events
    "character.stress_changed":           "stress changed",
    "character.gnosis_changed":           "gnosis changed",
    "character.meter_updated":            "meter updated",
    "character.skill_changed":            "skill changed",
    "character.magic_stat_changed":       "magic stat changed",
    "character.updated":                  "character updated",
    "character.resolve_trauma_generated": "trauma resolution pending",
    // Session events
    "session.started":                    "session started",
    "session.ended":                      "session ended",
    "session.ft_distributed":             "free time distributed",
    "session.plot_distributed":           "plot points distributed",
    "session.participant_added":          "participant added",
    // Clock events
    "clock.advanced":                     "clock advanced",
    "clock.resolve_generated":            "clock resolution pending",
    // Bond events
    "bond.created":                       "bond created",
    "bond.charges_changed":               "bond charges changed",
    "bond.updated":                       "bond updated",
    "bond.retired":                       "bond retired",
    // Trait events
    "trait.created":                      "trait created",
    "trait.recharged":                    "trait recharged",
    "trait.updated":                      "trait updated",
    "trait.retired":                      "trait retired",
    // Magic effect events
    "magic.effect_created":               "effect created",
    "magic.effect_charged":               "effect charged",
    "magic.effect_updated":               "effect updated",
    "magic.effect_retired":               "effect retired",
    // Group / location / world-object events
    "group.updated":                      "group updated",
    "location.updated":                   "location updated",
  };

  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  // Delegate to shared utils (window.utils — loaded via utils.js before this file).
  var _relativeTime = function (s) { return window.utils.relativeTime(s); };

  /**
   * Map an actor_type string to a BEM modifier class.
   * @param {string} actorType
   * @returns {string} modifier suffix
   */
  function _actorModifier(actorType) {
    switch (String(actorType || "").toLowerCase()) {
      case "gm":     return "gm";
      case "system": return "system";
      default:       return "player";
    }
  }

  /**
   * Resolve a human-readable label for an event type code.
   * Falls back to a formatted version of the raw code.
   * @param {string} eventType
   * @returns {string}
   */
  function _eventTypeLabel(eventType) {
    if (EVENT_TYPE_LABELS[eventType]) {
      return EVENT_TYPE_LABELS[eventType];
    }
    // Fallback: replace dots and underscores with spaces, then title-case
    return String(eventType || "action")
      .replace(/[._]/g, " ")
      .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  /**
   * Build a target list HTML string for an event.
   * Feed targets are {type, id} objects; they may also carry a name field
   * (populated by 8.3.1 backend enrichment).
   *
   * Each target renders as a clickable link to its world-detail page.
   * When a name is available it is used as the link label; otherwise the
   * target type is shown (e.g. "character").
   *
   * Falls back gracefully for plain string values.
   *
   * @param {Array} targets — array of {type, id[, name, display_name]} objects
   * @returns {string} HTML string (comma-separated), or empty string
   */
  function _targetList(targets) {
    if (!targets || !targets.length) return "";
    var parts = [];
    var typeToPath = { character: "characters", group: "groups", location: "locations" };
    for (var i = 0; i < targets.length; i++) {
      var t = targets[i];
      if (t && typeof t === "object") {
        var type    = t.type || "object";
        var id      = t.id   || "";
        // Prefer explicit name from 8.3.1 enrichment or legacy fields; fall
        // back to the target type as a human-readable label.
        var name    = t.name || t.display_name || null;
        var label   = name || type;
        var pathSeg = typeToPath[type] || (type + "s");

        if (id) {
          var href = "#/world/" + pathSeg + "/" + encodeURIComponent(id);
          parts.push('<a href="' + window.utils.esc(href) + '">' + window.utils.esc(label) + '</a>');
        } else {
          parts.push(window.utils.esc(label));
        }
      } else {
        parts.push(window.utils.esc(String(t)));
      }
    }
    return parts.join(", ");
  }

  // --------------------------------------------------------------------------
  // Type-specific renderers
  // --------------------------------------------------------------------------

  /**
   * Render the actor name, as a clickable link when actor_id is available
   * and the actor is not "You" (is_own) or "System".
   *
   * The API may provide actor_name (added in 8.3.1) as a display name.
   * Falls back to a label derived from actor_type + is_own when absent.
   *
   * @param {string} actorType — "player" | "gm" | "system"
   * @param {string|null} actorId — ULID of the acting user, or null
   * @param {string|null} actorName — display name from the API, or null
   * @param {boolean} isOwn — true when the current user is the actor
   * @returns {string} HTML string (plain text or <a> element)
   */
  function _actorHtml(actorType, actorId, actorName, isOwn) {
    var label;
    if (actorType === "system") {
      label = "System";
    } else if (isOwn) {
      label = "You";
    } else if (actorName) {
      label = actorName;
    } else if (actorType === "gm") {
      label = "GM";
    } else {
      label = "Player";
    }

    // Only link when we have an actor_id, the actor is not "You", and not "System".
    if (actorId && !isOwn && actorType !== "system") {
      var href = "#/world/characters/" + encodeURIComponent(actorId);
      return '<a class="feed-item__actor-link" href="' + window.utils.esc(href) + '">' + window.utils.esc(label) + '</a>';
    }
    return window.utils.esc(label);
  }

  /**
   * Build a small source-type badge HTML string.
   * Possible values: "Event", "Story", "Proposal".
   *
   * @param {string} sourceType — "event" | "story" | "proposal"
   * @returns {string} HTML
   */
  function _sourceBadge(sourceType) {
    var label, mod;
    switch (String(sourceType || "event").toLowerCase()) {
      case "story":
      case "story_entry":
        label = "Story";
        mod   = "story";
        break;
      case "proposal":
        label = "Proposal";
        mod   = "proposal";
        break;
      default:
        label = "Event";
        mod   = "event";
        break;
    }
    return (
      '<span class="feed-item__source-badge feed-item__source-badge--' + window.utils.esc(mod) + '">' +
        window.utils.esc(label) +
      '</span>'
    );
  }

  /**
   * Render an event feed item.
   * @param {object} item — event data from the API
   * @param {boolean} isOwn — true when the current user is the actor
   * @returns {string} HTML
   */
  function _renderEvent(item, isOwn) {
    var actorType  = item.actor_type || "player";
    // actor_name populated by 8.3.1 backend enrichment; may be null/absent.
    var actorName  = item.actor_name || null;
    var actorId    = item.actor_id || null;
    var eventType  = item.event_type || item.type || "";
    var narrative  = item.narrative || item.description || "";
    var targets    = item.targets || [];
    var timestamp  = item.created_at || item.timestamp || "";
    var relTime    = _relativeTime(timestamp);
    var modifier   = _actorModifier(actorType);
    var typeLabel  = _eventTypeLabel(eventType);
    var targetList = _targetList(targets);

    // targetList is already HTML (may contain <a> elements); do not re-escape.
    var targetHtml = targetList
      ? '<div class="feed-item__targets">Re: ' + targetList + '</div>'
      : "";

    var narrativeHtml = narrative
      ? '<p class="feed-item__narrative">' + window.utils.esc(narrative) + '</p>'
      : "";

    var ownClass = isOwn ? " feed-item--own" : "";
    var actorHtml = _actorHtml(actorType, actorId, actorName, isOwn);

    // Determine source type: events linked to a proposal show "Proposal".
    var sourceType = item.proposal_id ? "proposal" : "event";

    return (
      '<div class="feed-item feed-item--event feed-item--' + window.utils.esc(modifier) + ownClass + '">' +
        '<div class="feed-item__meta">' +
          '<span class="feed-item__actor">' + actorHtml + '</span>' +
          '<span class="feed-item__action">' + window.utils.esc(typeLabel) + '</span>' +
          _sourceBadge(sourceType) +
          (relTime
            ? '<time class="feed-item__time" datetime="' + window.utils.esc(timestamp) + '">' + window.utils.esc(relTime) + '</time>'
            : '') +
        '</div>' +
        targetHtml +
        narrativeHtml +
      '</div>'
    );
  }

  /**
   * Render a story entry feed item.
   * @param {object} item — story entry data from the API
   * @param {boolean} isOwn — true when the current user is the author
   * @returns {string} HTML
   */
  function _renderStoryEntry(item, isOwn) {
    // The API returns author_id (a ULID) rather than a name. Use is_own to
    // distinguish the current user's entries; fall back to a generic label.
    var authorName = isOwn ? "You" : "Player";
    var storyName  = item.story_name || "";
    var entryText  = item.entry_text || "";
    var timestamp  = item.timestamp || "";
    var relTime    = _relativeTime(timestamp);

    var storyHtml = storyName
      ? '<span class="feed-item__story-name">' + window.utils.esc(storyName) + '</span>'
      : "";

    var entryHtml = entryText
      ? '<p class="feed-item__entry">' + window.utils.esc(entryText) + '</p>'
      : "";

    var ownClass = isOwn ? " feed-item--own" : "";

    return (
      '<div class="feed-item feed-item--story-entry' + ownClass + '">' +
        '<div class="feed-item__meta">' +
          '<span class="feed-item__actor">' + window.utils.esc(authorName) + '</span>' +
          storyHtml +
          _sourceBadge("story") +
          (relTime
            ? '<time class="feed-item__time" datetime="' + window.utils.esc(timestamp) + '">' + window.utils.esc(relTime) + '</time>'
            : '') +
        '</div>' +
        entryHtml +
      '</div>'
    );
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  return {
    /**
     * Render a FeedItem to an HTML string.
     * @param {object} props
     * @param {object} props.item    — feed item object from the API
     * @param {string} props.type   — "event" | "story_entry"
     * @param {boolean} [props.isOwn] — override; falls back to item.is_own
     * @returns {string}
     */
    render: function (props) {
      var item   = props.item || {};
      var type   = String(props.type || item.type || "event");
      // Honour an explicit isOwn prop; otherwise use the API-provided is_own flag.
      var isOwn  = props.isOwn !== undefined ? Boolean(props.isOwn) : Boolean(item.is_own);

      if (type === "story_entry") {
        return _renderStoryEntry(item, isOwn);
      }
      return _renderEvent(item, isOwn);
    },
  };
})();
