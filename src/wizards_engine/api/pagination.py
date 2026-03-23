"""ULID cursor-based pagination utility for SQLAlchemy queries.

All list endpoints in Wizards Engine use ULID-ordered, cursor-based
pagination.  Since ULIDs are lexicographically sortable by creation
time, ordering by ``id`` DESC gives newest-first results and the cursor
is just the ``id`` string of the last seen item.

Two pagination modes are supported:

1. **Default ULID cursor** — ``ORDER BY id DESC``, cursor is the ``id``
   of the last returned row.  Used when ``sort_col`` is ``None``.

2. **Keyset cursor** — ``ORDER BY <sort_col> <sort_dir>, id DESC``,
   cursor encodes both the sort-column value and the ``id`` of the last
   returned row.  Used when ``sort_col`` is provided.  The cursor is
   the ULID ``id`` of the last row; the caller re-supplies ``sort_col``
   and ``sort_dir`` on subsequent requests to maintain consistent ordering.
"""

from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import asc, desc
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
    sort_col=None,
    sort_dir: str = "desc",
) -> PaginatedResponse[Any]:
    """Apply cursor pagination to a SQLAlchemy query and return results.

    The query must **not** already have an ``ORDER BY`` clause applied —
    this function adds the appropriate ``ORDER BY`` itself.

    Two modes are supported depending on whether ``sort_col`` is provided:

    **Default ULID cursor** (``sort_col=None``):
        Orders by ``id DESC`` (newest-first ULID order).  The cursor
        (``after``) is a ULID string; only rows with ``id < after`` are
        returned.

    **Keyset cursor** (``sort_col`` provided):
        Orders by ``<sort_col> <sort_dir>, id DESC`` to break ties.
        The cursor (``after``) is the ``id`` of the last returned row.
        Continuation pages must pass the same ``sort_col`` and ``sort_dir``
        so that the ``id``-based sub-sort remains consistent.  Rows whose
        sort-column value matches the boundary row are included only if
        their ``id`` is less than the cursor; rows with a strictly less
        favourable sort-column value are excluded entirely.

    Parameters
    ----------
    db:
        Active SQLAlchemy :class:`~sqlalchemy.orm.Session`.
    query:
        A SQLAlchemy ``Select`` statement targeting rows that have an
        ``id`` column populated with ULID strings.
    model:
        The ORM model class being queried.  Used to access the ``id``
        column for filtering and ordering.
    after:
        Optional ULID cursor identifying the last item seen.  Behaviour
        depends on the mode — see above.
    limit:
        Maximum number of items to return.  Clamped to
        :data:`_MAX_LIMIT`.  Defaults to :data:`_DEFAULT_LIMIT`.
    sort_col:
        Optional SQLAlchemy column object to sort by (e.g.
        ``Event.created_at``).  When provided, keyset cursor mode is
        active.  When ``None``, default ULID cursor mode is used.
    sort_dir:
        Sort direction for ``sort_col``: ``"asc"`` or ``"desc"``.
        Ignored when ``sort_col`` is ``None``.  Defaults to ``"desc"``.

    Returns
    -------
    PaginatedResponse
        A :class:`~wizards_engine.schemas.common.PaginatedResponse` with
        ``items``, ``next_cursor``, and ``has_more`` populated.
    """
    limit = min(limit, _MAX_LIMIT)

    if sort_col is None:
        # --- Default ULID cursor mode ---
        # ORDER BY id DESC; cursor is a raw ULID string.
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

    # --- Keyset cursor mode ---
    # ORDER BY sort_col <dir>, id DESC; cursor is the id of the last row.
    # To continue from a cursor we need the sort-col value of that row,
    # which we look up by id.
    col_order = asc(sort_col) if sort_dir == "asc" else desc(sort_col)
    q = query.order_by(col_order, desc(model.id))

    if after is not None:
        # Fetch the boundary row so we know its sort-column value.
        boundary = db.get(model, after)
        if boundary is not None:
            boundary_col_val = getattr(boundary, sort_col.key)
            if sort_dir == "asc":
                # Include rows where sort_col > boundary_val,
                # or sort_col == boundary_val and id < after.
                q = q.filter(
                    (sort_col > boundary_col_val)
                    | ((sort_col == boundary_col_val) & (model.id < after))
                )
            else:
                # Include rows where sort_col < boundary_val,
                # or sort_col == boundary_val and id < after.
                q = q.filter(
                    (sort_col < boundary_col_val)
                    | ((sort_col == boundary_col_val) & (model.id < after))
                )

    rows = db.scalars(q.limit(limit + 1)).all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


def paginate_with_filter(
    db: Session,
    query,
    *,
    model,
    filter_fn: Callable[[list], list],
    after: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> PaginatedResponse[Any]:
    """Apply ULID cursor pagination with a post-fetch visibility filter.

    Unlike :func:`paginate`, this function over-fetches rows from the database
    (``limit * 3``) and applies ``filter_fn`` to the batch before slicing to
    ``limit`` visible items.  This compensates for visibility filters that
    eliminate rows after DB retrieval, which would otherwise silently return
    fewer items than requested.

    Cursor semantics are identical to :func:`paginate` — newest-first (``id
    DESC``), with ``after`` as an exclusive upper bound on ``id``.

    Parameters
    ----------
    db:
        Active SQLAlchemy :class:`~sqlalchemy.orm.Session`.
    query:
        A SQLAlchemy ``Select`` statement targeting rows with an ``id`` column
        populated with ULID strings.  Must **not** already have ``ORDER BY``
        applied.
    model:
        The ORM model class being queried.  Used to access the ``id`` column.
    filter_fn:
        A callable that accepts a list of ORM model instances and returns a
        filtered list.  Applied to the over-fetched rows before slicing.
    after:
        Optional ULID cursor.  When provided, only rows whose ``id`` is less
        than this value are returned (i.e. older rows).
    limit:
        Maximum number of *visible* items to return.  Clamped to
        :data:`_MAX_LIMIT`.  Defaults to :data:`_DEFAULT_LIMIT`.

    Returns
    -------
    PaginatedResponse
        A :class:`~wizards_engine.schemas.common.PaginatedResponse` with
        ``items`` (already filtered), ``next_cursor``, and ``has_more``.

    Notes
    -----
    Cursor strategy when ``has_more`` is ``True``:

    * If visible items exceed ``limit`` — cursor points to the last *visible*
      item (normal case; caller resumes from there).
    * If we fetched a full ``limit * 3`` rows from DB but visible items
      <= ``limit`` — many rows were filtered out; cursor points to the last
      *DB row* so the caller resumes past all rows already examined.
    """
    limit = min(limit, _MAX_LIMIT)
    fetch_count = limit * 3

    q = query.order_by(desc(model.id))

    if after is not None:
        q = q.filter(model.id < after)

    db_rows = db.scalars(q.limit(fetch_count)).all()
    fetched_all_db = len(db_rows) < fetch_count

    visible = filter_fn(list(db_rows))

    if len(visible) > limit:
        # More visible items than needed — slice and cursor at last visible item.
        items = visible[:limit]
        next_cursor = items[-1].id
        has_more = True
    elif not fetched_all_db:
        # DB has more rows beyond what we fetched; caller must continue from last DB row.
        items = visible
        next_cursor = db_rows[-1].id if db_rows else None
        has_more = True
    else:
        # Fetched everything the DB had and visible fits within limit.
        items = visible
        next_cursor = None
        has_more = False

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
