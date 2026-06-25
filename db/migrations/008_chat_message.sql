-- ============================================================
-- 008_chat_message.sql
-- 상담 수락 후 농장주↔청년농 인앱 채팅
-- 작성: 2026-06-25
-- 선행: 002_core_schema.sql (consult_request)
--
-- 대화방 단위 = consult_request 1건. 상담이 ACCEPTED 된 뒤에만 메시지를
-- 주고받는다(애플리케이션에서 강제). 전화번호 비노출 정책에 따라 연락은
-- 전부 이 인앱 채팅으로 이뤄진다.
-- ============================================================

CREATE TABLE IF NOT EXISTS chat_message (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    consult_request_id  BIGINT NOT NULL REFERENCES consult_request(id) ON DELETE CASCADE,
    sender_role         TEXT NOT NULL CHECK (sender_role IN ('FARMER', 'YOUNG')),
    body                TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_message_consult
    ON chat_message (consult_request_id, created_at);

-- 검증:
-- SELECT consult_request_id, sender_role, left(body,20), created_at FROM chat_message ORDER BY id;
