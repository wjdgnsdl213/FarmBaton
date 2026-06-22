-- ============================================================
-- 004_farmer_auth.sql
-- 농가 로그인(이메일/비밀번호) + 상담 신청 연락처
-- 작성: 2026-06-22
-- 선행: 002_core_schema.sql
--
-- 로그인은 농가(FARMER)만 대상. 청년농(YOUNG)은 로그인 없이 상담 신청
-- 시점에 이름/연락처를 직접 입력 — 그래서 young_farmer_profile이 아니라
-- consult_request에 연락처 컬럼을 둔다.
-- ============================================================

ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS email         TEXT UNIQUE,   -- 농가 로그인용 (청년농은 NULL)
    ADD COLUMN IF NOT EXISTS password_hash TEXT;          -- bcrypt 해시

ALTER TABLE consult_request
    ADD COLUMN IF NOT EXISTS contact_name  TEXT,
    ADD COLUMN IF NOT EXISTS contact_phone TEXT;

-- 검증:
-- SELECT email, password_hash IS NOT NULL FROM app_user WHERE role = 'FARMER';
-- SELECT contact_name, contact_phone FROM consult_request;
