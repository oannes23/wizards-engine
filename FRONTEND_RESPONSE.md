# Backend Response — CR-001 & CR-009 Implemented

> For the frontend team. Both outstanding CRs from `BACKEND_HANDOFF.md` are now shipped.
> Date: 2026-03-27

---

## CR-001: Proposal dry-run / pre-calculate endpoint

**Status**: Implemented, ready for integration.

### Endpoint

```
POST /api/v1/proposals/calculate
Auth: Any authenticated player (same rules as POST /proposals)
```

### Request body

Same shape as `POST /proposals`:

```json
{
  "character_id": "<ulid>",
  "action_type": "use_skill",
  "narrative": "I check for traps.",
  "selections": { "skill": "awareness" }
}
```

All existing validation applies: `action_type` must be player-submittable, `character_id` must belong to the authenticated user, downtime actions require a narrative.

### Response (200)

```json
{
  "calculated_effect": {
    "dice_pool": 2,
    "skill": "awareness",
    "skill_level": 2,
    "modifiers": [],
    "plot_spend": 0,
    "costs": { "trait_charges": [], "plot": 0 }
  }
}
```

The `calculated_effect` shape is action-type-specific (same shapes as `ProposalResponse.calculated_effect`). No proposal record is created. No side effects. Safe to call repeatedly.

### Error responses

| Status | When |
|--------|------|
| 401 | Unauthenticated |
| 403 | GM caller |
| 422 | `character_id` doesn't belong to user, invalid `action_type`, missing narrative for downtime, or calculator validation failure (e.g., invalid skill name) |
| 404 | Character not found |

### Notes for integration

- You can now wire up Step 3 of the Proposal Wizard directly.
- The endpoint reuses the `CreateProposalRequest` schema, so the same form data that will eventually go to `POST /proposals` can be sent here first for preview.
- Calculator validation errors (e.g., referencing a nonexistent trait as a modifier) come back as 422 with the standard error envelope. You may want to catch these and surface them as inline form errors.

---

## CR-009: Paginated story entries

**Status**: Implemented, ready for integration.

### New endpoint

```
GET /api/v1/stories/{story_id}/entries?after=<cursor>&limit=N
Auth: Any authenticated user (same visibility rules as GET /stories/{id})
```

### Response (200)

```json
{
  "items": [
    {
      "id": "...",
      "story_id": "...",
      "text": "...",
      "author_id": "...",
      "character_id": null,
      "session_id": null,
      "event_id": null,
      "game_object_refs": null,
      "is_deleted": false,
      "updated_by": null,
      "deleted_by": null,
      "created_at": "2026-03-27T...",
      "updated_at": "2026-03-27T..."
    }
  ],
  "next_cursor": "<opaque-string>",
  "has_more": true
}
```

- Entries sorted by `created_at` ascending (oldest first).
- Default `limit`: 50. Max: 100.
- Cursor is an opaque base64-encoded keyset cursor (same pattern as `GET /sessions/{id}/timeline`).
- Soft-deleted entries are excluded.

### Changes to GET /stories/{id}

The `StoryDetailResponse` now includes two new fields:

```json
{
  "entries": [...],
  "has_more_entries": true,
  "entries_cursor": null
}
```

- `entries[]` is now capped at the **20 most recent** entries (by `created_at`), still sorted oldest-first within that window.
- `has_more_entries`: `true` when the story has more than 20 entries total.
- `entries_cursor`: Reserved for future use (currently always `null`). To load older entries, call `GET /stories/{id}/entries` from the beginning.

### Notes for integration

- For the "Load more" pattern: on initial story detail load, render the inline `entries[]`. If `has_more_entries` is `true`, show a "Load more" button that fetches `GET /stories/{id}/entries` from the start and paginates forward.
- The inline entries are the 20 *newest*, so the "Load more" flow fetches *older* entries preceding the inline window.
- Both `has_more_entries` and `entries_cursor` have defaults (`false` and `null`), so existing frontend code that doesn't reference these fields will not break.

---

## What's next

All outstanding CRs from `BACKEND_HANDOFF.md` are now resolved or implemented. If you need any adjustments to these endpoints or have new requests, add them to the handoff doc and we'll pick them up.
