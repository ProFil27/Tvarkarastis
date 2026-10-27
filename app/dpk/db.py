"""DPK (Duomenu prieigos komponentas).

Vienintele vieta sistemoje, kuri tiesiogiai kreipiasi i PostgreSQL duomenu baze
(N-02). Kiti komponentai (AK, TVK, DVK, KVK, AA, AN) duomenu baze turi pasiekti
tik per sita modulį arba per repository funkcijas, kurias teammate'ai pries
(dpk.users, dpk.schedules, ...), o ne per savo pacius psycopg2 kvietimus.
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
    """Suteikia dict-stiliaus kursoriu vienai duomenu bazes operacijai.

    Naudojimas:
        with get_cursor(commit=True) as cur:
            cur.execute("INSERT INTO users (...) VALUES (...)", (...))
    """
    if _pool is None:
        raise RuntimeError("DPK duomenu bazes jungciu tekle neinicializuota (init_pool).")

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
