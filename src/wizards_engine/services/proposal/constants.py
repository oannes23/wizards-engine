"""Constants for the proposal service."""

from __future__ import annotations

#: The 8 canonical skill names accepted in ``use_skill`` proposals.
CANONICAL_SKILLS: frozenset[str] = frozenset(
    {
        "awareness",
        "composure",
        "influence",
        "finesse",
        "speed",
        "power",
        "knowledge",
        "technology",
    }
)

#: The 5 canonical magic stat names accepted in ``use_magic`` / ``charge_magic`` proposals.
CANONICAL_MAGIC_STATS: frozenset[str] = frozenset(
    {
        "being",
        "wyrding",
        "summoning",
        "enchanting",
        "dreaming",
    }
)

#: The 5 magic stat keys used for ``regain_gnosis`` lowest-stat calculation.
MAGIC_STAT_KEYS: tuple[str, ...] = (
    "being",
    "wyrding",
    "summoning",
    "enchanting",
    "dreaming",
)

#: Maximum gnosis value (cap applied on approval).
GNOSIS_MAX: int = 23

#: Maximum free_time value.
FREE_TIME_MAX: int = 20

#: Maximum stress value (before trauma bond reduction).
STRESS_MAX: int = 9

#: Maximum plot value (clamped at session end).
PLOT_MAX: int = 5

#: Hard PC bond slot limit.
PC_BOND_LIMIT: int = 8

#: Hard active trait limits per slot_type.
TRAIT_LIMITS: dict[str, int] = {
    "core_trait": 2,
    "role_trait": 3,
}

#: Downtime action types that auto-cost 1 FT (proposal-based only).
#: ``recharge_trait`` and ``maintain_bond`` were promoted to direct player
#: actions in Phase 5.5 and are no longer valid proposal action types.
DOWNTIME_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "regain_gnosis",
        "work_on_project",
        "rest",
        "new_trait",
        "new_bond",
    }
)
