-- ============================================================
-- 010_young_intro.sql
-- 청년농 프로필에 한 줄 자기소개 + 검색/프로필 분리 대비
-- 작성: 2026-06-25
-- 선행: 002_core_schema.sql (young_farmer_profile)
--
-- young_farmer_profile은 이제 "검색 입력값"이 아니라 청년농의 실제 프로필
-- (내 정보에서 설정, 상담 신청 시 농장주에게 노출)이다. 매칭 검색은 별도
-- 미저장 엔드포인트(/match-search)로 처리해 프로필을 덮어쓰지 않는다.
-- intro: 농장주에게 보일 자기소개(선택).
-- ============================================================

ALTER TABLE young_farmer_profile
    ADD COLUMN IF NOT EXISTS intro TEXT;

-- 검증:
-- SELECT id, user_id, intro FROM young_farmer_profile ORDER BY id;
