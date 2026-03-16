"""ULID cursor-based pagination utility for SQLAlchemy queries.

All list endpoints in Wizards Engine use ULID-ordered, cursor-based
pagination.  Since ULIDs are lexicographically sortable by creation
time, ordering by ``id`` DESC gives newest-first results and the cursor
is just the ``id`` string of the last seen item.
"""

from typing import Any, TypeVar

from sqlalchemy import desc
from sqlalchemy.orm import Session

from wizards_engine.schemas.common import PaginatedResponse

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 100

ModelT = TypeVar("ModelT")


def paginate(
    db: Session,
    query,
    *,
    model,
    after: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> PaginatedResponse[Any]:
    """Apply ULID cursor pagination to a SQLAlchemy query and return results.

    The query must **not** already have an ``ORDER BY`` clause applied —
    this function adds ``ORDER BY id DESC`` itself.

    Parameters
    ----------
    db:
        Active SQLAlchemy :class:`~sqlalchemy.orm.Session`.
    query:
        A SQLAlchemy ``Select`` statement (or legacy ``Query``) targeting
        rows that have an ``id`` column populated with ULID strings.
    model:
        The ORM model class being queried.  Used to access the ``id``
        column for filtering and ordering.
    after:
        Optional ULID cursor.  When provided, only rows whose ``id`` is
        *less than* this value are returned (i.e. older rows), enabling
        forward pagination through newest-first results.
    limit:
        Maximum number of items to return.  Clamped to
        :data:`_MAX_LIMIT`.  Defaults to :data:`_DEFAULT_LIMIT`.

    Returns
    -------
    PaginatedResponse
        A :class:`~wizards_engine.schemas.common.PaginatedResponse` with
        ``items``, ``next_cursor``, and ``has_more`` populated.
    """
    limit = min(limit, _MAX_LIMIT)

    # Build the paginated query: filter by cursor, order newest-first, fetch
    # one extra row so we can detect whether more pages exist.
    q = query.order_by(desc(model.id))

    if after is not None:
        q = q.filter(model.id < after)

    rows = db.scalars(q.limit(limit + 1)).all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
