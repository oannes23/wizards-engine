# Backend Change Requests — Handoff

> For the backend team. These are outstanding API changes requested by the frontend spec process.
> Full context: [backend-change-requests.md](backend-change-requests.md)
> Date: 2026-03-27

---

## Outstanding CRs

_None — all CRs resolved or implemented._

---

## Resolved CRs (for reference)

These were resolved during the spec deepening process (2026-03-26). No backend changes needed — the documentation was clarified:

| CR | Resolution |
|----|-----------|
| CR-002 | `calculated_effect` shapes fully documented per action type |
| CR-003 | `MagicSacrifice` / `SacrificeEntry` type documented |
| CR-004 | `gm_overrides` flags enumerated per action type |
| CR-005 | `resolve_clock` / `resolve_trauma` approval schemas documented |
| CR-006 | `POST /me/character` body shape documented |
| CR-010 | Bidirectional bond representation clarified |
| CR-011 | Domain-specific error codes added to catalog |
| CR-012 | `InviteResponse` shape defined |

## Implemented CRs

| CR | Implementation |
|----|---------------|
| CR-001 | `POST /proposals/calculate` dry-run endpoint |
| CR-007 | `?status=` filter on `GET /sessions` (commit 14994ee) |
| CR-008 | `character_name` added to session participants (commit 14994ee) |
| CR-009 | `GET /stories/{id}/entries` paginated endpoint + inline cap at 20 |
