"""Proposal service — submission, calculation, approval, and rejection.

This package was split from a single ``proposal.py`` module for
maintainability.  All public symbols are re-exported here so that
existing imports (``from wizards_engine.services import proposal`` or
``from wizards_engine.services.proposal import ...``) continue to work.
"""

from .approval import approve_proposal, reject_proposal
from .calculators import (
    _gnosis_equiv_to_sacrifice_dice,
    calculate_charge_magic,
    calculate_new_bond,
    calculate_new_trait,
    calculate_regain_gnosis,
    calculate_rest,
    calculate_use_magic,
    calculate_use_skill,
    calculate_work_on_project,
)
from .constants import (
    CANONICAL_MAGIC_STATS,
    CANONICAL_SKILLS,
    DOWNTIME_ACTION_TYPES,
    FREE_TIME_MAX,
    GNOSIS_MAX,
    MAGIC_STAT_KEYS,
    PC_BOND_LIMIT,
    PLOT_MAX,
    STRESS_MAX,
    TRAIT_LIMITS,
)
from .crud import (
    create_proposal,
    delete_proposal,
    get_proposal,
    list_proposals_query,
    update_proposal,
)

__all__ = [
    # Constants
    "CANONICAL_SKILLS",
    "CANONICAL_MAGIC_STATS",
    "MAGIC_STAT_KEYS",
    "GNOSIS_MAX",
    "FREE_TIME_MAX",
    "STRESS_MAX",
    "PLOT_MAX",
    "PC_BOND_LIMIT",
    "TRAIT_LIMITS",
    "DOWNTIME_ACTION_TYPES",
    # Calculators
    "calculate_use_skill",
    "calculate_use_magic",
    "calculate_charge_magic",
    "calculate_regain_gnosis",
    "calculate_work_on_project",
    "calculate_rest",
    "calculate_new_trait",
    "calculate_new_bond",
    "_gnosis_equiv_to_sacrifice_dice",
    # CRUD
    "create_proposal",
    "get_proposal",
    "list_proposals_query",
    "update_proposal",
    "delete_proposal",
    # Approval
    "approve_proposal",
    "reject_proposal",
]
