"""Name-to-ULID registry used during campaign import.

The ``NameResolver`` maps ``(entity_type, name)`` pairs to ULIDs as
entities are created during the 6-phase import sequence.  Cross-references
between entities are stored as human-readable name strings in YAML; the
resolver converts them to database IDs on demand.

Typical usage::

    resolver = NameResolver()

    # Phase 1 — register locations as they are created.
    resolver.register("location", "Las Vegas", "01ABCDEF...")

    # Phase 3 — resolve a bond target.
    target_id = resolver.resolve("location", "Las Vegas")

    # Polymorphic ref from a TargetRef model.
    target_type, target_id = resolver.resolve_target_ref(bond.target)
"""

from __future__ import annotations

from wizards_engine.campaign.exceptions import DuplicateNameError, UnresolvedReferenceError
from wizards_engine.campaign.schemas import TargetRef

__all__ = ["NameResolver"]


class NameResolver:
    """Registry that maps ``(entity_type, name)`` → ULID.

    Used during import to resolve name-based cross-references to DB IDs.
    The registry is populated incrementally as each import phase creates
    entities in the database.

    Entity types are arbitrary strings — typically the singular form of
    the YAML entity type (e.g. ``"character"``, ``"group"``,
    ``"location"``, ``"trait_template"``, ``"clock"``, ``"session"``,
    ``"story"``, ``"user"``).

    Name matching is case-sensitive and exact.  Trailing/leading
    whitespace is stripped on both ``register`` and ``resolve`` calls.
    """

    def __init__(self) -> None:
        # Nested dict: entity_type → {name → ulid}
        self._registry: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, entity_type: str, name: str, ulid: str) -> None:
        """Register a name→ULID mapping.

        Parameters
        ----------
        entity_type:
            The entity type namespace (e.g. ``"character"``).
        name:
            Human-readable name of the entity.
        ulid:
            The ULID assigned to this entity in the database.

        Raises
        ------
        DuplicateNameError
            If ``name`` has already been registered for ``entity_type``.
        """
        name = name.strip()
        entity_type = entity_type.strip()

        if entity_type not in self._registry:
            self._registry[entity_type] = {}

        if name in self._registry[entity_type]:
            raise DuplicateNameError(entity_type, name)

        self._registry[entity_type][name] = ulid

    def resolve(self, entity_type: str, name: str) -> str:
        """Resolve a name to its ULID.

        Parameters
        ----------
        entity_type:
            The entity type namespace (e.g. ``"character"``).
        name:
            Human-readable name of the entity.

        Returns
        -------
        str
            The ULID registered under ``(entity_type, name)``.

        Raises
        ------
        UnresolvedReferenceError
            If no entry exists for the given ``(entity_type, name)`` pair.
        """
        name = name.strip()
        entity_type = entity_type.strip()

        type_registry = self._registry.get(entity_type, {})
        if name not in type_registry:
            raise UnresolvedReferenceError(entity_type, name)
        return type_registry[name]

    def resolve_target_ref(self, target_ref: TargetRef) -> tuple[str, str]:
        """Resolve a polymorphic ``TargetRef`` to ``(target_type, target_id)``.

        ``TargetRef`` uses ``type`` values of ``"character"``, ``"group"``,
        or ``"location"``.  These map directly to the same entity-type
        names used in the registry when entities are created.

        Parameters
        ----------
        target_ref:
            A ``TargetRef`` from the campaign YAML schemas.

        Returns
        -------
        tuple[str, str]
            A ``(target_type, target_id)`` pair where ``target_type`` is
            the same string as ``target_ref.type`` and ``target_id`` is
            the resolved ULID.

        Raises
        ------
        UnresolvedReferenceError
            If the referenced entity has not been registered.
        """
        target_id = self.resolve(target_ref.type, target_ref.name)
        return target_ref.type, target_id

    # ------------------------------------------------------------------
    # Introspection helpers (used in tests and diagnostics)
    # ------------------------------------------------------------------

    def registered_names(self, entity_type: str) -> list[str]:
        """Return all registered names for ``entity_type``, sorted."""
        return sorted(self._registry.get(entity_type, {}).keys())

    def is_registered(self, entity_type: str, name: str) -> bool:
        """Return ``True`` if ``(entity_type, name)`` is in the registry."""
        name = name.strip()
        return name in self._registry.get(entity_type, {})
