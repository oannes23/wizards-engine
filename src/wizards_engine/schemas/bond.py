"""Shared Pydantic schemas for bond and trait display in Game Object detail responses.

These schemas are consumed by the character, group, and location detail
endpoints.  They are never used for request validation — only for responses.
"""

from pydantic import BaseModel, ConfigDict


class BondDisplayResponse(BaseModel):
    """A single bond entry as returned on a Game Object detail endpoint.

    Perspective-normalized: the ``label`` field reflects the viewing entity's
    own perspective — ``source_label`` when the entity owns the bond,
    ``target_label`` when the bond is an inbound bidirectional bond and this
    entity is the target.

    Similarly, ``target_type``, ``target_id``, and ``target_name`` describe
    the *other end* of the relationship from the viewer's perspective:
    - For outbound bonds: the bond target.
    - For inbound bidirectional bonds: the bond source (i.e., the entity that
      owns the record), because from the viewer's perspective *they* are the
      other party.

    Attributes
    ----------
    id:
        ULID of the bond slot.
    slot_type:
        Bond slot type (``"pc_bond"``, ``"npc_bond"``, ``"group_relation"``,
        ``"group_holding"``, ``"location_bond"``).
    target_type:
        The type of the other Game Object from this viewer's perspective
        (``"character"``, ``"group"``, or ``"location"``).
    target_id:
        ULID of the other Game Object from this viewer's perspective.
    target_name:
        Resolved display name of the other Game Object.
    label:
        Perspective-normalized relationship label.  Empty string if not set.
    description:
        Optional freeform context text.
    is_active:
        ``True`` for current bonds; ``False`` for past/retired bonds.
    bidirectional:
        Whether the bond is visible from both sides.
    charges:
        Current bond charges (PC bonds only; ``null`` for all other types).
    degradations:
        Degradation count (PC bonds only; ``null`` for all other types).
    is_trauma:
        ``True`` if this bond slot holds a Trauma rather than a relationship
        (PC bonds only; ``null`` for all other types).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    slot_type: str
    target_type: str
    target_id: str
    target_name: str
    label: str
    description: str | None
    is_active: bool
    bidirectional: bool
    # PC bond mechanical fields — null for non-PC bonds.
    charges: int | None
    degradations: int | None
    is_trauma: bool | None
    effective_charges_max: int | None = None


class BondGroups(BaseModel):
    """Active and past bonds for a Game Object, returned in separate groups.

    Attributes
    ----------
    active:
        Currently active bonds.
    past:
        Retired/past bonds.
    """

    active: list[BondDisplayResponse] = []
    past: list[BondDisplayResponse] = []


class TraitDisplayResponse(BaseModel):
    """A descriptive trait entry (group_trait or feature_trait) in a detail response.

    Attributes
    ----------
    id:
        ULID of the trait slot.
    name:
        Trait name.
    description:
        Optional freeform description.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None


class GroupMemberResponse(BaseModel):
    """A minimal Character record representing a Group member in the members list.

    Membership is derived — any Character with an active bond targeting the
    Group is considered a member.

    Attributes
    ----------
    id:
        ULID of the character.
    name:
        Character display name.
    description:
        Optional freeform character description.
    detail_level:
        ``"full"`` (PC) or ``"simplified"`` (NPC).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    detail_level: str
