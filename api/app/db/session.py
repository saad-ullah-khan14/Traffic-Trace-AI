"""Database connections.

Every SQL statement in this project runs through a connection obtained here.
Route handlers and services must never construct their own psycopg connection.

A pool is used rather than connect-per-query: opening a fresh connection costs
roughly 15 ms on Windows, which would consume a third of the matching engine's
50 ms budget before any work is done.

Rows come back as dicts (`dict_row`), so query modules return plain
dictionaries and nothing downstream depends on column ordering.
"""

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings
from app.db.numpy_types import register_numpy_loaders

# Binary float4[] results become numpy arrays instead of Python float lists.
# See app/db/numpy_types.py for why this matters to the latency budget.
register_numpy_loaders()

pool = ConnectionPool(
    conninfo=settings.DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    open=False,
)


def open_pool() -> None:
    """Open the pool and wait until it is usable. Called from the app lifespan."""
    if pool.closed:
        pool.open()
    pool.wait(timeout=10.0)


def close_pool() -> None:
    if not pool.closed:
        pool.close()


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Borrow a connection from the pool.

    Commits on clean exit, rolls back if the block raises. Standalone scripts
    can call this without any setup — the pool opens itself on first use.
    """
    if pool.closed:
        open_pool()
    with pool.connection() as conn:
        yield conn
