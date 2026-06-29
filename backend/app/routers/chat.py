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
    ConversationItem,
)
from backend.app.services.report_ai import CROP_NAMES

router = APIRouter(prefix="/api/consult-requests", tags=["chat"])

# 별도 prefix 라우터 — 대화 목록(역할 무관)
conv_router = APIRouter(prefix="/api/conversations", tags=["chat"])


def _farm_label(sido: str | None, crop: str | None) -> str:
    return f"{sido or ''} {CROP_NAMES.get(crop, crop or '')} 농장".strip()


@conv_router.get("", response_model=list[ConversationItem])
def list_conversations(conn=Depends(get_db), user=Depends(get_current_user_optional)):
    """현재 사용자의 대화 목록(수락된 상담 = 대화방). 역할에 따라 자동 분기."""
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user_id, role = user

    # ADMIN은 농장 소유자(=농장주) 입장으로 대화를 본다(운영/시연용).
    if role in ("FARMER", "ADMIN"):
        where = "f.owner_id = %s"
        # 상대 = 청년농 계정 이름
        counterpart = "yau.name"
    elif role == "YOUNG":
        where = "yp.user_id = %s"
        # 상대 = 농장주 계정 이름
        counterpart = "fau.name"
    else:
        return []

    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT cr.id, f.id, f.sido, f.crop_code::TEXT, cr.initiated_by,
                   {counterpart},
                   (SELECT max(created_at) FROM chat_message WHERE consult_request_id = cr.id),
                   (SELECT body FROM chat_message WHERE consult_request_id = cr.id
                    ORDER BY created_at DESC, id DESC LIMIT 1)
            FROM consult_request cr
            JOIN farm f ON f.id = cr.farm_id
            JOIN app_user fau ON fau.id = f.owner_id
            JOIN young_farmer_profile yp ON yp.id = cr.young_farmer_id
            JOIN app_user yau ON yau.id = yp.user_id
            WHERE {where} AND cr.status = 'ACCEPTED'
            ORDER BY COALESCE(
                (SELECT max(created_at) FROM chat_message WHERE consult_request_id = cr.id),
                cr.created_at
            ) DESC
        """, (user_id,))
        rows = cur.fetchall()

    return [
        ConversationItem(
            consult_request_id=r[0], farm_id=r[1],
            farm_label=_farm_label(r[2], r[3]), initiated_by=r[4],
            counterpart_name=r[5] or "상대방",
            last_message_at=r[6].isoformat() if r[6] else None,
            last_message_preview=r[7],
        )
        for r in rows
    ]


def _authorize(req_id: int, user, conn):
    """이 상담의 당사자인지 검증 후 (status, my_role, counterpart_name, farm_label) 반환.

    my_role: 'FARMER'(농장 소유주) | 'YOUNG'(신청 청년농).
    """
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user_id, role = user

    with conn.cursor() as cur:
        cur.execute("""
            SELECT cr.status, f.owner_id, yp.user_id,
                   f.sido, f.crop_code::TEXT, fau.name, yau.name
            FROM consult_request cr
            JOIN farm f ON f.id = cr.farm_id
            JOIN app_user fau ON fau.id = f.owner_id
            JOIN young_farmer_profile yp ON yp.id = cr.young_farmer_id
            JOIN app_user yau ON yau.id = yp.user_id
            WHERE cr.id = %s
        """, (req_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="상담 신청을 찾을 수 없습니다.")
    status, owner_id, yf_user_id, sido, crop, farmer_name, young_name = row
    farm_label = _farm_label(sido, crop)

    # ADMIN은 소유 관계로 당사자를 판별(농장 소유 → 농장주, 청년농 본인 → 청년농).
    if owner_id == user_id and role in ("FARMER", "ADMIN"):
        return status, "FARMER", (young_name or "청년농"), farm_label
    if yf_user_id == user_id and role in ("YOUNG", "ADMIN"):
        return status, "YOUNG", (farmer_name or "농장주"), farm_label
    raise HTTPException(status_code=403, detail="이 대화의 당사자만 접근할 수 있습니다.")


@router.get("/{req_id}/messages", response_model=ChatThreadResponse)
def list_messages(req_id: int, conn=Depends(get_db), user=Depends(get_current_user_optional)):
    status, my_role, counterpart, farm_label = _authorize(req_id, user, conn)
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
        chat_enabled=(status == "ACCEPTED"),
        counterpart_name=counterpart, farm_label=farm_label, messages=messages,
    )


@router.post("/{req_id}/messages", response_model=ChatMessageItem, status_code=201)
def send_message(
    req_id: int, data: ChatMessageCreate,
    conn=Depends(get_db), user=Depends(get_current_user_optional),
):
    status, my_role, _counterpart, _farm = _authorize(req_id, user, conn)
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
