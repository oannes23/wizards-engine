"""Campaign import/export tooling for wizards-engine.

Provides YAML-based campaign data serialization (k8s gitops style).
All data maps to existing tables — no schema changes required.

Submodules:
- ``schemas``: Pydantic models for all YAML entity types.
- ``ordering``: Import phase constants and location topological sort.
"""
