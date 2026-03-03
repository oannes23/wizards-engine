# Auth — Domain Specification

**Status**: 🟡 In progress
**Last interrogated**: —
**Last verified**: —
**Depends on**: None (primitive)
**Depended on by**: [proposals](proposals.md), [events](events.md)

---

## Overview

Simple authentication and authorization for a small, fixed group. No external auth providers — this is a trusted small group. The GM creates the game, invites players, and manages access. Auth tokens are bearer tokens passed via HTTP header.

---

## Core Concepts

### Game Creation & Onboarding

1. **GM creates the game** and receives an admin token.
2. **GM generates invite links/codes** for players.
3. **Players join** with an invite code and set up a simple identity (display name + secret token).

### Token-Based Auth

- Auth tokens are passed via header: `Authorization: Bearer <token>`
- No session management, no cookies, no OAuth
- Tokens are simple secrets — no JWT, no expiry (TBD)

### Permission Model

Two roles:

**GM (Game Master)**:
- Full read/write access to everything
- Can create/modify all game objects (NPCs, Groups, Locations, Stories, Sessions)
- Can approve/reject proposals
- Can directly modify any character or game state
- Can trigger downtime
- Can generate invite codes

**Players**:
- Can read all public game state (characters, groups, locations, NPCs, stories, sessions, events)
- Can modify their own character (notes, direct actions)
- Can submit and revise proposals for their own character
- Cannot modify other players' characters
- Cannot access GM-only endpoints

---

## Decisions

### No External Auth

- **Decision**: No OAuth, no external identity providers. Simple bearer tokens.
- **Rationale**: This is a trusted small group (4–6 players + 1 GM). The complexity of external auth is not justified.
- **Implications**: Token management is simple but also less secure. Acceptable for the use case.

### Two-Role Model

- **Decision**: Only two roles — GM and Player. No granular permissions.
- **Rationale**: The game has exactly two types of users with clearly different capabilities. More granular permissions add complexity without value.
- **Implications**: Authorization checks are simple role-based conditionals.

### Invite-Based Onboarding

- **Decision**: Players join via GM-generated invite codes, not self-registration.
- **Rationale**: The GM controls who joins the game. There's no public registration.
- **Implications**: Need invite code generation and redemption endpoints.

---

## API Endpoints

- `GET /api/v1/game` — game settings, player roster
- `PATCH /api/v1/game` — update settings (GM)
- `POST /api/v1/game/invite` — generate invite link/code (GM)
- `POST /api/v1/game/join` — join with invite code (player)

---

## Open Questions

1. What is the token format? (Random string? UUID? Something else?)
2. Do tokens expire? If so, what's the renewal mechanism?
3. Is there a "player profile" beyond display name? (Avatar? Color?)
4. Can the GM revoke a player's access?
5. How is the initial GM account created? (First-run setup? CLI command? Env variable?)
6. Should there be a "spectator" role for read-only access without a character?
7. How are tokens stored server-side? (Hashed? Plaintext? Given trusted group, does it matter?)
8. Can a player have multiple characters, or is it strictly one-to-one?

---

## Implications for Other Specs

| Spec | Implication |
|------|-------------|
| [proposals](proposals.md) | Players can only submit proposals for their own character; GM approves/rejects |
| [events](events.md) | Event `actor` field identifies the user; all events readable by all players |
| [character-core](character-core.md) | Characters are owned by players; owner can edit notes directly |
| [game-objects](game-objects.md) | World objects (NPCs, Groups, etc.) are GM-only for creation/modification |

---

_Last updated: 2026-02-24_
