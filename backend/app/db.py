"""psycopg2 커넥션 풀 — FastAPI Dependency로 사용."""
import os

import psycopg2
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


def _is_alive(conn) -> bool:
    """유휴 중 서버가 끊은 커넥션인지 확인(pre-ping). 살아있으면 정리 후 True."""
    if conn.closed:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.rollback()
        return True
    except psycopg2.Error:
        return False


def get_db():
    """FastAPI Dependency: psycopg2 connection → pool 반환.

    풀에서 꺼낸 커넥션이 서버 측에서 이미 끊긴 상태면 버리고 새로 발급받는다
    (Supabase가 유휴 커넥션을 끊어도 다음 요청이 죽은 커넥션을 계속 재사용해
    500이 반복되는 걸 방지). 요청 처리 중 끊긴 경우도 풀에 되돌리지 않고 폐기한다.
    """
    pool = _get_pool()
    conn = pool.getconn()
    if not _is_alive(conn):
        pool.putconn(conn, close=True)
        conn = pool.getconn()

    try:
        yield conn
    except Exception:
        if not conn.closed:
            try:
                conn.rollback()
            except psycopg2.Error:
                pass
        raise
    finally:
        pool.putconn(conn, close=conn.closed)
