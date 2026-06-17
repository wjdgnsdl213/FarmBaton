"""psycopg2 커넥션 풀 — FastAPI Dependency로 사용."""
import os

from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")
        _pool = ThreadedConnectionPool(1, 5, dsn=url)
    return _pool


def get_db():
    """FastAPI Dependency: psycopg2 connection → pool 반환."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)
