# Epic 8.6 — Game Object CRUD Forms

**Phase**: 8 — UI Cleanup & UX Modernization
**Depends on**: 8.4.4 (CRUD action buttons in Game Objects browser)
**Blocks**: None
**Parallel with**: None (final epic)

---

## Overview

Build create, edit, and archive forms for all game object types (Characters, Groups, Locations) accessible from the Game Objects browser. All backend CRUD endpoints already exist — this epic is frontend-only, creating form views that call the existing REST API.

---

## Stories

| Story | Status | Completed |
|-------|--------|-----------|
| 8.6.1 — Character Create and Edit Forms | 🔴 Not started | — |
| 8.6.2 — Group Create/Edit/Archive Forms | 🔴 Not started | — |
| 8.6.3 — Location Create/Edit/Archive Forms | 🔴 Not started | — |

### Story 8.6.1 — Character Create and Edit Forms

**Files to create**:
- `src/wizards_engine/static/js/views/character-create.js` — NPC creation form

**Files to modify**:
- `src/wizards_engine/static/js/views/character-edit.js` — extend to support all GM-editable fields
- `src/wizards_engine/static/js/router.js` — add route for `#/gm/world/characters/new`
- `src/wizards_engine/static/index.html` — add script tag for character-create.js

**Spec refs**: [game-objects.md](../domains/game-objects.md) (Character CRUD), [character-core.md](../domains/character-core.md)

**Implementation notes**:
- **Create form** (`#/gm/world/characters/new`): GM creates NPCs. Fields: Name (required text), Description (textarea), Detail Level (select: PC/NPC, defaulting to NPC). Uses `POST /api/v1/characters`
- PCs are created through the player join flow, not this form — but the select allows GM to create a full (PC) character shell if needed
- **Edit form** (`#/gm/world/characters/{id}/edit`): extend existing `character-edit.js` to include GM-specific fields (currently only supports name, description, notes). Add fields accessible via GM actions: attributes, notes
- **Archive**: soft-delete button with confirmation dialog on the edit form. Uses `DELETE /api/v1/characters/{id}`. Button styled as destructive (red border). Confirmation: "Are you sure you want to archive [name]?"
- On successful create: navigate to the new character's detail page (`#/gm/world/characters/{new_id}`)
- On successful edit: navigate back to character detail
- On cancel: navigate back to Game Objects browser
- GM-only forms — redirect non-GM users

**Acceptance criteria**:
1. `#/gm/world/characters/new` renders a character creation form
2. Filling in name and description and submitting creates a new character via API
3. After creation, navigates to the new character's detail page
4. Edit form loads with current character values pre-populated
5. Saving edit form updates character via PATCH API
6. Archive button shows confirmation dialog; confirming soft-deletes the character
7. After archive, navigates back to Game Objects browser
8. Non-GM users redirected to home
9. Validation: name is required; shows inline error if empty

### Story 8.6.2 — Group Create/Edit/Archive Forms

**Files to create**:
- `src/wizards_engine/static/js/views/group-edit.js` — group create and edit form (single view handling both modes)

**Files to modify**:
- `src/wizards_engine/static/js/router.js` — add routes for `#/gm/world/groups/new` and `#/gm/world/groups/{id}/edit`
- `src/wizards_engine/static/index.html` — add script tag

**Spec refs**: [game-objects.md](../domains/game-objects.md) (Group CRUD)

**Implementation notes**:
- Single view file handles both create and edit modes (determined by URL: `/new` vs `/{id}/edit`)
- **Create fields**: Name (required text), Description (textarea), Tier (select 1-5, default 1)
- **Edit fields**: same as create, pre-populated with current values
- Uses existing `POST /api/v1/groups` (create) and `PATCH /api/v1/groups/{id}` (edit)
- Archive: `DELETE /api/v1/groups/{id}` with confirmation dialog
- On create success: navigate to `#/gm/world/groups/{new_id}`
- On edit success: navigate to `#/gm/world/groups/{id}`
- Form follows consistent styling with character forms

**Acceptance criteria**:
1. `#/gm/world/groups/new` renders a group creation form with Name, Description, Tier fields
2. `#/gm/world/groups/{id}/edit` renders an edit form with pre-populated values
3. Creating a group navigates to the new group's detail page
4. Editing a group saves changes and navigates back to detail page
5. Archive button with confirmation dialog soft-deletes the group
6. After archive, navigates to Game Objects browser
7. Tier select shows options 1-5
8. Validation: name is required
9. Non-GM users redirected to home

### Story 8.6.3 — Location Create/Edit/Archive Forms

**Files to create**:
- `src/wizards_engine/static/js/views/location-edit.js` — location create and edit form

**Files to modify**:
- `src/wizards_engine/static/js/router.js` — add routes for `#/gm/world/locations/new` and `#/gm/world/locations/{id}/edit`
- `src/wizards_engine/static/index.html` — add script tag

**Spec refs**: [game-objects.md](../domains/game-objects.md) (Location CRUD)

**Implementation notes**:
- Single view file for both create and edit modes
- **Create fields**: Name (required text), Description (textarea), Parent Location (select dropdown populated from `GET /api/v1/locations`, with "None" option for top-level locations)
- **Edit fields**: same as create, pre-populated with current values
- Uses existing `POST /api/v1/locations` (create, with optional `parent_id`) and `PATCH /api/v1/locations/{id}` (edit)
- Parent location dropdown: fetch all locations, filter out the current location (can't be own parent) and any children (to prevent circular references)
- Archive: `DELETE /api/v1/locations/{id}` with confirmation dialog
- On create success: navigate to `#/gm/world/locations/{new_id}`
- On edit success: navigate to `#/gm/world/locations/{id}`

**Acceptance criteria**:
1. `#/gm/world/locations/new` renders a location creation form with Name, Description, Parent fields
2. `#/gm/world/locations/{id}/edit` renders an edit form with pre-populated values
3. Parent location dropdown shows all existing locations plus "None (top-level)"
4. Current location and its children excluded from parent dropdown (prevent circular references)
5. Creating a location navigates to the new location's detail page
6. Editing a location saves changes and navigates back to detail page
7. Archive button with confirmation dialog soft-deletes the location
8. After archive, navigates to Game Objects browser
9. Validation: name is required
10. Non-GM users redirected to home

---

## Notes

- All three stories are independent and can run in parallel (maximum parallelism = 3)
- All backend CRUD endpoints already exist and are tested — this epic is frontend-only
- Forms should follow a consistent visual pattern: card-style container, labeled inputs, submit/cancel/archive buttons, inline validation errors
- Consider extracting a shared `CrudForm` utility if the three forms share enough structure (header, field layout, submit/cancel/archive button bar, validation pattern). If the forms are simple enough, direct implementation is acceptable
- Archive is soft-delete (sets `is_deleted = true`) — the game object can still be viewed via direct URL but disappears from lists
