"""Models package — SQLAlchemy ORM models for all database tables.

Import order matters: models with no cross-model dependencies first, then
models that reference them.  All models must be imported here so that
SQLAlchemy's mapper registry is fully populated before ``configure_mappers()``
is called (which happens on the first query or explicit call).

Tables (18 total):
  Auth:           users, invites
  Game Objects:   characters, groups, locations
  Slots:          trait_templates, slots
  Character sub:  magic_effects
  System:         clocks, sessions, session_participants
  Narrative:      stories, story_owners, story_entries
  Events:         events, event_targets
  Workflow:       proposals
  Prefs:          starred_objects
"""

# Base must be imported first so the DeclarativeBase is available.
from wizards_engine.models.base import Base, TimestampMixin  # noqa: F401

# Auth — no cross-model dependencies at the column level.
from wizards_engine.models.user import Invite, User  # noqa: F401

# Game Objects — independent of each other.
from wizards_engine.models.character import Character  # noqa: F401
from wizards_engine.models.group import Group  # noqa: F401
from wizards_engine.models.location import Location  # noqa: F401

# Slots catalog — TraitTemplate is independent; Slot FKs trait_templates.
from wizards_engine.models.slot import Slot, TraitTemplate  # noqa: F401

# Character sub-entities — MagicEffect FKs characters.
from wizards_engine.models.magic_effect import MagicEffect  # noqa: F401

# System entities.
from wizards_engine.models.clock import Clock  # noqa: F401
from wizards_engine.models.session import Session, SessionParticipant  # noqa: F401

# Narrative — Story is self-referential; StoryEntry FKs users, characters,
# sessions, and events (events not yet imported at this point — FK resolved
# lazily by SQLAlchemy from the string "events.id").
from wizards_engine.models.story import Story, StoryEntry, StoryOwner  # noqa: F401

# Events — Event FKs users, proposals (forward ref), sessions, and itself.
# EventTarget FKs events.  Proposals FKs events (circular with Event.proposal_id);
# SQLAlchemy resolves this via deferred FK strings.
from wizards_engine.models.event import Event, EventTarget  # noqa: F401

# Proposals — FKs characters, events, clocks.
from wizards_engine.models.proposal import Proposal  # noqa: F401

# User preferences.
from wizards_engine.models.starred import StarredObject  # noqa: F401

__all__ = [
    "Base",
    "TimestampMixin",
    # Auth
    "User",
    "Invite",
    # Game Objects
    "Character",
    "Group",
    "Location",
    # Slots
    "TraitTemplate",
    "Slot",
    # Character sub-entities
    "MagicEffect",
    # System entities
    "Clock",
    "Session",
    "SessionParticipant",
    # Narrative
    "Story",
    "StoryOwner",
    "StoryEntry",
    # Events
    "Event",
    "EventTarget",
    # Workflow
    "Proposal",
    # Preferences
    "StarredObject",
]
