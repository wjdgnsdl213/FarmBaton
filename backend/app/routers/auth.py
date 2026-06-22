"""
농가 로그인 라우터.

POST /api/auth/register — 농가 회원가입 (이메일/비밀번호)
POST /api/auth/login    — 로그인
GET  /api/auth/me       — 현재 로그인한 농가 정보
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.app.db import get_db
from backend.app.schemas import AuthResponse, LoginRequest, MeResponse, RegisterRequest
from backend.app.services.auth import create_token, decode_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_current_farmer(authorization: str = Header(default=""), conn=Depends(get_db)) -> int:
    """Authorization: Bearer <token> → user_id. 다른 라우터에서 Depends로 재사용."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    token = authorization.removeprefix("Bearer ")
    try:
        user_id = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 토큰입니다.")

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM app_user WHERE id = %s AND role = 'FARMER'", (user_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=401, detail="유효하지 않은 사용자입니다.")
    return user_id


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(data: RegisterRequest, conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM app_user WHERE email = %s", (data.email,))
        if cur.fetchone() is not None:
            raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

        cur.execute("""
            INSERT INTO app_user (role, name, phone, email, password_hash, is_demo)
            VALUES ('FARMER', %s, %s, %s, %s, FALSE)
            RETURNING id
        """, (data.name, data.phone, data.email, hash_password(data.password)))
        user_id = cur.fetchone()[0]
    conn.commit()

    return AuthResponse(token=create_token(user_id), user_id=user_id, name=data.name)


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, password_hash FROM app_user
            WHERE email = %s AND role = 'FARMER'
        """, (data.email,))
        row = cur.fetchone()

    if row is None or row[2] is None or not verify_password(data.password, row[2]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    user_id, name, _ = row
    return AuthResponse(token=create_token(user_id), user_id=user_id, name=name or "")


@router.get("/me", response_model=MeResponse)
def me(user_id: int = Depends(get_current_farmer), conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute("SELECT name, email FROM app_user WHERE id = %s", (user_id,))
        name, email = cur.fetchone()
    return MeResponse(user_id=user_id, name=name or "", email=email or "")
