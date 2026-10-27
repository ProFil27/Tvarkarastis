"""PostgreSQL connection pool.

Only the persistence repositories use this class (N-02): nothing else in the
system opens database connections.
"""

from contextlib import contextmanager
from typing import Iterator

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

from app.infrastructure.config import Settings


class Database:
    def __init__(self, settings: Settings, min_connections: int = 1, max_connections: int = 10):
        self._pool = SimpleConnectionPool(
            min_connections,
            max_connections,
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
        )

    @contextmanager
    def cursor(self, commit: bool = False) -> Iterator:
        """Yield a dict-style cursor for one database operation."""
        connection = self._pool.getconn()
        try:
            cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                yield cursor
                if commit:
                    connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()
        finally:
            self._pool.putconn(connection)
