"""DPK (data access component).

The only place in the system that talks to PostgreSQL directly (N-02). Other
components (AK, TVK, DVK, KVK, AA, AN) must reach the database through this
module or through the repository modules built on it (dpk.users,
dpk.schedules, ...), never through their own psycopg2 calls.
"""

from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

_pool: SimpleConnectionPool | None = None


def init_pool(config, minconn: int = 1, maxconn: int = 10) -> None:
    global _pool
    if _pool is not None:
        return
    _pool = SimpleConnectionPool(
        minconn,
        maxconn,
        host=config.db_host,
        port=config.db_port,
        dbname=config.db_name,
        user=config.db_user,
        password=config.db_password,
    )


@contextmanager
def get_cursor(commit: bool = False):
    """Yield a dict-style cursor for a single database operation.

    Usage:
        with get_cursor(commit=True) as cur:
            cur.execute("INSERT INTO users (...) VALUES (...)", (...))
    """
    if _pool is None:
        raise RuntimeError("DPK connection pool is not initialised (call init_pool).")

    conn = _pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        _pool.putconn(conn)
