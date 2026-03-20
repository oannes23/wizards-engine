"""Two-pass campaign directory validation.

Validates a campaign YAML directory before importing it into the database.

**Pass 1 — Schema validation**:
    Walk the directory structure, load each YAML file, and validate it
    against the appropriate Pydantic model.  All errors are collected
    (fail-slow, not fail-fast) so the user gets a complete error report.

**Pass 2 — Reference validation**:
    Build a registry of all entity names from the schema-validated data
    and then check every cross-reference.  Only runs if Pass 1 has zero
    errors.

Returns a list of :class:`ValidationError` dataclass instances, each with
``file_path``, ``field``, and ``error_message`` attributes.

Usage::

    from pathlib import Path
    from wizards_engine.campaign.validators import validate_campaign

    errors = validate_campaign(Path("campaign-data/"))
    if errors:
        for e in errors:
            print(f"{e.file_path}:{e.field}: {e.error_message}")
    else:
        print("Campaign is valid.")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from wizards_engine.campaign.exceptions import (
    DuplicateNameError,
    UnresolvedReferenceError,
)
from wizards_engine.campaign.ordering import topological_sort_locations
from wizards_engine.campaign.resolver import NameResolver
from wizards_engine.campaign.schemas import (
    CampaignMeta,
    ClockYaml,
    GroupYaml,
    LocationYaml,
    NPCCharacterYaml,
    PCCharacterYaml,
    SessionYaml,
    StoryYaml,
    TargetRef,
    TraitTemplateYaml,
    UserYaml,
)

__all__ = ["ValidationFinding", "validate_campaign"]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ValidationFinding:
    """A single validation error found during two-pass validation.

    Attributes
    ----------
    file_path:
        Path to the YAML file that contains the error, relative to the
        campaign root directory.
    field:
        Dot-path to the erroneous field (e.g. ``"bonds[0].target.name"``),
        or ``""`` if the error applies to the whole file.
    error_message:
        Human-readable description of the problem.
    """

    file_path: str
    field: str
    error_message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """Load a YAML file and return its contents as a dict.

    Returns ``None`` if the file is empty.  Raises ``yaml.YAMLError`` if
    the file is not valid YAML.
    """
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _rel(base: Path, path: Path) -> str:
    """Return ``path`` relative to ``base`` as a forward-slash string."""
    return str(path.relative_to(base))


def _pydantic_errors(exc: PydanticValidationError, file_path: str) -> list[ValidationFinding]:
    """Convert a Pydantic ValidationError into ValidationFinding instances."""
    errors = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        errors.append(
            ValidationFinding(
                file_path=file_path,
                field=loc,
                error_message=err["msg"],
            )
        )
    return errors



# ---------------------------------------------------------------------------
# Pass 1 — Schema validation
# ---------------------------------------------------------------------------


def _pass1_schema(
    campaign_dir: Path,
    errors: list[ValidationFinding],
) -> dict[str, Any]:
    """Walk the campaign directory and validate every YAML file.

    Returns a dict of collected (validated) data keyed by entity type,
    for use in Pass 2.  The dict is populated even when errors are found
    so that Pass 2 can be as complete as possible — though Pass 2 is only
    called when the error list is empty.

    Structure of the returned dict::

        {
            "meta": CampaignMeta | None,
            "trait_templates": list[dict],   # {"name": ..., "yaml": TraitTemplateYaml}
            "locations": list[dict],         # {"name": ..., "yaml": LocationYaml, "path": str}
            "characters_pc": list[dict],     # {"name": ..., "yaml": PCCharacterYaml, "path": str}
            "characters_npc": list[dict],    # {"name": ..., "yaml": NPCCharacterYaml, "path": str}
            "groups": list[dict],
            "clocks": list[dict],
            "sessions": list[dict],
            "stories": list[dict],
            "users": list[dict],
        }
    """
    data: dict[str, Any] = {
        "meta": None,
        "trait_templates": [],
        "locations": [],
        "characters_pc": [],
        "characters_npc": [],
        "groups": [],
        "clocks": [],
        "sessions": [],
        "stories": [],
        "users": [],
    }

    # --- meta.yaml ---
    meta_path = campaign_dir / "meta.yaml"
    if meta_path.exists():
        rel = _rel(campaign_dir, meta_path)
        try:
            raw = _load_yaml(meta_path)
            if raw:
                data["meta"] = CampaignMeta.model_validate(raw)
        except yaml.YAMLError as exc:
            errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
        except PydanticValidationError as exc:
            errors.extend(_pydantic_errors(exc, rel))

    # --- trait-templates/*.yaml ---
    tt_dir = campaign_dir / "trait-templates"
    if tt_dir.is_dir():
        for path in sorted(tt_dir.glob("*.yaml")):
            rel = _rel(campaign_dir, path)
            try:
                raw = _load_yaml(path)
                if raw:
                    tt = TraitTemplateYaml.model_validate(raw)
                    data["trait_templates"].append({"name": tt.name, "yaml": tt, "path": rel})
            except yaml.YAMLError as exc:
                errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
            except PydanticValidationError as exc:
                errors.extend(_pydantic_errors(exc, rel))

    # --- locations/**/_location.yaml ---
    loc_dir = campaign_dir / "locations"
    if loc_dir.is_dir():
        for path in sorted(loc_dir.rglob("_location.yaml")):
            rel = _rel(campaign_dir, path)
            try:
                raw = _load_yaml(path)
                if raw:
                    loc = LocationYaml.model_validate(raw)
                    data["locations"].append({"name": loc.name, "yaml": loc, "path": rel})
            except yaml.YAMLError as exc:
                errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
            except PydanticValidationError as exc:
                errors.extend(_pydantic_errors(exc, rel))

    # --- characters/pcs/*.yaml ---
    pc_dir = campaign_dir / "characters" / "pcs"
    if pc_dir.is_dir():
        for path in sorted(pc_dir.glob("*.yaml")):
            rel = _rel(campaign_dir, path)
            try:
                raw = _load_yaml(path)
                if raw:
                    pc = PCCharacterYaml.model_validate(raw)
                    data["characters_pc"].append({"name": pc.name, "yaml": pc, "path": rel})
            except yaml.YAMLError as exc:
                errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
            except PydanticValidationError as exc:
                errors.extend(_pydantic_errors(exc, rel))

    # --- characters/npcs/*.yaml and characters/entities/*.yaml ---
    for sub in ("npcs", "entities"):
        npc_dir = campaign_dir / "characters" / sub
        if npc_dir.is_dir():
            for path in sorted(npc_dir.glob("*.yaml")):
                rel = _rel(campaign_dir, path)
                try:
                    raw = _load_yaml(path)
                    if raw:
                        npc = NPCCharacterYaml.model_validate(raw)
                        data["characters_npc"].append({"name": npc.name, "yaml": npc, "path": rel})
                except yaml.YAMLError as exc:
                    errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
                except PydanticValidationError as exc:
                    errors.extend(_pydantic_errors(exc, rel))

    # --- groups/*.yaml ---
    grp_dir = campaign_dir / "groups"
    if grp_dir.is_dir():
        for path in sorted(grp_dir.glob("*.yaml")):
            rel = _rel(campaign_dir, path)
            try:
                raw = _load_yaml(path)
                if raw:
                    grp = GroupYaml.model_validate(raw)
                    data["groups"].append({"name": grp.name, "yaml": grp, "path": rel})
            except yaml.YAMLError as exc:
                errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
            except PydanticValidationError as exc:
                errors.extend(_pydantic_errors(exc, rel))

    # --- clocks/*.yaml ---
    clk_dir = campaign_dir / "clocks"
    if clk_dir.is_dir():
        for path in sorted(clk_dir.glob("*.yaml")):
            rel = _rel(campaign_dir, path)
            try:
                raw = _load_yaml(path)
                if raw:
                    clk = ClockYaml.model_validate(raw)
                    data["clocks"].append({"name": clk.name, "yaml": clk, "path": rel})
            except yaml.YAMLError as exc:
                errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
            except PydanticValidationError as exc:
                errors.extend(_pydantic_errors(exc, rel))

    # --- sessions/*.yaml ---
    ses_dir = campaign_dir / "sessions"
    if ses_dir.is_dir():
        for path in sorted(ses_dir.glob("*.yaml")):
            rel = _rel(campaign_dir, path)
            try:
                raw = _load_yaml(path)
                if raw:
                    ses = SessionYaml.model_validate(raw)
                    data["sessions"].append({"number": ses.number, "yaml": ses, "path": rel})
            except yaml.YAMLError as exc:
                errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
            except PydanticValidationError as exc:
                errors.extend(_pydantic_errors(exc, rel))

    # --- stories/*.yaml ---
    sto_dir = campaign_dir / "stories"
    if sto_dir.is_dir():
        for path in sorted(sto_dir.glob("*.yaml")):
            rel = _rel(campaign_dir, path)
            try:
                raw = _load_yaml(path)
                if raw:
                    sto = StoryYaml.model_validate(raw)
                    data["stories"].append({"name": sto.name, "yaml": sto, "path": rel})
            except yaml.YAMLError as exc:
                errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
            except PydanticValidationError as exc:
                errors.extend(_pydantic_errors(exc, rel))

    # --- users/*.yaml ---
    usr_dir = campaign_dir / "users"
    if usr_dir.is_dir():
        for path in sorted(usr_dir.glob("*.yaml")):
            rel = _rel(campaign_dir, path)
            try:
                raw = _load_yaml(path)
                if raw:
                    usr = UserYaml.model_validate(raw)
                    data["users"].append({"display_name": usr.display_name, "yaml": usr, "path": rel})
            except yaml.YAMLError as exc:
                errors.append(ValidationFinding(rel, "", f"YAML parse error: {exc}"))
            except PydanticValidationError as exc:
                errors.extend(_pydantic_errors(exc, rel))

    return data


# ---------------------------------------------------------------------------
# Pass 2 — Reference validation
# ---------------------------------------------------------------------------


def _build_resolver(data: dict[str, Any]) -> NameResolver:
    """Build a NameResolver populated with all names from the schema-validated data.

    Uses placeholder ULIDs (the name itself) since we only need to check
    that references resolve — we don't need actual ULIDs for validation.
    """
    resolver = NameResolver()

    for item in data["trait_templates"]:
        if not resolver.is_registered("trait_template", item["name"]):
            resolver.register("trait_template", item["name"], item["name"])

    for item in data["locations"]:
        if not resolver.is_registered("location", item["name"]):
            resolver.register("location", item["name"], item["name"])

    for item in data["characters_pc"]:
        if not resolver.is_registered("character", item["name"]):
            resolver.register("character", item["name"], item["name"])

    for item in data["characters_npc"]:
        # Silently skip duplicates — duplicate detection is handled separately
        # in _check_duplicates, which runs before reference checks.
        if not resolver.is_registered("character", item["name"]):
            resolver.register("character", item["name"], item["name"])

    for item in data["groups"]:
        if not resolver.is_registered("group", item["name"]):
            resolver.register("group", item["name"], item["name"])

    for item in data["clocks"]:
        if not resolver.is_registered("clock", item["name"]):
            resolver.register("clock", item["name"], item["name"])

    for item in data["sessions"]:
        if not resolver.is_registered("session", str(item["number"])):
            resolver.register("session", str(item["number"]), str(item["number"]))

    for item in data["stories"]:
        if not resolver.is_registered("story", item["name"]):
            resolver.register("story", item["name"], item["name"])

    for item in data["users"]:
        if not resolver.is_registered("user", item["display_name"]):
            resolver.register("user", item["display_name"], item["display_name"])

    return resolver


def _check_target_ref(
    ref: TargetRef,
    resolver: NameResolver,
    file_path: str,
    field: str,
    errors: list[ValidationFinding],
) -> None:
    """Check that a TargetRef resolves, appending to errors if not."""
    try:
        resolver.resolve(ref.type, ref.name)
    except UnresolvedReferenceError:
        errors.append(
            ValidationFinding(
                file_path=file_path,
                field=field,
                error_message=(
                    f"Reference to {ref.type} {ref.name!r} cannot be resolved: "
                    f"no {ref.type} with that name exists."
                ),
            )
        )


def _pass2_references(
    data: dict[str, Any],
    errors: list[ValidationFinding],
) -> None:
    """Check all cross-references using a fully populated NameResolver."""
    # --- Duplicate name checks must run first ---
    # _build_resolver silently skips duplicates; _check_duplicates reports them.
    _check_duplicates(data, errors)

    # --- Circular location parent detection ---
    # topological_sort_locations raises ValueError on cycles.  Convert to
    # structured errors so the caller gets a consistent result type.
    if data["locations"]:
        loc_dicts = [
            {"name": item["name"], "parent": item["yaml"].parent}
            for item in data["locations"]
        ]
        try:
            topological_sort_locations(loc_dicts)
        except ValueError as exc:
            errors.append(
                ValidationFinding(
                    file_path="locations/",
                    field="parent",
                    error_message=str(exc),
                )
            )

    resolver = _build_resolver(data)

    # --- Trait template references (PC traits) ---
    for item in data["characters_pc"]:
        pc: PCCharacterYaml = item["yaml"]
        file_path: str = item["path"]

        for i, t in enumerate(pc.core_traits):
            try:
                resolver.resolve("trait_template", t.template)
            except UnresolvedReferenceError:
                errors.append(ValidationFinding(
                    file_path=file_path,
                    field=f"core_traits[{i}].template",
                    error_message=f"Trait template {t.template!r} does not exist.",
                ))

        for i, t in enumerate(pc.role_traits):
            try:
                resolver.resolve("trait_template", t.template)
            except UnresolvedReferenceError:
                errors.append(ValidationFinding(
                    file_path=file_path,
                    field=f"role_traits[{i}].template",
                    error_message=f"Trait template {t.template!r} does not exist.",
                ))

        # Bond targets
        for i, bond in enumerate(pc.bonds):
            _check_target_ref(
                bond.target,
                resolver,
                file_path,
                f"bonds[{i}].target",
                errors,
            )

    # --- NPC bond targets ---
    for item in data["characters_npc"]:
        npc: NPCCharacterYaml = item["yaml"]
        file_path = item["path"]

        for i, bond in enumerate(npc.bonds):
            _check_target_ref(
                bond.target,
                resolver,
                file_path,
                f"bonds[{i}].target",
                errors,
            )

    # --- Group relations (target group) and holdings (target location) ---
    for item in data["groups"]:
        grp: GroupYaml = item["yaml"]
        file_path = item["path"]

        for i, rel in enumerate(grp.relations):
            try:
                resolver.resolve("group", rel.target)
            except UnresolvedReferenceError:
                errors.append(ValidationFinding(
                    file_path=file_path,
                    field=f"relations[{i}].target",
                    error_message=f"Group {rel.target!r} does not exist.",
                ))

        for i, holding in enumerate(grp.holdings):
            try:
                resolver.resolve("location", holding.target)
            except UnresolvedReferenceError:
                errors.append(ValidationFinding(
                    file_path=file_path,
                    field=f"holdings[{i}].target",
                    error_message=f"Location {holding.target!r} does not exist.",
                ))

    # --- Location bonds and parent references ---
    for item in data["locations"]:
        loc: LocationYaml = item["yaml"]
        file_path = item["path"]

        if loc.parent is not None:
            try:
                resolver.resolve("location", loc.parent)
            except UnresolvedReferenceError:
                errors.append(ValidationFinding(
                    file_path=file_path,
                    field="parent",
                    error_message=f"Parent location {loc.parent!r} does not exist.",
                ))

        for i, bond in enumerate(loc.bonds):
            _check_target_ref(
                bond.target,
                resolver,
                file_path,
                f"bonds[{i}].target",
                errors,
            )

    # --- Clock associated_with ---
    for item in data["clocks"]:
        clk: ClockYaml = item["yaml"]
        file_path = item["path"]

        if clk.associated_with is not None:
            _check_target_ref(
                clk.associated_with,
                resolver,
                file_path,
                "associated_with",
                errors,
            )

    # --- User → character links ---
    for item in data["users"]:
        usr: UserYaml = item["yaml"]
        file_path = item["path"]

        if usr.character is not None:
            try:
                resolver.resolve("character", usr.character)
            except UnresolvedReferenceError:
                errors.append(ValidationFinding(
                    file_path=file_path,
                    field="character",
                    error_message=f"Character {usr.character!r} does not exist.",
                ))

    # --- Session participants ---
    for item in data["sessions"]:
        ses: SessionYaml = item["yaml"]
        file_path = item["path"]

        for i, part in enumerate(ses.participants):
            try:
                resolver.resolve("character", part.character)
            except UnresolvedReferenceError:
                errors.append(ValidationFinding(
                    file_path=file_path,
                    field=f"participants[{i}].character",
                    error_message=f"Character {part.character!r} does not exist.",
                ))

    # Build a set of valid session numbers for story entry checks.
    valid_session_numbers: set[int] = {
        item["number"] for item in data["sessions"]
    }

    # Build a set of valid user display_names for story entry author checks.
    valid_user_display_names: set[str] = {
        item["display_name"] for item in data["users"]
    }

    # --- Story owners, entry authors, entry character refs, entry session refs ---
    for item in data["stories"]:
        _check_story(item, resolver, valid_session_numbers, valid_user_display_names, errors)


def _check_story(
    item: dict[str, Any],
    resolver: NameResolver,
    valid_session_numbers: set[int],
    valid_user_display_names: set[str],
    errors: list[ValidationFinding],
) -> None:
    """Validate references within a single story (and its children recursively)."""
    sto: StoryYaml = item["yaml"]
    file_path: str = item["path"]

    # Owners
    for i, owner in enumerate(sto.owners):
        try:
            resolver.resolve(owner.type, owner.name)
        except UnresolvedReferenceError:
            errors.append(ValidationFinding(
                file_path=file_path,
                field=f"owners[{i}].name",
                error_message=(
                    f"{owner.type.capitalize()} {owner.name!r} does not exist."
                ),
            ))

    # Entries
    for i, entry in enumerate(sto.entries):
        # Author (display_name of a user)
        if entry.author not in valid_user_display_names:
            errors.append(ValidationFinding(
                file_path=file_path,
                field=f"entries[{i}].author",
                error_message=f"User display_name {entry.author!r} does not exist.",
            ))

        # Character link (optional)
        if entry.character is not None:
            try:
                resolver.resolve("character", entry.character)
            except UnresolvedReferenceError:
                errors.append(ValidationFinding(
                    file_path=file_path,
                    field=f"entries[{i}].character",
                    error_message=f"Character {entry.character!r} does not exist.",
                ))

        # Session link (optional, by number)
        if entry.session is not None:
            if entry.session not in valid_session_numbers:
                errors.append(ValidationFinding(
                    file_path=file_path,
                    field=f"entries[{i}].session",
                    error_message=(
                        f"Session number {entry.session} does not exist."
                    ),
                ))

    # Recurse into children
    for child in sto.children:
        _check_story(
            {"yaml": child, "path": file_path},
            resolver,
            valid_session_numbers,
            valid_user_display_names,
            errors,
        )


def _check_duplicates(
    data: dict[str, Any],
    errors: list[ValidationFinding],
) -> None:
    """Check for duplicate names within each entity type."""

    def _find_duplicates(
        items: list[dict],
        name_key: str,
        entity_label: str,
    ) -> None:
        seen: dict[str, str] = {}  # name → file_path
        for item in items:
            name = item[name_key]
            if name in seen:
                errors.append(ValidationFinding(
                    file_path=item["path"],
                    field=name_key,
                    error_message=(
                        f"Duplicate {entity_label} name {name!r}. "
                        f"First seen in {seen[name]!r}."
                    ),
                ))
            else:
                seen[name] = item["path"]

    _find_duplicates(data["trait_templates"], "name", "trait_template")
    _find_duplicates(data["locations"], "name", "location")
    _find_duplicates(data["groups"], "name", "group")
    _find_duplicates(data["clocks"], "name", "clock")
    _find_duplicates(data["stories"], "name", "story")
    _find_duplicates(data["users"], "display_name", "user")
    _find_duplicates(data["sessions"], "number", "session")

    # Characters across all subdirs share the same namespace.
    all_characters = data["characters_pc"] + data["characters_npc"]
    _find_duplicates(all_characters, "name", "character")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_campaign(campaign_dir: Path) -> list[ValidationFinding]:
    """Validate a campaign directory in two passes.

    **Pass 1** loads and schema-validates every YAML file in the campaign
    directory tree.  All schema errors are collected before Pass 2 begins.

    **Pass 2** checks every cross-reference between entities (bond targets,
    trait template refs, user→character links, session participants, story
    owners/authors, clock associations, location parents).  Pass 2 only
    runs if Pass 1 produced zero errors.

    Parameters
    ----------
    campaign_dir:
        Path to the root campaign directory (the directory that contains
        ``meta.yaml``, ``characters/``, ``groups/``, etc.).

    Returns
    -------
    list[ValidationFinding]
        A (possibly empty) list of structured validation errors.  An
        empty list means the campaign is valid and safe to import.
    """
    errors: list[ValidationFinding] = []

    data = _pass1_schema(campaign_dir, errors)

    if not errors:
        _pass2_references(data, errors)

    return errors
