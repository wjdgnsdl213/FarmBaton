"""
인증 라우터 (농가·청년농 공통).

POST /api/auth/register — 회원가입 (role=FARMER|YOUNG 선택)
POST /api/auth/login    — 로그인 (역할 무관, 응답에 role 포함)
GET  /api/auth/me       — 현재 로그인한 사용자 정보
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.app.db import get_db
from backend.app.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
    UpdateMeRequest,
)
from backend.app.services.auth import create_token, decode_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_current_farmer(authorization: str = Header(default=""), conn=Depends(get_db)) -> int:
    """Authorization: Bearer <token> → FARMER user_id. 농장 소유 엔드포인트 전용."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    token = authorization.removeprefix("Bearer ")
    try:
        user_id = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 토큰입니다.")

    with conn.cursor() as cur:
        # ADMIN은 농가·청년농 양쪽 플로우를 모두 이용할 수 있다(운영/시연용).
        cur.execute("SELECT 1 FROM app_user WHERE id = %s AND role IN ('FARMER','ADMIN')", (user_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=403, detail="농가 계정만 이용할 수 있습니다.")
    return user_id


def get_current_user_optional(
    authorization: str = Header(default=""), conn=Depends(get_db)
) -> Optional[tuple[int, str]]:
    """토큰이 있으면 (user_id, role), 없거나 유효하지 않으면 None.

    로그인 없이도 동작해야 하는 엔드포인트(청년농 매칭·상담)에서 사용 —
    로그인한 사용자에겐 추가 동작(본인 정보 자동 사용)을, 익명에겐 기존
    동작을 그대로 제공한다.
    """
    if not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        user_id = decode_token(token)
    except Exception:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT role::TEXT FROM app_user WHERE id = %s", (user_id,))
        row = cur.fetchone()
    if row is None:
        return None
    return (user_id, row[0])


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(data: RegisterRequest, conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM app_user WHERE email = %s", (data.email,))
        if cur.fetchone() is not None:
            raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

        cur.execute("""
            INSERT INTO app_user (role, name, phone, email, password_hash, is_demo)
            VALUES (%s::user_role_t, %s, %s, %s, %s, FALSE)
            RETURNING id
        """, (data.role, data.name, data.phone, data.email, hash_password(data.password)))
        user_id = cur.fetchone()[0]
    conn.commit()

    return AuthResponse(token=create_token(user_id), user_id=user_id, name=data.name, role=data.role)


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, password_hash, role::TEXT FROM app_user
            WHERE email = %s
        """, (data.email,))
        row = cur.fetchone()

    if row is None or row[2] is None or not verify_password(data.password, row[2]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    user_id, name, _, role = row
    return AuthResponse(token=create_token(user_id), user_id=user_id, name=name or "", role=role)


@router.get("/me", response_model=MeResponse)
def me(authorization: str = Header(default=""), conn=Depends(get_db)):
    user = get_current_user_optional(authorization, conn)
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user_id, role = user
    with conn.cursor() as cur:
        cur.execute("SELECT name, email, phone FROM app_user WHERE id = %s", (user_id,))
        name, email, phone = cur.fetchone()
    return MeResponse(user_id=user_id, name=name or "", email=email or "", role=role, phone=phone)


@router.patch("/me", response_model=MeResponse)
def update_me(data: UpdateMeRequest, authorization: str = Header(default=""), conn=Depends(get_db)):
    """계정 정보 수정 (이름·연락처). 이메일·역할은 변경 불가."""
    user = get_current_user_optional(authorization, conn)
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user_id, role = user
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE app_user SET name = %s, phone = %s WHERE id = %s RETURNING email",
            (data.name, data.phone, user_id),
        )
        email = cur.fetchone()[0]
    conn.commit()
    return MeResponse(user_id=user_id, name=data.name, email=email or "", role=role, phone=data.phone)


@router.post("/password", status_code=204)
def change_password(data: ChangePasswordRequest, authorization: str = Header(default=""), conn=Depends(get_db)):
    """비밀번호 변경 — 현재 비밀번호 확인 후 교체."""
    user = get_current_user_optional(authorization, conn)
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user_id, _role = user
    with conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM app_user WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if row is None or row[0] is None or not verify_password(data.current_password, row[0]):
            raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")
        cur.execute(
            "UPDATE app_user SET password_hash = %s WHERE id = %s",
            (hash_password(data.new_password), user_id),
        )
    conn.commit()
