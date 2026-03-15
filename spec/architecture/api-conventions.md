# API Conventions

**Status**: 🟢 Complete
**Last interrogated**: 2026-03-13
**Last verified**: —

---

## Overview

This document defines the conventions for all HTTP API endpoints in Wizards Engine. It is the **authoritative source** for response shapes, error formats, naming conventions, HTTP semantics, and cross-cutting API behaviors. Domain specs define *what* endpoints exist; this document defines *how* they behave.

**Stack**: FastAPI + SQLAlchemy ORM + Pydantic validation + SQLite + Alembic migrations.

---

## Framework

### FastAPI

- **Decision**: Use FastAPI as the web framework.
- **Rationale**: Native Pydantic integration, auto OpenAPI generation, async support, dependency injection. Natural fit for the Pydantic validation layer already specified in domain specs.
- **Implications**: Request/response models are Pydantic `BaseModel` subclasses. Path operations use FastAPI decorators. Dependency injection for auth, DB sessions, etc.

### OpenAPI Documentation

- **Decision**: Auto-generated OpenAPI docs are always on — `/docs` (Swagger UI), `/redoc` (ReDoc), `/openapi.json` (raw spec).
- **Rationale**: Useful for development and the small user group. No security concern for a self-hosted single-game app.

---

## URL Conventions

### Base Path

All API endpoints are prefixed with `/api/v1/`.

### Naming

- **Decision**: snake_case for both JSON field names and URL path segments.
- **Rationale**: Matches Python conventions, Pydantic field names, and database column names directly. No translation layer needed.
- **Examples**: `/api/v1/trait_templates/{id}`, `/api/v1/game/invites`, `character_id`, `is_deleted`

### Sub-Resource Endpoints

- **Decision**: Sub-resource endpoints return the same response shape as the corresponding top-level endpoint, just pre-filtered by the parent resource.
- **Rationale**: Consistent and predictable. Clients can use the same deserialization logic regardless of which route they hit.
- **Example**: `GET /api/v1/groups/{id}/clocks` returns the same `{items: [...], next_cursor: ...}` shape as `GET /api/v1/clocks`.

---

## Response Format

### Successful Responses — Single Resource

Return the resource directly as the top-level JSON object. No envelope wrapper.

```json
GET /api/v1/characters/01H...
→ 200
{
  "id": "01HABCDEF...",
  "name": "Kael",
  "detail_level": "full",
  "is_deleted": false,
  "created_at": "2026-03-13T14:30:00Z",
  "updated_at": "2026-03-13T15:45:12Z"
}
```

### Successful Responses — List

Return an object with `items` array and optional `next_cursor` for pagination.

```json
GET /api/v1/characters
→ 200
{
  "items": [
    {"id": "01H...", "name": "Kael", ...},
    {"id": "01H...", "name": "Aldric", ...}
  ],
  "next_cursor": "01HABCDEF...",
  "has_more": true
}
```

- `next_cursor` is `null` when there are no more results.
- `has_more` is a boolean indicating whether more items exist beyond this page.
- Pagination is ULID cursor-based: `?after=<ulid>&limit=N` (default 50, max 100 — as established in [feed.md](../domains/feed.md)).

### Successful Responses — Create (POST)

- **Decision**: Return the full created resource with `201 Created`.
- **Rationale**: Saves a follow-up GET. The client immediately has the complete object with server-generated fields (id, timestamps, defaults).

### Successful Responses — Delete (DELETE)

Return `204 No Content` with an empty body.

### Sorting

- **Decision**: All list endpoints return items in ULID order (creation time, newest first). No server-side sort parameter.
- **Rationale**: For 4–6 players with small datasets, client-side re-sorting is sufficient. ULID order is the natural sort for cursor pagination.

---

## Error Format

### Error Response Body

- **Decision**: All errors return a nested `{error: {code, message, details?}}` structure.
- **Rationale**: Machine-readable `code` for programmatic handling, human-readable `message` for display, optional `details` for field-level validation context.

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid proposal submission",
    "details": {
      "fields": {
        "target_id": "Character not found",
        "action_type": "Unknown action type 'cast_spell'"
      }
    }
  }
}
```

- `code`: Machine-readable snake_case string (e.g., `not_found`, `validation_error`, `insufficient_free_time`, `forbidden`)
- `message`: Human-readable explanation
- `details`: Optional object. For validation errors, contains a `fields` map of field name → error message. May carry other structured context as needed.

### HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| `200 OK` | Successful GET or PATCH | Read or update |
| `201 Created` | Successful POST | Resource created (body = full resource) |
| `204 No Content` | Successful DELETE | Resource deleted (empty body) |
| `400 Bad Request` | Malformed request | Unparseable JSON, missing Content-Type |
| `401 Unauthorized` | Authentication missing/invalid | No cookie, expired cookie, invalid cookie |
| `403 Forbidden` | Insufficient permissions | Player accessing GM-only endpoint |
| `404 Not Found` | Resource not found **or inaccessible** | Missing resource, soft-deleted (on lists), or caller lacks visibility |
| `409 Conflict` | Business rule violation | Insufficient resources on approval, duplicate constraint |
| `422 Unprocessable Entity` | Validation error | Valid JSON but fails schema or domain validation |
| `500 Internal Server Error` | Unexpected failure | Unhandled exception |

### Authorization Errors

- **Decision**: Return `404` (not `403`) for resources the caller doesn't have permission to see.
- **Rationale**: Don't reveal the existence of resources the user shouldn't know about. Standard security practice.
- **Scope**: 403 is still used for **role-based** access control (player hitting a GM-only endpoint). 404 is used for **resource-level** visibility (player requesting a `gm_only` event, or another player's private proposal).

---

## Request Conventions

### Content Type

All request and response bodies are `application/json`. No other content types supported.

### PATCH Semantics

- **Decision**: Omitted fields are unchanged. Explicitly sending `null` clears the field (for nullable fields).
- **Rationale**: Standard partial-update semantics. Pydantic's `model_fields_set` tracks which fields were explicitly provided vs. omitted.
- **Implementation**: Use `Optional[T] = None` with `exclude_unset=True` serialization. Only apply fields present in `model_fields_set`.

```json
PATCH /api/v1/characters/01H...

// Only update description:
{"description": "A wandering mage"}

// Clear the description:
{"description": null}
```

### Timestamps

- **Decision**: ISO 8601 UTC with `Z` suffix for all datetime values. Calendar-only dates as `YYYY-MM-DD`.
- **Rationale**: Universally understood, unambiguous timezone. Frontend handles local display conversion.

```json
{
  "created_at": "2026-03-13T14:30:00Z",
  "updated_at": "2026-03-13T15:45:12Z",
  "date": "2026-03-13"
}
```

---

## Filtering and Pagination

### Pagination

ULID cursor-based pagination on all list endpoints:
- `?after=<ulid>` — return items after this cursor
- `?limit=N` — items per page (default 50, max 100)
- Response includes `next_cursor` and `has_more` for the next page

### Filtering

- **Decision**: Simple query parameters per field. Only add filters where there's a clear use case.
- **Rationale**: No generic filter language needed for a small-group app. Filters are defined per endpoint based on domain needs.

Already-specified filters (from domain specs):
- **Feed**: `type`, `target_type`, `target_id`, `actor_type`, `session_id`, `since`, `until`
- **Proposals**: `status`, `character_id`
- **Characters**: `detail_level`

Additional filters should follow the same pattern: simple query params matching field names.

### Soft-Deleted Resources

- **Decision**: List endpoints exclude soft-deleted items by default. `?include_deleted=true` reveals them. Direct GET by ID always returns the resource (with `is_deleted` visible in the response).
- **Rationale**: Clean default behavior for normal use. Opt-in for admin/audit views.

---

## CORS

- **Decision**: No CORS headers needed. The web UI is served from the same process (same origin).
- **Rationale**: Simplest option. If a separate frontend or mobile client is needed later, add CORS middleware then.

---

## Open Questions

_All resolved._

---

_Last updated: 2026-03-14 (added has_more boolean to paginated list response envelope, consistent with feed.md)_
