"""ORM model for Proposal (player-submitted or system-generated action requests)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wizards_engine.models.base import Base, TimestampMixin


class Proposal(TimestampMixin, Base):
    """A request for a state change — either player-submitted or system-generated.

    ``character_id`` is null for system-generated proposals (e.g. ``resolve_clock``).
    ``origin`` distinguishes player-submitted from system-generated proposals.

    ``selections`` JSON contains all player inputs: modifier trait/bond IDs,
    plot_spend, and type-specific details.

    ``calculated_effect`` is the system-computed result (typed per action_type).
    ``gm_overrides`` replaces fields within ``calculated_effect`` on approval.

    ``event_id`` is set on approval, linking to the generated event.
    ``rider_event_id`` is set on approval if a rider event was created.
    ``clock_id`` is pre-linked for ``resolve_clock`` proposals only.
    """

    __tablename__ = "proposals"

    character_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    origin: Mapped[str] = mapped_column(String(10), nullable=False)  # 'player' | 'system'
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    selections: Mapped[dict] = mapped_column(JSON, nullable=False)
    calculated_effect: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # 'pending' | 'approved' | 'rejected'
    revision_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    gm_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    gm_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    event_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    clock_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("clocks.id", ondelete="SET NULL"),
        nullable=True,
    )
    rider_event_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships.
    character: Mapped[Character | None] = relationship(
        "Character", foreign_keys="[Proposal.character_id]"
    )
    event: Mapped[Event | None] = relationship(
        "Event", foreign_keys="[Proposal.event_id]"
    )
    rider_event: Mapped[Event | None] = relationship(
        "Event", foreign_keys="[Proposal.rider_event_id]"
    )
    clock: Mapped[Clock | None] = relationship(
        "Clock", foreign_keys="[Proposal.clock_id]"
    )
