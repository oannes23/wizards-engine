"""Custom path parameter types with validation."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator


def _validate_ulid(value: str) -> str:
    """Validate that *value* is a syntactically valid ULID (26 Crockford Base32 chars).

    Args:
        value: The raw string received from the path parameter.

    Returns:
        The original value, unchanged, if it matches the ULID pattern.

    Raises:
        ValueError: If *value* does not match the 26-character Crockford Base32 pattern.
    """
    if not re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", value, re.IGNORECASE):
        raise ValueError(f"Invalid ULID: '{value}'")
    return value


UlidStr = Annotated[str, AfterValidator(_validate_ulid)]
