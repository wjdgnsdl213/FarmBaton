-- ============================================================
-- 005_support_program.sql
-- 지원사업(정책자금) 기준 테이블
-- 작성: 2026-06-23
-- 선행: 002_core_schema.sql
--
-- facility_std와 동일한 정적 기준 테이블 패턴. target_sido/target_crop이
-- NULL이면 "전국"/"전체 작목" 대상. 자격·금액 등 사실 정보는 이 테이블의
-- CSV 원문을 그대로 노출하고, LLM은 추천 사유 한 줄만 덧붙인다
-- (report_ai.generate_program_pitch) — 절대 LLM이 이 테이블의 값을
-- 새로 만들거나 바꾸지 않는다.
--
-- 데이터: db/seed/support_program.csv (정훈님이 정리해서 제공할 때까지
-- 빈 테이블로 둔다 — 임의로 사업 내용을 채우지 않음, CLAUDE.md rule 8).
-- ============================================================

CREATE TABLE IF NOT EXISTS support_program (
    program_code    TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    target_sido     TEXT,              -- NULL = 전국
    target_crop     TEXT,              -- NULL = 전체 작목 (APPLE/PEACH/GRAPE)
    target_role     TEXT NOT NULL,     -- YOUNG | FARMER | ANY
    description     TEXT NOT NULL,
    amount_text     TEXT NOT NULL,
    apply_url       TEXT,
    source_refs     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 검증:
-- SELECT program_code, name, target_sido, target_crop FROM support_program;
