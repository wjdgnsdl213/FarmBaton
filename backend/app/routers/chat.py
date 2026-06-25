"""
상담 채팅 라우터 — 농장주↔청년농, 대화방 단위 = consult_request 1건.

GET  /api/consult-requests/{req_id}/messages — 대화 조회(양측)
POST /api/consult-requests/{req_id}/messages — 메시지 전송(수락된 상담만)

전화번호 비노출 정책에 따라 수락 후 연락은 전부 이 인앱 채팅으로 한다.
권한: 해당 상담의 농장 소유 농장주 또는 신청 청년농 본인만 접근 가능.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.db import get_db
from backend.app.routers.auth import get_current_user_optional
from backend.app.schemas import (
    ChatMessageCreate,
    ChatMessageItem,
    ChatThreadResponse,
)

router = APIRouter(prefix="/api/consult-requests", tags=["chat"])


def _authorize(req_id: int, user, conn):
    """이 상담의 당사자인지 검증 후 (consult_status, my_role) 반환.

    my_role: 'FARMER'(농장 소유주) | 'YOUNG'(신청 청년농).
    """
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user_id, role = user

    with conn.cursor() as cur:
        cur.execute("""
            SELECT cr.status, f.owner_id, yp.user_id
            FROM consult_request cr
            JOIN farm f ON f.id = cr.farm_id
            JOIN young_farmer_profile yp ON yp.id = cr.young_farmer_id
            WHERE cr.id = %s
        """, (req_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="상담 신청을 찾을 수 없습니다.")
    status, owner_id, yf_user_id = row

    if role == "FARMER" and owner_id == user_id:
        return status, "FARMER"
    if role == "YOUNG" and yf_user_id == user_id:
        return status, "YOUNG"
    raise HTTPException(status_code=403, detail="이 대화의 당사자만 접근할 수 있습니다.")


@router.get("/{req_id}/messages", response_model=ChatThreadResponse)
def list_messages(req_id: int, conn=Depends(get_db), user=Depends(get_current_user_optional)):
    status, my_role = _authorize(req_id, user, conn)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, sender_role, body, created_at
            FROM chat_message WHERE consult_request_id = %s ORDER BY created_at, id
        """, (req_id,))
        rows = cur.fetchall()
    messages = [
        ChatMessageItem(
            id=r[0], sender_role=r[1], body=r[2],
            created_at=r[3].isoformat(), mine=(r[1] == my_role),
        )
        for r in rows
    ]
    return ChatThreadResponse(
        consult_request_id=req_id, status=status,
        chat_enabled=(status == "ACCEPTED"), messages=messages,
    )


@router.post("/{req_id}/messages", response_model=ChatMessageItem, status_code=201)
def send_message(
    req_id: int, data: ChatMessageCreate,
    conn=Depends(get_db), user=Depends(get_current_user_optional),
):
    status, my_role = _authorize(req_id, user, conn)
    if status != "ACCEPTED":
        raise HTTPException(status_code=409, detail="상담이 수락된 후에 대화할 수 있습니다.")

    body = data.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="빈 메시지는 보낼 수 없습니다.")

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO chat_message (consult_request_id, sender_role, body)
            VALUES (%s, %s, %s)
            RETURNING id, sender_role, body, created_at
        """, (req_id, my_role, body))
        r = cur.fetchone()
    conn.commit()
    return ChatMessageItem(
        id=r[0], sender_role=r[1], body=r[2], created_at=r[3].isoformat(), mine=True,
    )
