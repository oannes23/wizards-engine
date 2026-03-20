"""Campaign YAML importer — populates the database from a YAML directory.

Reads the 6-phase import order defined in ``ordering.py`` and creates all
entities in dependency order.  All cross-references are resolved via the
``NameResolver`` (name-based strings → database ULIDs).

Usage::

    from pathlib import Path
    from sqlalchemy.orm import Session
    from wizards_engine.campaign.importer import CampaignImporter

    importer = CampaignImporter(db, Path("campaign-data/"))
    result = importer.import_all()
    print(result)

Design decisions
----------------
- Fresh ULIDs for every entity (ULIDs from YAML are never used).
- Validation runs before any DB writes (fail-fast on schema/ref errors).
- The entire import is atomic: a single transaction that rolls back on any
  error.
- ``dry_run=True`` runs all validation and reports counts but does not commit.
- ``force=True`` allows importing into a non-empty database.
- ``secrets`` YAML fields are appended to the entity ``notes`` column with a
  separator line.
"""

from __future__ import annotations

import datetime
import secrets as _secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wizards_engine.campaign.exceptions import CampaignValidationError
from wizards_engine.campaign.ordering import topological_sort_locations
from wizards_engine.campaign.resolver import NameResolver
from wizards_engine.campaign.schemas import (
    ClockYaml,
    GroupYaml,
    LocationYaml,
    NPCCharacterYaml,
    PCCharacterYaml,
    SessionYaml,
    StoryYaml,
    TraitTemplateYaml,
    UserYaml,
)
from wizards_engine.campaign.validators import validate_campaign
from wizards_engine.models.character import Character
from wizards_engine.models.clock import Clock
from wizards_engine.models.group import Group
from wizards_engine.models.location import Location
from wizards_engine.models.magic_effect import MagicEffect
from wizards_engine.models.session import Session as SessionModel
from wizards_engine.models.session import SessionParticipant
from wizards_engine.models.slot import Slot, TraitTemplate
from wizards_engine.models.story import Story, StoryEntry, StoryOwner
from wizards_engine.models.user import User

__all__ = ["CampaignImporter", "ImportResult"]

_SECRETS_SEPARATOR = "\n\n---\nSECRETS:\n"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    """Summary of a completed (or dry-run) import operation.

    Attributes
    ----------
    trait_templates:
        Number of TraitTemplate rows created.
    locations:
        Number of Location rows created.
    characters:
        Number of Character rows created.
    groups:
        Number of Group rows created.
    slots:
        Number of Slot rows created.
    magic_effects:
        Number of MagicEffect rows created.
    clocks:
        Number of Clock rows created.
    users:
        Number of User rows created.
    sessions:
        Number of Session rows created.
    session_participants:
        Number of SessionParticipant rows created.
    stories:
        Number of Story rows created.
    story_owners:
        Number of StoryOwner rows created.
    story_entries:
        Number of StoryEntry rows created.
    warnings:
        Non-fatal messages collected during import.
    dry_run:
        ``True`` if no data was committed to the database.
    """

    trait_templates: int = 0
    locations: int = 0
    characters: int = 0
    groups: int = 0
    slots: int = 0
    magic_effects: int = 0
    clocks: int = 0
    users: int = 0
    sessions: int = 0
    session_participants: int = 0
    stories: int = 0
    story_owners: int = 0
    story_entries: int = 0
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False

    def total_entities(self) -> int:
        """Return the sum of all entity counts."""
        return (
            self.trait_templates
            + self.locations
            + self.characters
            + self.groups
            + self.slots
            + self.magic_effects
            + self.clocks
            + self.users
            + self.sessions
            + self.session_participants
            + self.stories
            + self.story_owners
            + self.story_entries
        )

    def __repr__(self) -> str:
        status = "dry-run" if self.dry_run else "committed"
        return (
            f"ImportResult({status}, total={self.total_entities()}, "
            f"trait_templates={self.trait_templates}, "
            f"locations={self.locations}, "
            f"characters={self.characters}, "
            f"groups={self.groups}, "
            f"slots={self.slots}, "
            f"magic_effects={self.magic_effects}, "
            f"clocks={self.clocks}, "
            f"users={self.users}, "
            f"sessions={self.sessions}, "
            f"stories={self.stories}, "
            f"warnings={len(self.warnings)})"
        )


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """Load a YAML file. Returns ``None`` if the file is empty."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _append_secrets(notes: str | None, secrets: str | None) -> str | None:
    """Append a secrets block to a notes string.

    If ``secrets`` is ``None`` or empty, returns ``notes`` unchanged.
    If ``notes`` is ``None``, returns only the secrets block (with separator).

    Args:
        notes: The existing notes text, or ``None``.
        secrets: The secrets text to append, or ``None``.

    Returns:
        Combined notes string, or ``None`` if both inputs are ``None``.
    """
    if not secrets:
        return notes
    secrets_block = _SECRETS_SEPARATOR + secrets
    if notes:
        return notes + secrets_block
    return secrets_block



# ---------------------------------------------------------------------------
# CampaignImporter
# ---------------------------------------------------------------------------


class CampaignImporter:
    """Reads a YAML campaign directory and populates the database.

    Parameters
    ----------
    db:
        An open SQLAlchemy session.
    input_dir:
        Path to the root campaign directory (the directory that contains
        ``meta.yaml``, ``characters/``, ``groups/``, etc.).
    """

    def __init__(self, db: Session, input_dir: Path) -> None:
        self._db = db
        self._input_dir = input_dir
        self._resolver = NameResolver()
        # Maps session number (int) → Session ORM id (str)
        self._session_by_number: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def import_all(self, dry_run: bool = False, force: bool = False) -> ImportResult:
        """Import the entire campaign directory into the database.

        Parameters
        ----------
        dry_run:
            If ``True``, run validation and count what would be created,
            but do not commit any data to the database.  The session is
            rolled back after counting.
        force:
            If ``True``, allow importing into a non-empty database.  The
            existing data is NOT deleted — new entities are added alongside
            it.

        Returns
        -------
        ImportResult
            Entity counts and warnings.

        Raises
        ------
        ValueError
            If validation fails (schema or reference errors).
        RuntimeError
            If the database is non-empty and ``force=False``.
        """
        # --- Step 1: validate first (fail-fast) ---
        errors = validate_campaign(self._input_dir)
        if errors:
            messages = [
                f"{e.file_path}:{e.field}: {e.error_message}" for e in errors
            ]
            raise ValueError(
                f"Campaign validation failed with {len(errors)} error(s):\n"
                + "\n".join(messages)
            )

        # --- Step 2: non-empty DB check ---
        if not force:
            self._check_empty_db()

        # --- Step 3: run import phases (all in one transaction) ---
        result = ImportResult(dry_run=dry_run)
        try:
            self._phase1_trait_templates_and_locations(result)
            self._phase2_groups_and_characters(result)
            self._phase3_slots_and_magic_effects(result)
            self._phase4_clocks(result)
            self._phase5_users(result)
            self._phase6_sessions_and_stories(result)

            if dry_run:
                self._db.rollback()
            else:
                self._db.commit()

        except Exception:
            self._db.rollback()
            raise

        return result

    # ------------------------------------------------------------------
    # Private: non-empty DB check
    # ------------------------------------------------------------------

    def _check_empty_db(self) -> None:
        """Raise RuntimeError if the database contains any Characters.

        Using Character as a proxy for "has data" — if there are any
        characters, the DB is considered non-empty.

        Raises
        ------
        RuntimeError
            If the database contains data.
        """
        count = self._db.execute(
            select(func.count()).select_from(Character)
        ).scalar_one()
        if count > 0:
            raise RuntimeError(
                f"Database is not empty ({count} character(s) found). "
                "Use force=True to import into a non-empty database."
            )

    # ------------------------------------------------------------------
    # Phase 1 — Trait templates + Locations
    # ------------------------------------------------------------------

    def _phase1_trait_templates_and_locations(self, result: ImportResult) -> None:
        """Create TraitTemplate and Location rows.

        Trait templates are created first (no dependencies).
        Locations are topologically sorted so parents are created before
        children.
        """
        self._import_trait_templates(result)
        self._import_locations(result)
        self._db.flush()

    def _import_trait_templates(self, result: ImportResult) -> None:
        """Read ``trait-templates/*.yaml`` and create TraitTemplate rows."""
        tt_dir = self._input_dir / "trait-templates"
        if not tt_dir.is_dir():
            return

        for path in sorted(tt_dir.glob("*.yaml")):
            raw = _load_yaml(path)
            if not raw:
                continue
            tt_yaml = TraitTemplateYaml.model_validate(raw)

            row = TraitTemplate(
                name=tt_yaml.name,
                description=tt_yaml.description,
                type=tt_yaml.type,
            )
            self._db.add(row)
            self._db.flush()

            self._resolver.register("trait_template", tt_yaml.name, row.id)
            result.trait_templates += 1

    def _import_locations(self, result: ImportResult) -> None:
        """Read ``locations/**/_location.yaml`` and create Location rows.

        Uses topological sort to ensure parent locations exist before
        children.  The parent is inferred from the YAML ``parent`` field
        (explicit override) or from directory structure.
        """
        loc_dir = self._input_dir / "locations"
        if not loc_dir.is_dir():
            return

        # Collect all _location.yaml files with their parsed content.
        loc_items: list[dict[str, Any]] = []
        for path in sorted(loc_dir.rglob("_location.yaml")):
            raw = _load_yaml(path)
            if not raw:
                continue
            loc_yaml = LocationYaml.model_validate(raw)

            # Determine parent from YAML field (explicit override) or directory.
            parent_name = loc_yaml.parent
            if parent_name is None:
                parent_name = self._infer_location_parent(path, loc_dir)

            loc_items.append({
                "name": loc_yaml.name,
                "parent": parent_name,
                "yaml": loc_yaml,
                "path": path,
            })

        if not loc_items:
            return

        # Topological sort: parents before children.
        sorted_items = topological_sort_locations(loc_items)

        for item in sorted_items:
            loc_yaml: LocationYaml = item["yaml"]

            parent_id: str | None = None
            if item["parent"] is not None:
                parent_id = self._resolver.resolve("location", item["parent"])

            row = Location(
                name=loc_yaml.name,
                description=loc_yaml.description,
                notes=loc_yaml.notes,
                parent_id=parent_id,
            )
            self._db.add(row)
            self._db.flush()

            self._resolver.register("location", loc_yaml.name, row.id)
            result.locations += 1

    def _infer_location_parent(self, path: Path, loc_dir: Path) -> str | None:
        """Infer a location's parent name from its directory position.

        A ``_location.yaml`` at ``locations/foo/bar/_location.yaml``
        has parent ``locations/foo/_location.yaml`` (if that exists).
        The parent name is read from that file.

        Args:
            path: The path to the child ``_location.yaml``.
            loc_dir: The root ``locations/`` directory.

        Returns:
            The parent location name string, or ``None`` for root locations.
        """
        parent_dir = path.parent.parent
        if parent_dir == loc_dir:
            # This is a top-level location directory — no parent.
            return None

        parent_location_file = parent_dir / "_location.yaml"
        if not parent_location_file.exists():
            return None

        raw = _load_yaml(parent_location_file)
        if not raw:
            return None

        parent_yaml = LocationYaml.model_validate(raw)
        return parent_yaml.name

    # ------------------------------------------------------------------
    # Phase 2 — Groups + Characters (core fields only)
    # ------------------------------------------------------------------

    def _phase2_groups_and_characters(self, result: ImportResult) -> None:
        """Create Group and Character rows (core fields, no slots yet)."""
        self._import_groups(result)
        self._import_characters(result)
        self._db.flush()

    def _import_groups(self, result: ImportResult) -> None:
        """Read ``groups/*.yaml`` and create Group rows."""
        grp_dir = self._input_dir / "groups"
        if not grp_dir.is_dir():
            return

        for path in sorted(grp_dir.glob("*.yaml")):
            raw = _load_yaml(path)
            if not raw:
                continue
            grp_yaml = GroupYaml.model_validate(raw)

            row = Group(
                name=grp_yaml.name,
                description=grp_yaml.description,
                tier=grp_yaml.tier,
                notes=grp_yaml.notes,
            )
            self._db.add(row)
            self._db.flush()

            self._resolver.register("group", grp_yaml.name, row.id)
            result.groups += 1

    def _import_characters(self, result: ImportResult) -> None:
        """Read ``characters/pcs/*.yaml``, ``npcs/*.yaml``, and ``entities/*.yaml``.

        PC characters get all meter/skill/magic_stat columns populated.
        NPC characters (and entities) get ``detail_level='simplified'``
        with all mechanical columns left as ``None``.
        """
        # PCs
        pc_dir = self._input_dir / "characters" / "pcs"
        if pc_dir.is_dir():
            for path in sorted(pc_dir.glob("*.yaml")):
                raw = _load_yaml(path)
                if not raw:
                    continue
                pc_yaml = PCCharacterYaml.model_validate(raw)
                self._create_pc_character(pc_yaml, result)

        # NPCs and entities — both are simplified characters.
        for sub in ("npcs", "entities"):
            npc_dir = self._input_dir / "characters" / sub
            if npc_dir.is_dir():
                for path in sorted(npc_dir.glob("*.yaml")):
                    raw = _load_yaml(path)
                    if not raw:
                        continue
                    npc_yaml = NPCCharacterYaml.model_validate(raw)
                    self._create_npc_character(npc_yaml, result)

    def _create_pc_character(
        self, pc_yaml: PCCharacterYaml, result: ImportResult
    ) -> None:
        """Create a full (PC) Character row and register it in the resolver.

        Args:
            pc_yaml: Validated PC character YAML.
            result: ImportResult to increment.
        """
        notes = _append_secrets(pc_yaml.notes, pc_yaml.secrets)
        m = pc_yaml.meters

        row = Character(
            name=pc_yaml.name,
            detail_level="full",
            description=pc_yaml.description,
            notes=notes,
            attributes=pc_yaml.attributes,
            stress=m.get("stress", 0),
            free_time=m.get("free_time", 0),
            plot=m.get("plot", 0),
            gnosis=m.get("gnosis", 0),
            skills=pc_yaml.skills,
            magic_stats=pc_yaml.magic_stats,
            last_session_time_now=0,
        )
        self._db.add(row)
        self._db.flush()

        self._resolver.register("character", pc_yaml.name, row.id)
        result.characters += 1

    def _create_npc_character(
        self, npc_yaml: NPCCharacterYaml, result: ImportResult
    ) -> None:
        """Create a simplified (NPC) Character row and register it.

        Args:
            npc_yaml: Validated NPC character YAML.
            result: ImportResult to increment.
        """
        notes = _append_secrets(npc_yaml.notes, npc_yaml.secrets)

        row = Character(
            name=npc_yaml.name,
            detail_level="simplified",
            description=npc_yaml.description,
            notes=notes,
            attributes=npc_yaml.attributes,
            # All meter/skill/magic columns remain None for simplified NPCs.
        )
        self._db.add(row)
        self._db.flush()

        self._resolver.register("character", npc_yaml.name, row.id)
        result.characters += 1

    # ------------------------------------------------------------------
    # Phase 3 — Slots + Magic effects
    # ------------------------------------------------------------------

    def _phase3_slots_and_magic_effects(self, result: ImportResult) -> None:
        """Create all slot rows and magic effects.

        Requires all characters, groups, and locations to already exist
        (Phase 2 must be complete).
        """
        self._import_character_slots(result)
        self._import_group_slots(result)
        self._import_location_slots(result)
        self._import_magic_effects(result)
        self._db.flush()

    def _import_character_slots(self, result: ImportResult) -> None:
        """Create trait and bond slots for all characters."""
        # PCs: core_traits, role_traits, bonds
        pc_dir = self._input_dir / "characters" / "pcs"
        if pc_dir.is_dir():
            for path in sorted(pc_dir.glob("*.yaml")):
                raw = _load_yaml(path)
                if not raw:
                    continue
                pc_yaml = PCCharacterYaml.model_validate(raw)
                owner_id = self._resolver.resolve("character", pc_yaml.name)

                # Core traits
                for trait in pc_yaml.core_traits:
                    template_id = self._resolver.resolve(
                        "trait_template", trait.template
                    )
                    self._db.add(Slot(
                        slot_type="core_trait",
                        owner_type="character",
                        owner_id=owner_id,
                        name=trait.template,
                        template_id=template_id,
                        charge=trait.charge,
                        is_active=trait.is_active,
                    ))
                    result.slots += 1

                # Role traits
                for trait in pc_yaml.role_traits:
                    template_id = self._resolver.resolve(
                        "trait_template", trait.template
                    )
                    self._db.add(Slot(
                        slot_type="role_trait",
                        owner_type="character",
                        owner_id=owner_id,
                        name=trait.template,
                        template_id=template_id,
                        charge=trait.charge,
                        is_active=trait.is_active,
                    ))
                    result.slots += 1

                # PC bonds
                for bond in pc_yaml.bonds:
                    target_type, target_id = self._resolver.resolve_target_ref(
                        bond.target
                    )
                    source_label = None
                    target_label = None
                    if bond.labels:
                        source_label = bond.labels.get("source")
                        target_label = bond.labels.get("target")
                    self._db.add(Slot(
                        slot_type="pc_bond",
                        owner_type="character",
                        owner_id=owner_id,
                        name=bond.name,
                        description=bond.description,
                        target_type=target_type,
                        target_id=target_id,
                        source_label=source_label,
                        target_label=target_label,
                        bidirectional=True,
                        charges=bond.charges,
                        degradations=bond.degradations,
                        is_trauma=bond.is_trauma,
                        is_active=bond.is_active,
                    ))
                    result.slots += 1

        # NPCs and entities: npc_bond slots
        for sub in ("npcs", "entities"):
            npc_dir = self._input_dir / "characters" / sub
            if npc_dir.is_dir():
                for path in sorted(npc_dir.glob("*.yaml")):
                    raw = _load_yaml(path)
                    if not raw:
                        continue
                    npc_yaml = NPCCharacterYaml.model_validate(raw)
                    owner_id = self._resolver.resolve("character", npc_yaml.name)

                    for bond in npc_yaml.bonds:
                        target_type, target_id = self._resolver.resolve_target_ref(
                            bond.target
                        )
                        source_label = None
                        target_label = None
                        if bond.labels:
                            source_label = bond.labels.get("source")
                            target_label = bond.labels.get("target")
                        self._db.add(Slot(
                            slot_type="npc_bond",
                            owner_type="character",
                            owner_id=owner_id,
                            name=bond.name,
                            description=bond.description,
                            target_type=target_type,
                            target_id=target_id,
                            source_label=source_label,
                            target_label=target_label,
                            bidirectional=bond.bidirectional,
                            is_active=bond.is_active,
                        ))
                        result.slots += 1

    def _import_group_slots(self, result: ImportResult) -> None:
        """Create trait, relation, and holding slots for all groups."""
        grp_dir = self._input_dir / "groups"
        if not grp_dir.is_dir():
            return

        for path in sorted(grp_dir.glob("*.yaml")):
            raw = _load_yaml(path)
            if not raw:
                continue
            grp_yaml = GroupYaml.model_validate(raw)
            owner_id = self._resolver.resolve("group", grp_yaml.name)

            # Group traits
            for trait in grp_yaml.traits:
                self._db.add(Slot(
                    slot_type="group_trait",
                    owner_type="group",
                    owner_id=owner_id,
                    name=trait.name,
                    description=trait.description,
                    is_active=trait.is_active,
                ))
                result.slots += 1

            # Group relations (group → group)
            for rel in grp_yaml.relations:
                target_id = self._resolver.resolve("group", rel.target)
                source_label = None
                target_label = None
                if rel.labels:
                    source_label = rel.labels.get("source")
                    target_label = rel.labels.get("target")
                self._db.add(Slot(
                    slot_type="group_relation",
                    owner_type="group",
                    owner_id=owner_id,
                    name=rel.name,
                    description=rel.description,
                    target_type="group",
                    target_id=target_id,
                    source_label=source_label,
                    target_label=target_label,
                    bidirectional=rel.bidirectional,
                    is_active=rel.is_active,
                ))
                result.slots += 1

            # Group holdings (group → location)
            for holding in grp_yaml.holdings:
                target_id = self._resolver.resolve("location", holding.target)
                self._db.add(Slot(
                    slot_type="group_holding",
                    owner_type="group",
                    owner_id=owner_id,
                    name=holding.name,
                    description=holding.description,
                    target_type="location",
                    target_id=target_id,
                    is_active=holding.is_active,
                ))
                result.slots += 1

    def _import_location_slots(self, result: ImportResult) -> None:
        """Create feature and bond slots for all locations."""
        loc_dir = self._input_dir / "locations"
        if not loc_dir.is_dir():
            return

        for path in sorted(loc_dir.rglob("_location.yaml")):
            raw = _load_yaml(path)
            if not raw:
                continue
            loc_yaml = LocationYaml.model_validate(raw)
            owner_id = self._resolver.resolve("location", loc_yaml.name)

            # Feature traits
            for feature in loc_yaml.features:
                self._db.add(Slot(
                    slot_type="feature_trait",
                    owner_type="location",
                    owner_id=owner_id,
                    name=feature.name,
                    description=feature.description,
                    is_active=feature.is_active,
                ))
                result.slots += 1

            # Location bonds
            for bond in loc_yaml.bonds:
                target_type, target_id = self._resolver.resolve_target_ref(
                    bond.target
                )
                source_label = None
                target_label = None
                if bond.labels:
                    source_label = bond.labels.get("source")
                    target_label = bond.labels.get("target")
                self._db.add(Slot(
                    slot_type="location_bond",
                    owner_type="location",
                    owner_id=owner_id,
                    name=bond.name,
                    description=bond.description,
                    target_type=target_type,
                    target_id=target_id,
                    source_label=source_label,
                    target_label=target_label,
                    is_active=bond.is_active,
                ))
                result.slots += 1

    def _import_magic_effects(self, result: ImportResult) -> None:
        """Create MagicEffect rows for all PCs."""
        pc_dir = self._input_dir / "characters" / "pcs"
        if not pc_dir.is_dir():
            return

        for path in sorted(pc_dir.glob("*.yaml")):
            raw = _load_yaml(path)
            if not raw:
                continue
            pc_yaml = PCCharacterYaml.model_validate(raw)
            character_id = self._resolver.resolve("character", pc_yaml.name)

            for effect in pc_yaml.magic_effects:
                charges_current: int | None = None
                charges_max: int | None = None
                if effect.effect_type == "charged" and effect.charges:
                    charges_current = effect.charges.get("current")
                    charges_max = effect.charges.get("max")

                self._db.add(MagicEffect(
                    character_id=character_id,
                    name=effect.name,
                    description=effect.description,
                    effect_type=effect.effect_type,
                    power_level=effect.power_level,
                    charges_current=charges_current,
                    charges_max=charges_max,
                    is_active=effect.is_active,
                ))
                result.magic_effects += 1

    # ------------------------------------------------------------------
    # Phase 4 — Clocks
    # ------------------------------------------------------------------

    def _phase4_clocks(self, result: ImportResult) -> None:
        """Create Clock rows with optional game object associations."""
        clk_dir = self._input_dir / "clocks"
        if not clk_dir.is_dir():
            return

        for path in sorted(clk_dir.glob("*.yaml")):
            raw = _load_yaml(path)
            if not raw:
                continue
            clk_yaml = ClockYaml.model_validate(raw)

            associated_type: str | None = None
            associated_id: str | None = None
            if clk_yaml.associated_with is not None:
                associated_type, associated_id = self._resolver.resolve_target_ref(
                    clk_yaml.associated_with
                )

            row = Clock(
                name=clk_yaml.name,
                segments=clk_yaml.segments,
                progress=clk_yaml.progress,
                associated_type=associated_type,
                associated_id=associated_id,
                notes=clk_yaml.notes,
            )
            self._db.add(row)
            result.clocks += 1

        self._db.flush()

    # ------------------------------------------------------------------
    # Phase 5 — Users
    # ------------------------------------------------------------------

    def _phase5_users(self, result: ImportResult) -> None:
        """Create User rows with generated login codes."""
        usr_dir = self._input_dir / "users"
        if not usr_dir.is_dir():
            return

        for path in sorted(usr_dir.glob("*.yaml")):
            raw = _load_yaml(path)
            if not raw:
                continue
            usr_yaml = UserYaml.model_validate(raw)

            character_id: str | None = None
            if usr_yaml.character is not None:
                character_id = self._resolver.resolve("character", usr_yaml.character)

            row = User(
                display_name=usr_yaml.display_name,
                role=usr_yaml.role,
                login_code=_secrets.token_urlsafe(32),
                is_active=True,
                character_id=character_id,
            )
            self._db.add(row)
            self._db.flush()

            self._resolver.register("user", usr_yaml.display_name, row.id)
            result.users += 1

    # ------------------------------------------------------------------
    # Phase 6 — Sessions + Stories
    # ------------------------------------------------------------------

    def _phase6_sessions_and_stories(self, result: ImportResult) -> None:
        """Create Session and Story rows (with all associations)."""
        self._import_sessions(result)
        self._import_stories(result)
        self._db.flush()

    def _import_sessions(self, result: ImportResult) -> None:
        """Read ``sessions/*.yaml`` and create Session + SessionParticipant rows."""
        ses_dir = self._input_dir / "sessions"
        if not ses_dir.is_dir():
            return

        # Sort by session number for deterministic ordering.
        session_files = sorted(ses_dir.glob("*.yaml"))

        for path in session_files:
            raw = _load_yaml(path)
            if not raw:
                continue
            ses_yaml = SessionYaml.model_validate(raw)

            # Parse date string to a date object if present.
            session_date: datetime.date | None = None
            if ses_yaml.date:
                try:
                    session_date = datetime.date.fromisoformat(ses_yaml.date)
                except ValueError:
                    session_date = None

            row = SessionModel(
                status=ses_yaml.status,
                time_now=ses_yaml.time_now,
                date=session_date,
                summary=ses_yaml.summary,
                notes=ses_yaml.notes,
            )
            self._db.add(row)
            self._db.flush()

            # Register session by number for story-entry cross-references.
            self._session_by_number[ses_yaml.number] = row.id
            self._resolver.register("session", str(ses_yaml.number), row.id)
            result.sessions += 1

            # Create participant rows.
            for participant in ses_yaml.participants:
                char_id = self._resolver.resolve("character", participant.character)
                self._db.add(SessionParticipant(
                    session_id=row.id,
                    character_id=char_id,
                    additional_contribution=participant.additional_contribution,
                ))
                result.session_participants += 1

            self._db.flush()

    def _import_stories(self, result: ImportResult) -> None:
        """Read ``stories/*.yaml`` and create Story, StoryOwner, StoryEntry rows."""
        sto_dir = self._input_dir / "stories"
        if not sto_dir.is_dir():
            return

        for path in sorted(sto_dir.glob("*.yaml")):
            raw = _load_yaml(path)
            if not raw:
                continue
            sto_yaml = StoryYaml.model_validate(raw)
            self._create_story(sto_yaml, parent_id=None, result=result)

    def _create_story(
        self,
        sto_yaml: StoryYaml,
        parent_id: str | None,
        result: ImportResult,
    ) -> str:
        """Create a Story row and all its owners, entries, and children.

        Args:
            sto_yaml: Validated story YAML (may contain nested children).
            parent_id: ULID of the parent Story, or ``None`` for root stories.
            result: ImportResult to increment.

        Returns:
            The ULID of the newly created Story row.
        """
        row = Story(
            name=sto_yaml.name,
            summary=sto_yaml.summary,
            status=sto_yaml.status,
            parent_id=parent_id,
            tags=sto_yaml.tags if sto_yaml.tags else None,
        )
        self._db.add(row)
        self._db.flush()
        result.stories += 1

        # Story owners
        for owner in sto_yaml.owners:
            owner_id = self._resolver.resolve(owner.type, owner.name)
            self._db.add(StoryOwner(
                story_id=row.id,
                owner_type=owner.type,
                owner_id=owner_id,
            ))
            result.story_owners += 1

        # Story entries
        for entry in sto_yaml.entries:
            author_id = self._resolver.resolve("user", entry.author)

            character_id: str | None = None
            if entry.character is not None:
                character_id = self._resolver.resolve("character", entry.character)

            session_id: str | None = None
            if entry.session is not None:
                session_id = self._session_by_number.get(entry.session)

            self._db.add(StoryEntry(
                story_id=row.id,
                text=entry.text,
                author_id=author_id,
                character_id=character_id,
                session_id=session_id,
            ))
            result.story_entries += 1

        self._db.flush()

        # Recurse into children
        for child_yaml in sto_yaml.children:
            self._create_story(child_yaml, parent_id=row.id, result=result)

        return row.id
