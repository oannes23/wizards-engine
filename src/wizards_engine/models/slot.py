"""ORM models for the unified Slot table and TraitTemplate catalog."""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base, TimestampMixin


class TraitTemplate(TimestampMixin, Base):
    """GM-created catalog entry for Core and Role Trait definitions.

    Templates are shared across characters.  Editing a template's name or
    description propagates to all characters referencing it via
    ``slots.template_id``.  The ``type`` field is immutable after creation.
    """

    __tablename__ = "trait_templates"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'core' | 'role'
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationship — all slots using this template.
    slots: Mapped[list["Slot"]] = relationship("Slot", back_populates="template")


class Slot(TimestampMixin, Base):
    """Unified table for all traits and bonds across all Game Object types.

    The ``slot_type`` discriminator determines which columns are active for a
    given row.  Application code enforces valid column usage per slot type.

    Slot types:
    - ``core_trait``: Character (full) — uses ``template_id``, ``charge``
    - ``role_trait``: Character (full) — uses ``template_id``, ``charge``
    - ``pc_bond``: Character (full) — uses ``charges``, ``degradations``,
      ``is_trauma``, plus label/bidirectional columns
    - ``npc_bond``: Character (simplified) — label/bidirectional columns only
    - ``group_trait``: Group — descriptive only
    - ``group_relation``: Group → Group — label/bidirectional only
    - ``group_holding``: Group → Location — descriptive only
    - ``feature_trait``: Location — descriptive only
    - ``location_bond``: Location → any — label columns only (directional)

    Note: ``charges`` and ``degradations`` are the physical column names
    for what bonds.md calls "bond charges" and "degradation count".
    """

    __tablename__ = "slots"

    __table_args__ = (
        Index("ix_slots_owner", "owner_type", "owner_id", "slot_type"),
        Index("ix_slots_target", "target_type", "target_id"),
    )

    # Discriminator + ownership.
    slot_type: Mapped[str] = mapped_column(String(30), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(26), nullable=False)

    # Common fields.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Bond target (polymorphic — no FK constraint, enforced in app code).
    target_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(26), nullable=True)

    # Bond label columns.
    source_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bidirectional: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Trait template link (core_trait / role_trait only).
    template_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("trait_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Trait mechanical fields (core_trait / role_trait only).
    charge: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Bond mechanical fields (pc_bond only).
    charges: Mapped[int | None] = mapped_column(Integer, nullable=True)
    degradations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_trauma: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Relationship to template.
    template: Mapped["TraitTemplate | None"] = relationship(
        "TraitTemplate",
        back_populates="slots",
    )
