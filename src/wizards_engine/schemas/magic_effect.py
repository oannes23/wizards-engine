"""Pydantic schemas for Magic Effect API endpoints.

Covers request shapes for the effect action endpoints on
``/api/v1/characters/{id}/effects/{effect_id}/use`` and
``/api/v1/characters/{id}/effects/{effect_id}/retire``.

Response schemas for Magic Effects are defined in
:mod:`wizards_engine.schemas.character` (``MagicEffectResponse``) and are
reused here to keep the shape consistent across endpoints.
"""

from pydantic import BaseModel


class UseEffectRequest(BaseModel):
    """Request body for POST /api/v1/characters/{id}/effects/{effect_id}/use.

    All fields are optional — an empty JSON body ``{}`` is also accepted.

    Attributes
    ----------
    narrative:
        Optional freeform description of what the character does with the
        effect (e.g., "I pour the vial of shadows onto the floor to open
        the portal").  Stored in the event log when event logging is
        implemented (Epic 4.1).  No effect on the charge decrement logic.
    """

    narrative: str | None = None
