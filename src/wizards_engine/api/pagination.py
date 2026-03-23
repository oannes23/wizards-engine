"""ULID cursor-based pagination utility for SQLAlchemy queries.

All list endpoints in Wizards Engine use ULID-ordered, cursor-based
pagination.  Since ULIDs are lexicographically sortable by creation
time, ordering by ``id`` DESC gives newest-first results and the cursor
is just the ``id`` string of the last seen item.

When a custom ``order_by`` expression is provided via the ``sort_col``
parameter, the paginator switches to keyset pagination: the cursor
encodes the last-seen sort column value **and** the row ``id``, allowing
correct forward paging through arbitrary sort orders without duplicate
or missing rows.
"""

import base64
import json
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import asc, desc, or_, and_
from sqlalchemy.orm import Session

from wizards_engine.schemas.common import PaginatedResponse

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 100

ModelT = TypeVar("ModelT")


def _encode_cursor(sort_value: Any, row_id: str) -> str:
    """Encode a keyset cursor as a URL-safe base64 JSON string.

    Parameters
    ----------
    sort_value:
        The primary sort column value for the last-seen row.  Must be
        JSON-serialisable (strings, numbers, ISO-format datetimes serialised
        as strings).
    row_id:
        The ULID ``id`` of the last-seen row, used as the tiebreaker.

    Returns
    -------
    str
        URL-safe base64-encoded JSON string.
    """
    payload = json.dumps({"v": sort_value, "id": row_id}, default=str)
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[Any, str] | None:
    """Decode a keyset cursor produced by :func:`_encode_cursor`.

    Returns ``None`` on any decode error so callers can treat a bad cursor
    gracefully (e.g. ignore it and return from the beginning).

    Parameters
    ----------
    cursor:
        URL-safe base64 string as produced by :func:`_encode_cursor`.

    Returns
    -------
    tuple[Any, str] | None
        ``(sort_value, row_id)`` if the cursor is valid, else ``None``.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return payload["v"], payload["id"]
    except Exception:
        return None


def paginate(
    db: Session,
    query,
    *,
    model,
    after: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    order_by=None,
    sort_col=None,
    sort_dir: str = "desc",
) -> PaginatedResponse[Any]:
    """Apply cursor-based pagination to a SQLAlchemy query and return results.

    Two pagination modes are supported:

    **ULID cursor mode** (default — no ``sort_col``):
        Orders by ``id DESC`` and uses the ``id`` value directly as the
        cursor.  This is equivalent to the original behaviour.  Callers
        pass a bare ULID string as ``after``.

    **Keyset cursor mode** (when ``sort_col`` is provided):
        Orders by ``(sort_col <direction>, id DESC)`` and encodes the last
        row's ``(sort_col_value, id)`` pair as the cursor.  This guarantees
        correct forward paging through any sort order without duplicates.

    The query must **not** already have an ``ORDER BY`` clause applied.

    Parameters
    ----------
    db:
        Active SQLAlchemy :class:`~sqlalchemy.orm.Session`.
    query:
        A SQLAlchemy ``Select`` statement targeting rows with an ``id``
        column populated with ULID strings.
    model:
        The ORM model class being queried.  Used to access the ``id``
        column.
    after:
        Optional cursor string.  In ULID mode this is a bare ULID; in
        keyset mode this is a base64-encoded keyset cursor produced by a
        previous page response.
    limit:
        Maximum number of items to return.  Clamped to
        :data:`_MAX_LIMIT`.  Defaults to :data:`_DEFAULT_LIMIT`.
    order_by:
        **Deprecated** — use ``sort_col`` + ``sort_dir`` instead.  When
        provided and ``sort_col`` is ``None``, this expression is used
        as the primary sort and ULID cursor mode is still used (legacy
        behaviour matching the original Story 8.3.1 interface).
    sort_col:
        SQLAlchemy column object to sort by.  When provided, keyset cursor
        mode is activated.  Must be the same column object used in the
        ``SELECT`` — not a string.
    sort_dir:
        Sort direction for ``sort_col`` — ``"asc"`` or ``"desc"``.
        Defaults to ``"desc"``.  Ignored when ``sort_col`` is ``None``.

    Returns
    -------
    PaginatedResponse
        A :class:`~wizards_engine.schemas.common.PaginatedResponse` with
        ``items``, ``next_cursor``, and ``has_more`` populated.
    """
    limit = min(limit, _MAX_LIMIT)

    if sort_col is not None:
        # ---------------------------------------------------------------
        # Keyset pagination mode: sort by (sort_col, id DESC) and encode
        # both values in the cursor so we can page correctly.
        # ---------------------------------------------------------------
        if sort_dir == "asc":
            primary_order = asc(sort_col)
        else:
            primary_order = desc(sort_col)

        q = query.order_by(primary_order, desc(model.id))

        if after is not None:
            decoded = _decode_cursor(after)
            if decoded is not None:
                last_val, last_id = decoded
                # Keyset condition: rows that come *after* the cursor in the
                # sorted order.
                # For ASC primary sort:  (col > last_val) OR (col == last_val AND id < last_id)
                # For DESC primary sort: (col < last_val) OR (col == last_val AND id < last_id)
                if sort_dir == "asc":
                    q = q.filter(
                        or_(
                            sort_col > last_val,
                            and_(sort_col == last_val, model.id < last_id),
                        )
                    )
                else:
                    q = q.filter(
                        or_(
                            sort_col < last_val,
                            and_(sort_col == last_val, model.id < last_id),
                        )
                    )

        rows = db.scalars(q.limit(limit + 1)).all()
        has_more = len(rows) > limit
        items = rows[:limit]

        if has_more and items:
            last_item = items[-1]
            last_sort_val = getattr(last_item, sort_col.key)
            next_cursor = _encode_cursor(last_sort_val, last_item.id)
        else:
            next_cursor = None

    elif order_by is not None:
        # ---------------------------------------------------------------
        # Legacy mode: custom order expression but ULID cursor (id < after).
        # Correct only when the sort order correlates with id order (e.g.
        # sort by created_at where ULID ≈ creation time).
        # ---------------------------------------------------------------
        q = query.order_by(order_by, desc(model.id))

        if after is not None:
            q = q.filter(model.id < after)

        rows = db.scalars(q.limit(limit + 1)).all()
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = items[-1].id if has_more and items else None

    else:
        # ---------------------------------------------------------------
        # Default mode: ORDER BY id DESC with bare ULID cursor.
        # ---------------------------------------------------------------
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

    Cursor semantics are identical to the default mode of :func:`paginate` —
    newest-first (``id DESC``), with ``after`` as an exclusive upper bound
    on ``id``.

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
