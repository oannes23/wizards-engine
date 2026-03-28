# Viewer Role — Frontend Handoff

> For the Next.js frontend team. Documents all API contract changes for the new "viewer" role.
> Full context: see `spec/implementation/phase9-viewer-role.md`
> Date: 2026-03-28

---

## Summary

A third user role, `"viewer"`, now exists in the system. Viewer accounts:

- Have **GM-level read access**: dashboard, queue summary, all proposals, all events (except `silent`), all characters, all sessions, invite list
- Are **blocked from all mutations**: approve, reject, create, edit, delete, GM actions — these return 403
- Have **no character**: `character_id` is always `null`
- Are **not players**: the proposal submission flow does not apply
- Are **invisible to players**: filtered out of the player roster for player callers

---

## API contract changes

### GET /me

Two new fields added:

```json
{
  "id": "...",
  "display_name": "Spectator",
  "role": "viewer",
  "character_id": null,
  "can_view_gm_content": true,
  "can_take_gm_actions": false
}
```

| Role | `can_view_gm_content` | `can_take_gm_actions` |
|------|----------------------|----------------------|
| `"gm"` | `true` | `true` |
| `"viewer"` | `true` | `false` |
| `"player"` | `false` | `false` |

**Recommended frontend pattern:** Derive UI capabilities from these fields rather than hardcoding role checks:

```typescript
// From GET /me response:
const canViewGmContent = me.can_view_gm_content;   // GM, viewer
const canTakeGmActions = me.can_take_gm_actions;    // GM only
const canSubmitProposals = me.role === "player";     // player only
const hasCharacter = me.character_id !== null;       // player (and optionally GM)
```

### POST /auth/login

Response includes `role: "viewer"` for viewer accounts. Same shape as before — no new fields.

### Routing after login

```
role === "gm"     → GM dashboard (full access)
role === "viewer" → GM dashboard (read-only — hide action buttons)
role === "player" → Player character sheet
```

---

## Viewer creation flow

### POST /game/invites

Now accepts an optional request body:

```json
{ "role": "viewer" }
```

- No body or `{"role": "player"}` → player invite (existing behavior)
- `{"role": "viewer"}` → viewer invite

Response now includes `role` field:

```json
{
  "id": "01JQXYZ...",
  "is_consumed": false,
  "role": "viewer",
  "login_url": "/login/01JQXYZ...",
  "created_at": "2026-03-28T..."
}
```

### POST /game/join

For viewer invites, `character_name` is not required:

```json
{
  "code": "01JQXYZ...",
  "display_name": "Spectator"
}
```

For player invites, `character_name` is still required (422 if missing).

Response:

```json
{
  "id": "...",
  "display_name": "Spectator",
  "role": "viewer",
  "character_id": null
}
```

---

## Endpoint access matrix

### Read endpoints — viewer has access

| Endpoint | Notes |
|----------|-------|
| `GET /gm/dashboard` | Same data as GM |
| `GET /gm/queue-summary` | Same data as GM |
| `GET /game/invites` | Viewer can see invite list |
| `GET /proposals` | Returns all proposals (same as GM) |
| `GET /proposals/{id}` | Access to any proposal |
| `GET /sessions`, `GET /sessions/{id}` | Full access |
| `GET /sessions/{id}/timeline` | All visibility levels except `silent` |
| `GET /characters`, `GET /characters/{id}`, `GET /characters/summary` | Full access |
| `GET /groups`, `GET /groups/{id}` | Full access |
| `GET /locations`, `GET /locations/{id}` | Full access |
| `GET /clocks`, `GET /clocks/{id}` | Full access |
| `GET /trait-templates`, `GET /trait-templates/{id}` | Full access |
| `GET /stories`, `GET /stories/{id}`, `GET /stories/{id}/entries` | All stories visible |
| `GET /events`, `GET /events/{id}` | All except `silent` |
| `GET /players` | Sees all users (including viewers) but no `login_url` |
| `GET /me/feed`, `GET /me/feed/starred` | All visibility levels except `silent` |
| `GET /me/starred` | Personal starred objects |
| `POST /me/starred`, `DELETE /me/starred/{type}/{id}` | Viewer CAN star/unstar (personal feature) |

### Write endpoints — viewer is blocked (403)

All of these return:

```json
{
  "error": {
    "code": "insufficient_role",
    "message": "This action requires GM privileges."
  }
}
```

| Endpoint | Category |
|----------|----------|
| `POST /gm/actions` | GM actions |
| `POST /gm/actions/batch` | GM actions |
| `POST /proposals` | Player-only |
| `POST /proposals/calculate` | Player-only |
| `POST /proposals/{id}/approve` | GM-only |
| `POST /proposals/{id}/reject` | GM-only |
| `POST /characters`, `PATCH /characters/{id}`, `DELETE /characters/{id}` | GM-only CRUD |
| `POST /groups`, `PATCH /groups/{id}`, `DELETE /groups/{id}` | GM-only CRUD |
| `POST /locations`, `PATCH /locations/{id}`, `DELETE /locations/{id}` | GM-only CRUD |
| `POST /clocks`, `PATCH /clocks/{id}`, `DELETE /clocks/{id}` | GM-only CRUD |
| `POST /trait-templates`, `PATCH /trait-templates/{id}`, `DELETE /trait-templates/{id}` | GM-only CRUD |
| `POST /sessions`, `PATCH /sessions/{id}`, `DELETE /sessions/{id}` | GM-only CRUD |
| `POST /sessions/{id}/start`, `POST /sessions/{id}/end` | GM-only |
| `POST /sessions/{id}/participants`, `DELETE .../participants/{cid}`, `PATCH .../participants/{cid}` | Session management |
| `POST /stories`, `PATCH /stories/{id}`, `DELETE /stories/{id}` | GM-only CRUD |
| `PATCH /events/{id}/visibility` | GM-only |
| `POST /players/{id}/regenerate-token` | GM-only |
| `POST /me/character` | GM-only |
| `DELETE /game/invites/{id}` | GM-only |
| Player direct actions (find-time, recharge-trait, maintain-bond, effects use/retire) | Player-only |

### GET /me/feed/silent

**Not available to viewers.** Returns 403. The silent feed is system audit data.

---

## Player roster behavior

`GET /players` returns different data based on the caller's role:

| Caller | Sees viewers? | Sees `login_url`? |
|--------|--------------|-------------------|
| GM | Yes | Yes |
| Viewer | Yes | No |
| Player | No | No |

---

## Error handling

All viewer-blocked mutations return the same 403 shape:

```json
{
  "error": {
    "code": "insufficient_role",
    "message": "This action requires GM privileges."
  }
}
```

**Recommended:** Map this to a role-aware UI message:

```typescript
if (error.code === "insufficient_role" && me.role === "viewer") {
  showToast("You have read-only access.");
} else {
  showToast(error.message);
}
```

---

## Event visibility

Viewers see all 7 visibility levels except `silent`:

| Level | Viewer sees? |
|-------|-------------|
| `silent` | No |
| `gm_only` | Yes |
| `private` | Yes |
| `bonded` | Yes |
| `familiar` | Yes |
| `public` | Yes |
| `global` | Yes |

---

## Integration checklist

- [ ] Add `"viewer"` to role type/enum
- [ ] Update login routing: viewer → GM dashboard (read-only)
- [ ] Use `can_view_gm_content` / `can_take_gm_actions` from `GET /me` instead of `role === "gm"`
- [ ] Hide all action buttons (approve, reject, create, edit, delete) when `can_take_gm_actions === false`
- [ ] Hide proposal wizard when `role !== "player"`
- [ ] Hide character sheet nav when `character_id === null`
- [ ] Handle viewer invite creation (optional role field on invite form)
- [ ] Handle viewer join flow (no character_name field)
- [ ] Map `insufficient_role` 403 to "Read-only access" toast for viewers
- [ ] Filter silent feed tab out of viewer navigation
- [ ] Confirm backend deployment before integrating viewer-accessible GM endpoints

---

## What's next

All backend changes for the viewer role are implemented and tested. If you need any adjustments to these endpoints or have new requests, add them to the handoff doc and we'll pick them up.
