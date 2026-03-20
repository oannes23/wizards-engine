"""Campaign exporter: serialises the entire database to a YAML directory tree.

The ``CampaignExporter`` reads all entities from a SQLAlchemy session and
writes them to a YAML directory structure matching the ``campaign-data/``
format defined in Epic 7.1 Story 7.1.1.

Key design decisions
--------------------
- ULIDs are **never** written to YAML — all cross-references use
  human-readable entity names resolved through a reverse ``id → name``
  registry built at the start of export.
- Slots (traits, bonds, features, relations, holdings) are queried by
  owner and inlined into the owner's YAML file.
- Magic effects are inlined into their owning PC's YAML file.
- The location hierarchy is reflected in the directory structure: each
  location becomes a directory with a ``_location.yaml`` file inside it.
  Root-level (no-parent) locations that have no children are still written
  as ``<slug>/_location.yaml`` for consistency.
- Sessions are numbered by ULID sort order (creation time), since there is
  no ``number`` column in the ``sessions`` table.
- Stories are exported with their entries and nested children (parent stories
  first, children embedded).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.session import Session as GameSession
from wizards_engine.models.session import SessionParticipant
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.story import Story, StoryEntry, StoryOwner
from wizards_engine.models.user import User


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExportResult:
    """Summary of entities exported by :class:`CampaignExporter`.

    Attributes
    ----------
    trait_templates:
        Number of trait template YAML files written.
    locations:
        Number of location YAML files written.
    characters_pc:
        Number of PC (full detail_level) character files written.
    characters_npc:
        Number of NPC (simplified detail_level) character files written.
    groups:
        Number of group YAML files written.
    clocks:
        Number of clock YAML files written.
    users:
        Number of user YAML files written.
    sessions:
        Number of session YAML files written.
    stories:
        Number of top-level story YAML files written (children are embedded).
    """

    trait_templates: int = 0
    locations: int = 0
    characters_pc: int = 0
    characters_npc: int = 0
    groups: int = 0
    clocks: int = 0
    users: int = 0
    sessions: int = 0
    stories: int = 0


# ---------------------------------------------------------------------------
# YAML dump settings
# ---------------------------------------------------------------------------


def _dump(data: Any, fh: Any) -> None:
    """Write *data* to *fh* as human-readable YAML."""
    yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert an entity name to a filesystem-safe slug.

    Lowercases, replaces whitespace and punctuation runs with a single
    hyphen, and strips leading/trailing hyphens.

    Parameters
    ----------
    name:
        Raw entity name (e.g. ``"The Shattered Coast"``).

    Returns
    -------
    str
        URL/filename-safe slug (e.g. ``"the-shattered-coast"``).
    """
    slug = name.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Name registry
# ---------------------------------------------------------------------------


class _NameRegistry:
    """Reverse lookup: ``(entity_type, ulid) → name``.

    Built once at the start of export and consulted for every cross-reference
    that must appear as a human-readable name in the output YAML.

    The *entity_type* key must be one of the strings used in polymorphic
    reference columns: ``"character"``, ``"group"``, ``"location"``,
    ``"trait_template"``, ``"user"``, ``"session"``.
    """

    def __init__(self) -> None:
        self._map: dict[tuple[str, str], str] = {}

    def register(self, entity_type: str, ulid: str, name: str) -> None:
        """Register *name* for *(entity_type, ulid)*.

        Parameters
        ----------
        entity_type:
            The type key (e.g. ``"character"``).
        ulid:
            The entity's primary-key string.
        name:
            The human-readable display name.
        """
        self._map[(entity_type, ulid)] = name

    def resolve(self, entity_type: str, ulid: str | None) -> str | None:
        """Return the name for *(entity_type, ulid)*, or ``None`` if unknown.

        Parameters
        ----------
        entity_type:
            The type key.
        ulid:
            The entity's primary-key string.  ``None`` is passed through
            as ``None`` (convenience for optional FK columns).

        Returns
        -------
        str | None
            The registered name, or ``None`` if *ulid* is ``None`` or
            not registered.
        """
        if ulid is None:
            return None
        return self._map.get((entity_type, ulid))

    def resolve_target_ref(
        self, target_type: str | None, target_id: str | None
    ) -> dict[str, str] | None:
        """Return a ``{type, name}`` dict for a polymorphic bond target.

        Parameters
        ----------
        target_type:
            The entity type string stored in the ``target_type`` column.
        target_id:
            The ULID stored in the ``target_id`` column.

        Returns
        -------
        dict | None
            ``{"type": target_type, "name": resolved_name}`` or ``None``
            if either argument is ``None`` or the ID is unknown.
        """
        if target_type is None or target_id is None:
            return None
        name = self.resolve(target_type, target_id)
        if name is None:
            return None
        return {"type": target_type, "name": name}

    def resolve_session_number(
        self, session_id: str | None, session_numbers: dict[str, int]
    ) -> int | None:
        """Resolve a session ULID to its sequential number.

        Parameters
        ----------
        session_id:
            The ULID of the session.
        session_numbers:
            Mapping of session ULID → sequential number (derived from ULID
            sort order).

        Returns
        -------
        int | None
            The session number, or ``None`` if *session_id* is ``None``.
        """
        if session_id is None:
            return None
        return session_numbers.get(session_id)


# ---------------------------------------------------------------------------
# Main exporter
# ---------------------------------------------------------------------------


class CampaignExporter:
    """Exports the entire database to a YAML directory tree.

    Parameters
    ----------
    db:
        An open SQLAlchemy ``Session`` bound to the campaign database.
    output_dir:
        Root directory where the YAML files will be written.  Created
        if it does not exist.

    Usage::

        from pathlib import Path
        from wizards_engine.campaign.exporter import CampaignExporter

        result = CampaignExporter(db, Path("campaign-data")).export_all()
        print(result)
    """

    def __init__(self, db: Session, output_dir: Path) -> None:
        self._db = db
        self._out = output_dir
        self._registry = _NameRegistry()
        # Populated during export — maps session ULID → sequential number.
        self._session_numbers: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_all(self) -> ExportResult:
        """Export every entity to the output directory.

        Returns
        -------
        ExportResult
            Entity counts by type.
        """
        self._out.mkdir(parents=True, exist_ok=True)
        self._build_registry()
        result = ExportResult()
        result.trait_templates = self._export_trait_templates()
        result.locations = self._export_locations()
        result.characters_pc, result.characters_npc = self._export_characters()
        result.groups = self._export_groups()
        result.clocks = self._export_clocks()
        result.users = self._export_users()
        result.sessions = self._export_sessions()
        result.stories = self._export_stories()
        self._export_meta()
        return result

    # ------------------------------------------------------------------
    # Registry construction
    # ------------------------------------------------------------------

    def _build_registry(self) -> None:
        """Query all entities and populate the reverse id→name registry."""
        for tt in self._db.execute(select(TraitTemplate)).scalars():
            self._registry.register("trait_template", tt.id, tt.name)

        for char in self._db.execute(select(Character)).scalars():
            self._registry.register("character", char.id, char.name)

        for grp in self._db.execute(select(Group)).scalars():
            self._registry.register("group", grp.id, grp.name)

        for loc in self._db.execute(select(Location)).scalars():
            self._registry.register("location", loc.id, loc.name)

        for user in self._db.execute(select(User)).scalars():
            self._registry.register("user", user.id, user.display_name)

        sessions = list(
            self._db.execute(select(GameSession).order_by(GameSession.id)).scalars()
        )
        for idx, session in enumerate(sessions, start=1):
            self._registry.register("session", session.id, str(idx))
            self._session_numbers[session.id] = idx

    # ------------------------------------------------------------------
    # Trait templates
    # ------------------------------------------------------------------

    def _export_trait_templates(self) -> int:
        """Write each trait template to ``trait-templates/<slug>.yaml``.

        Returns
        -------
        int
            Number of files written.
        """
        tt_dir = self._out / "trait-templates"
        tt_dir.mkdir(parents=True, exist_ok=True)

        templates = list(
            self._db.execute(
                select(TraitTemplate).where(TraitTemplate.is_deleted == False)  # noqa: E712
            ).scalars()
        )
        for tt in templates:
            data = {
                "name": tt.name,
                "type": tt.type,
                "description": tt.description,
            }
            slug = _slugify(tt.name)
            with open(tt_dir / f"{slug}.yaml", "w", encoding="utf-8") as fh:
                _dump(data, fh)

        return len(templates)

    # ------------------------------------------------------------------
    # Locations
    # ------------------------------------------------------------------

    def _build_location_path(
        self,
        loc: Location,
        location_by_id: dict[str, Location],
    ) -> Path:
        """Return the relative directory path for *loc* within the output tree.

        Each ancestor location contributes a directory segment (slugified name).
        The location itself is also a directory containing ``_location.yaml``.

        Parameters
        ----------
        loc:
            The location to compute the path for.
        location_by_id:
            All locations keyed by their ULID, for parent chain traversal.

        Returns
        -------
        Path
            Relative path from the locations root directory, e.g.
            ``Path("the-shattered-coast/old-quarter")``.
        """
        parts: list[str] = []
        current = loc
        while current is not None:
            parts.append(_slugify(current.name))
            parent_id = current.parent_id
            current = location_by_id.get(parent_id) if parent_id else None
        parts.reverse()
        return Path(*parts) if parts else Path(_slugify(loc.name))

    def _export_locations(self) -> int:
        """Write each location to ``locations/<path>/_location.yaml``.

        The directory structure mirrors the location hierarchy: each location
        becomes a directory, and its YAML data lives in ``_location.yaml``
        inside that directory.

        Returns
        -------
        int
            Number of location files written.
        """
        loc_root = self._out / "locations"
        loc_root.mkdir(parents=True, exist_ok=True)

        locations = list(
            self._db.execute(
                select(Location).where(Location.is_deleted == False)  # noqa: E712
            ).scalars()
        )
        location_by_id: dict[str, Location] = {loc.id: loc for loc in locations}

        for loc in locations:
            rel_path = self._build_location_path(loc, location_by_id)
            loc_dir = loc_root / rel_path
            loc_dir.mkdir(parents=True, exist_ok=True)

            # Resolve parent name (from the registry).
            parent_name = self._registry.resolve("location", loc.parent_id)

            # Collect slots.
            slots = self._get_slots_for_owner("location", loc.id)
            features = [
                self._slot_to_feature(s) for s in slots if s.slot_type == "feature_trait"
            ]
            bonds = [
                self._slot_to_location_bond(s) for s in slots if s.slot_type == "location_bond"
            ]

            data: dict[str, Any] = {"name": loc.name}
            if loc.description:
                data["description"] = loc.description
            if loc.notes:
                data["notes"] = loc.notes
            if parent_name:
                data["parent"] = parent_name
            if features:
                data["features"] = features
            if bonds:
                data["bonds"] = bonds

            with open(loc_dir / "_location.yaml", "w", encoding="utf-8") as fh:
                _dump(data, fh)

        return len(locations)

    # ------------------------------------------------------------------
    # Characters
    # ------------------------------------------------------------------

    def _export_characters(self) -> tuple[int, int]:
        """Write characters to ``characters/pcs/`` and ``characters/npcs/``.

        Full (PC) characters go to ``pcs/``, simplified (NPC) characters
        go to ``npcs/``.

        Returns
        -------
        tuple[int, int]
            ``(pc_count, npc_count)``
        """
        pcs_dir = self._out / "characters" / "pcs"
        npcs_dir = self._out / "characters" / "npcs"
        pcs_dir.mkdir(parents=True, exist_ok=True)
        npcs_dir.mkdir(parents=True, exist_ok=True)

        characters = list(
            self._db.execute(
                select(Character).where(Character.is_deleted == False)  # noqa: E712
            ).scalars()
        )

        pc_count = 0
        npc_count = 0

        for char in characters:
            if char.detail_level == "full":
                data = self._build_pc_data(char)
                out_dir = pcs_dir
                pc_count += 1
            else:
                data = self._build_npc_data(char)
                out_dir = npcs_dir
                npc_count += 1

            slug = _slugify(char.name)
            with open(out_dir / f"{slug}.yaml", "w", encoding="utf-8") as fh:
                _dump(data, fh)

        return pc_count, npc_count

    def _build_pc_data(self, char: Character) -> dict[str, Any]:
        """Build the YAML dict for a full (PC) character.

        Parameters
        ----------
        char:
            A ``Character`` ORM instance with ``detail_level="full"``.

        Returns
        -------
        dict
            A dict that validates as ``PCCharacterYaml``.
        """
        slots = self._get_slots_for_owner("character", char.id)

        core_traits = [
            self._slot_to_pc_trait(s) for s in slots if s.slot_type == "core_trait"
        ]
        role_traits = [
            self._slot_to_pc_trait(s) for s in slots if s.slot_type == "role_trait"
        ]
        bonds = [
            self._slot_to_pc_bond(s) for s in slots if s.slot_type == "pc_bond"
        ]

        # Magic effects.
        effects_orm = list(
            self._db.execute(
                select(MagicEffect).where(MagicEffect.character_id == char.id)
            ).scalars()
        )
        magic_effects = [self._magic_effect_to_yaml(e) for e in effects_orm]

        data: dict[str, Any] = {
            "name": char.name,
            "detail_level": "full",
        }
        if char.description:
            data["description"] = char.description
        if char.notes:
            data["notes"] = char.notes
        if char.attributes:
            data["attributes"] = char.attributes
        data["meters"] = {
            "stress": char.stress or 0,
            "free_time": char.free_time or 0,
            "plot": char.plot or 0,
            "gnosis": char.gnosis or 0,
        }
        data["skills"] = char.skills or {
            "awareness": 0,
            "composure": 0,
            "influence": 0,
            "finesse": 0,
            "speed": 0,
            "power": 0,
            "knowledge": 0,
            "technology": 0,
        }
        data["magic_stats"] = char.magic_stats or {
            "being": {"level": 0, "xp": 0},
            "wyrding": {"level": 0, "xp": 0},
            "summoning": {"level": 0, "xp": 0},
            "enchanting": {"level": 0, "xp": 0},
            "dreaming": {"level": 0, "xp": 0},
        }
        if core_traits:
            data["core_traits"] = core_traits
        if role_traits:
            data["role_traits"] = role_traits
        if bonds:
            data["bonds"] = bonds
        if magic_effects:
            data["magic_effects"] = magic_effects

        return data

    def _build_npc_data(self, char: Character) -> dict[str, Any]:
        """Build the YAML dict for a simplified (NPC) character.

        Parameters
        ----------
        char:
            A ``Character`` ORM instance with ``detail_level="simplified"``.

        Returns
        -------
        dict
            A dict that validates as ``NPCCharacterYaml``.
        """
        slots = self._get_slots_for_owner("character", char.id)
        bonds = [
            self._slot_to_npc_bond(s) for s in slots if s.slot_type == "npc_bond"
        ]

        data: dict[str, Any] = {
            "name": char.name,
            "detail_level": "simplified",
        }
        if char.description:
            data["description"] = char.description
        if char.notes:
            data["notes"] = char.notes
        if char.attributes:
            data["attributes"] = char.attributes
        if bonds:
            data["bonds"] = bonds

        return data

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def _export_groups(self) -> int:
        """Write each group to ``groups/<slug>.yaml``.

        Returns
        -------
        int
            Number of group files written.
        """
        grp_dir = self._out / "groups"
        grp_dir.mkdir(parents=True, exist_ok=True)

        groups = list(
            self._db.execute(
                select(Group).where(Group.is_deleted == False)  # noqa: E712
            ).scalars()
        )

        for grp in groups:
            slots = self._get_slots_for_owner("group", grp.id)
            traits = [
                self._slot_to_group_trait(s) for s in slots if s.slot_type == "group_trait"
            ]
            relations = [
                self._slot_to_group_relation(s)
                for s in slots
                if s.slot_type == "group_relation"
            ]
            holdings = [
                self._slot_to_group_holding(s)
                for s in slots
                if s.slot_type == "group_holding"
            ]

            data: dict[str, Any] = {
                "name": grp.name,
                "tier": grp.tier,
            }
            if grp.description:
                data["description"] = grp.description
            if grp.notes:
                data["notes"] = grp.notes
            if traits:
                data["traits"] = traits
            if relations:
                data["relations"] = relations
            if holdings:
                data["holdings"] = holdings

            slug = _slugify(grp.name)
            with open(grp_dir / f"{slug}.yaml", "w", encoding="utf-8") as fh:
                _dump(data, fh)

        return len(groups)

    # ------------------------------------------------------------------
    # Clocks
    # ------------------------------------------------------------------

    def _export_clocks(self) -> int:
        """Write each clock to ``clocks/<slug>.yaml``.

        Returns
        -------
        int
            Number of clock files written.
        """
        clk_dir = self._out / "clocks"
        clk_dir.mkdir(parents=True, exist_ok=True)

        clocks = list(
            self._db.execute(
                select(Clock).where(Clock.is_deleted == False)  # noqa: E712
            ).scalars()
        )

        for clk in clocks:
            associated_with = self._registry.resolve_target_ref(
                clk.associated_type, clk.associated_id
            )

            data: dict[str, Any] = {
                "name": clk.name,
                "segments": clk.segments,
                "progress": clk.progress,
            }
            if associated_with:
                data["associated_with"] = associated_with
            if clk.notes:
                data["notes"] = clk.notes

            slug = _slugify(clk.name)
            with open(clk_dir / f"{slug}.yaml", "w", encoding="utf-8") as fh:
                _dump(data, fh)

        return len(clocks)

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def _export_users(self) -> int:
        """Write each user to ``users/<slug>.yaml``.

        Returns
        -------
        int
            Number of user files written.
        """
        usr_dir = self._out / "users"
        usr_dir.mkdir(parents=True, exist_ok=True)

        users = list(
            self._db.execute(
                select(User).where(User.is_active == True)  # noqa: E712
            ).scalars()
        )

        for user in users:
            character_name = self._registry.resolve("character", user.character_id)

            data: dict[str, Any] = {
                "display_name": user.display_name,
                "role": user.role,
            }
            if character_name:
                data["character"] = character_name

            slug = _slugify(user.display_name)
            with open(usr_dir / f"{slug}.yaml", "w", encoding="utf-8") as fh:
                _dump(data, fh)

        return len(users)

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def _export_sessions(self) -> int:
        """Write each session to ``sessions/<number>-<slug>.yaml``.

        Session numbers are derived from ULID sort order (ascending creation
        time), since the ``sessions`` table has no ``number`` column.

        Returns
        -------
        int
            Number of session files written.
        """
        sess_dir = self._out / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)

        sessions = list(
            self._db.execute(
                select(GameSession).order_by(GameSession.id)
            ).scalars()
        )

        for idx, sess in enumerate(sessions, start=1):
            # Resolve participants.
            participants_orm = list(
                self._db.execute(
                    select(SessionParticipant).where(
                        SessionParticipant.session_id == sess.id
                    )
                ).scalars()
            )
            participants = []
            for p in participants_orm:
                char_name = self._registry.resolve("character", p.character_id)
                if char_name:
                    p_data: dict[str, Any] = {"character": char_name}
                    if p.additional_contribution:
                        p_data["additional_contribution"] = True
                    participants.append(p_data)

            data: dict[str, Any] = {
                "number": idx,
                "status": sess.status,
            }
            if sess.time_now is not None:
                data["time_now"] = sess.time_now
            if sess.date is not None:
                data["date"] = sess.date.isoformat()
            if sess.summary:
                data["summary"] = sess.summary
            if sess.notes:
                data["notes"] = sess.notes
            if participants:
                data["participants"] = participants

            # Filename: zero-padded number + slugified summary/id.
            number_str = str(idx).zfill(3)
            if sess.summary:
                slug = _slugify(sess.summary[:40])
            else:
                slug = f"session-{idx}"
            filename = f"{number_str}-{slug}.yaml"

            with open(sess_dir / filename, "w", encoding="utf-8") as fh:
                _dump(data, fh)

        return len(sessions)

    # ------------------------------------------------------------------
    # Stories
    # ------------------------------------------------------------------

    def _export_stories(self) -> int:
        """Write each top-level story to ``stories/<slug>.yaml``.

        Child stories are embedded as ``children`` within their parent's YAML
        rather than being written to separate files.

        Returns
        -------
        int
            Number of top-level story files written.
        """
        story_dir = self._out / "stories"
        story_dir.mkdir(parents=True, exist_ok=True)

        # Collect all stories; separate top-level from children.
        all_stories = list(
            self._db.execute(
                select(Story).where(Story.is_deleted == False)  # noqa: E712
            ).scalars()
        )

        # Index by id for child lookup.
        story_by_id: dict[str, Story] = {s.id: s for s in all_stories}
        # Collect children grouped by parent_id.
        children_by_parent: dict[str, list[Story]] = {}
        top_level: list[Story] = []
        for story in all_stories:
            if story.parent_id is None:
                top_level.append(story)
            else:
                children_by_parent.setdefault(story.parent_id, []).append(story)

        top_level_count = 0
        for story in top_level:
            data = self._build_story_data(story, children_by_parent)
            slug = _slugify(story.name)
            with open(story_dir / f"{slug}.yaml", "w", encoding="utf-8") as fh:
                _dump(data, fh)
            top_level_count += 1

        return top_level_count

    def _build_story_data(
        self,
        story: Story,
        children_by_parent: dict[str, list[Story]],
    ) -> dict[str, Any]:
        """Build the YAML dict for a story and its nested children.

        Parameters
        ----------
        story:
            The ``Story`` ORM instance to serialise.
        children_by_parent:
            All child stories grouped by parent ULID.

        Returns
        -------
        dict
            A dict that validates as ``StoryYaml``.
        """
        # Owners.
        owners_orm = list(
            self._db.execute(
                select(StoryOwner).where(StoryOwner.story_id == story.id)
            ).scalars()
        )
        owners = []
        for o in owners_orm:
            owner_name = self._registry.resolve(o.owner_type, o.owner_id)
            if owner_name:
                owners.append({"type": o.owner_type, "name": owner_name})

        # Entries — ordered by created_at.
        entries_orm = list(
            self._db.execute(
                select(StoryEntry)
                .where(StoryEntry.story_id == story.id)
                .where(StoryEntry.is_deleted == False)  # noqa: E712
                .order_by(StoryEntry.created_at)
            ).scalars()
        )
        entries = []
        for e in entries_orm:
            author_name = self._registry.resolve("user", e.author_id)
            char_name = self._registry.resolve("character", e.character_id)
            session_num = self._session_numbers.get(e.session_id) if e.session_id else None
            entry_data: dict[str, Any] = {
                "text": e.text,
                "author": author_name or e.author_id,
            }
            if char_name:
                entry_data["character"] = char_name
            if session_num is not None:
                entry_data["session"] = session_num
            entries.append(entry_data)

        # Children — recurse.
        child_stories = children_by_parent.get(story.id, [])
        children = [
            self._build_story_data(child, children_by_parent) for child in child_stories
        ]

        data: dict[str, Any] = {"name": story.name}
        if story.summary:
            data["summary"] = story.summary
        data["status"] = story.status
        if story.tags:
            data["tags"] = story.tags
        if owners:
            data["owners"] = owners
        if entries:
            data["entries"] = entries
        if children:
            data["children"] = children

        return data

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    def _export_meta(self) -> None:
        """Write ``meta.yaml`` with engine version and export timestamp."""
        try:
            from importlib.metadata import version

            engine_version = version("wizards-engine")
        except Exception:
            engine_version = "0.1.0"

        data = {
            "engine_version": engine_version,
            "campaign_name": "Campaign",
            "format_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(self._out / "meta.yaml", "w", encoding="utf-8") as fh:
            _dump(data, fh)

    # ------------------------------------------------------------------
    # Slot helpers — query
    # ------------------------------------------------------------------

    def _get_slots_for_owner(self, owner_type: str, owner_id: str) -> list[Slot]:
        """Return all slots whose ``owner_type``/``owner_id`` match.

        Parameters
        ----------
        owner_type:
            The ``owner_type`` column value to match.
        owner_id:
            The ``owner_id`` column value to match.

        Returns
        -------
        list[Slot]
            All matching Slot ORM instances, ordered by ``id`` (creation time).
        """
        return list(
            self._db.execute(
                select(Slot)
                .where(Slot.owner_type == owner_type)
                .where(Slot.owner_id == owner_id)
                .order_by(Slot.id)
            ).scalars()
        )

    # ------------------------------------------------------------------
    # Slot helpers — serialisation
    # ------------------------------------------------------------------

    def _slot_to_pc_trait(self, slot: Slot) -> dict[str, Any]:
        """Serialise a ``core_trait`` or ``role_trait`` slot to YAML dict.

        Parameters
        ----------
        slot:
            A Slot with ``slot_type`` in ``{"core_trait", "role_trait"}``.

        Returns
        -------
        dict
            A dict that validates as ``PCTraitYaml``.
        """
        template_name = self._registry.resolve("trait_template", slot.template_id)
        data: dict[str, Any] = {
            "template": template_name or slot.name,
            "charge": slot.charge if slot.charge is not None else 5,
            "is_active": slot.is_active,
        }
        return data

    def _slot_to_pc_bond(self, slot: Slot) -> dict[str, Any]:
        """Serialise a ``pc_bond`` slot to YAML dict.

        Parameters
        ----------
        slot:
            A Slot with ``slot_type="pc_bond"``.

        Returns
        -------
        dict
            A dict that validates as ``PCBondYaml``.
        """
        target_ref = self._registry.resolve_target_ref(slot.target_type, slot.target_id)
        data: dict[str, Any] = {
            "name": slot.name,
            "target": target_ref or {"type": slot.target_type or "character", "name": "Unknown"},
        }
        if slot.description:
            data["description"] = slot.description

        labels: dict[str, str] = {}
        if slot.source_label:
            labels["source"] = slot.source_label
        if slot.target_label:
            labels["target"] = slot.target_label
        if labels:
            data["labels"] = labels

        data["charges"] = slot.charges if slot.charges is not None else 5
        data["degradations"] = slot.degradations if slot.degradations is not None else 0
        data["is_trauma"] = bool(slot.is_trauma)
        data["is_active"] = slot.is_active
        return data

    def _slot_to_npc_bond(self, slot: Slot) -> dict[str, Any]:
        """Serialise an ``npc_bond`` slot to YAML dict.

        Parameters
        ----------
        slot:
            A Slot with ``slot_type="npc_bond"``.

        Returns
        -------
        dict
            A dict that validates as ``NPCBondYaml``.
        """
        target_ref = self._registry.resolve_target_ref(slot.target_type, slot.target_id)
        data: dict[str, Any] = {
            "name": slot.name,
            "target": target_ref or {"type": slot.target_type or "character", "name": "Unknown"},
        }
        if slot.description:
            data["description"] = slot.description

        labels: dict[str, str] = {}
        if slot.source_label:
            labels["source"] = slot.source_label
        if slot.target_label:
            labels["target"] = slot.target_label
        if labels:
            data["labels"] = labels

        data["bidirectional"] = bool(slot.bidirectional) if slot.bidirectional is not None else False
        data["is_active"] = slot.is_active
        return data

    def _slot_to_group_trait(self, slot: Slot) -> dict[str, Any]:
        """Serialise a ``group_trait`` slot to YAML dict.

        Parameters
        ----------
        slot:
            A Slot with ``slot_type="group_trait"``.

        Returns
        -------
        dict
            A dict that validates as ``GroupTraitYaml``.
        """
        data: dict[str, Any] = {"name": slot.name, "is_active": slot.is_active}
        if slot.description:
            data["description"] = slot.description
        return data

    def _slot_to_group_relation(self, slot: Slot) -> dict[str, Any]:
        """Serialise a ``group_relation`` slot to YAML dict.

        The target is always another group — stored as a plain name string.

        Parameters
        ----------
        slot:
            A Slot with ``slot_type="group_relation"``.

        Returns
        -------
        dict
            A dict that validates as ``GroupRelationYaml``.
        """
        target_name = self._registry.resolve("group", slot.target_id) or "Unknown"
        data: dict[str, Any] = {
            "name": slot.name,
            "target": target_name,
            "bidirectional": bool(slot.bidirectional) if slot.bidirectional is not None else False,
            "is_active": slot.is_active,
        }
        if slot.description:
            data["description"] = slot.description

        labels: dict[str, str] = {}
        if slot.source_label:
            labels["source"] = slot.source_label
        if slot.target_label:
            labels["target"] = slot.target_label
        if labels:
            data["labels"] = labels

        return data

    def _slot_to_group_holding(self, slot: Slot) -> dict[str, Any]:
        """Serialise a ``group_holding`` slot to YAML dict.

        The target is always a location — stored as a plain name string.

        Parameters
        ----------
        slot:
            A Slot with ``slot_type="group_holding"``.

        Returns
        -------
        dict
            A dict that validates as ``GroupHoldingYaml``.
        """
        target_name = self._registry.resolve("location", slot.target_id) or "Unknown"
        data: dict[str, Any] = {
            "name": slot.name,
            "target": target_name,
            "is_active": slot.is_active,
        }
        if slot.description:
            data["description"] = slot.description
        return data

    def _slot_to_feature(self, slot: Slot) -> dict[str, Any]:
        """Serialise a ``feature_trait`` slot to YAML dict.

        Parameters
        ----------
        slot:
            A Slot with ``slot_type="feature_trait"``.

        Returns
        -------
        dict
            A dict that validates as ``LocationFeatureYaml``.
        """
        data: dict[str, Any] = {"name": slot.name, "is_active": slot.is_active}
        if slot.description:
            data["description"] = slot.description
        return data

    def _slot_to_location_bond(self, slot: Slot) -> dict[str, Any]:
        """Serialise a ``location_bond`` slot to YAML dict.

        Parameters
        ----------
        slot:
            A Slot with ``slot_type="location_bond"``.

        Returns
        -------
        dict
            A dict that validates as ``LocationBondYaml``.
        """
        target_ref = self._registry.resolve_target_ref(slot.target_type, slot.target_id)
        data: dict[str, Any] = {
            "name": slot.name,
            "target": target_ref or {"type": slot.target_type or "character", "name": "Unknown"},
            "is_active": slot.is_active,
        }
        if slot.description:
            data["description"] = slot.description

        labels: dict[str, str] = {}
        if slot.source_label:
            labels["source"] = slot.source_label
        if slot.target_label:
            labels["target"] = slot.target_label
        if labels:
            data["labels"] = labels

        return data

    # ------------------------------------------------------------------
    # Magic effect serialisation
    # ------------------------------------------------------------------

    def _magic_effect_to_yaml(self, effect: MagicEffect) -> dict[str, Any]:
        """Serialise a ``MagicEffect`` to YAML dict.

        Parameters
        ----------
        effect:
            A ``MagicEffect`` ORM instance.

        Returns
        -------
        dict
            A dict that validates as ``MagicEffectYaml``.
        """
        data: dict[str, Any] = {
            "name": effect.name,
            "description": effect.description,
            "effect_type": effect.effect_type,
            "power_level": effect.power_level,
            "is_active": effect.is_active,
        }
        if effect.effect_type == "charged" and effect.charges_current is not None:
            data["charges"] = {
                "current": effect.charges_current,
                "max": effect.charges_max,
            }
        return data
