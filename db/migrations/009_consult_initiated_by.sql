-- ============================================================
-- 009_consult_initiated_by.sql
-- 상담/대화 발신 주체 구분 (청년농 신청 vs 농장주 발신)
-- 작성: 2026-06-25
-- 선행: 002(consult_request), 008(chat_message)
--
-- 농장주가 매칭 후보(미신청) 청년농에게 먼저 대화를 거는 경우를 지원한다.
-- 이때 consult_request 를 status='ACCEPTED', initiated_by='FARMER' 로 생성해
-- 기존 채팅(chat_message)·대화 목록을 그대로 재사용한다.
-- 기존 청년농 신청 건은 모두 'YOUNG'(기본값).
-- ============================================================

ALTER TABLE consult_request
    ADD COLUMN IF NOT EXISTS initiated_by TEXT NOT NULL DEFAULT 'YOUNG'
        CHECK (initiated_by IN ('YOUNG', 'FARMER'));

-- 같은 (농장, 청년농) 대화는 1개만 — 발신 중복 방지
CREATE UNIQUE INDEX IF NOT EXISTS uq_consult_farm_young
    ON consult_request (farm_id, young_farmer_id);

-- 검증:
-- SELECT farm_id, young_farmer_id, status, initiated_by FROM consult_request ORDER BY id;
