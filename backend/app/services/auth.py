"""
backend/app/services/auth.py

농가(FARMER) 로그인 — 이메일/비밀번호. 청년농(YOUNG)은 로그인 대상이 아님.
"""
from __future__ import annotations

import datetime
import os

import bcrypt
import jwt

TOKEN_TTL_DAYS = 30


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET 환경변수가 설정되지 않았습니다.")
    return secret


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str) -> int:
    """토큰에서 user_id 추출. 위변조/만료 시 jwt.PyJWTError 발생."""
    payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    return int(payload["sub"])
