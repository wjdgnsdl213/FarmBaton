-- ============================================================
-- 003_ai_report_cache.sql
-- AI 인수 검토 리포트 / 매칭 설명문 캐시 컬럼
-- 작성: 2026-06-22
-- 선행: 002_core_schema.sql
--
-- LLM(Claude)이 생성하는 설명문은 전부 결정론적 계산 결과(calc_total_value,
-- calc_match_score)를 그대로 문장화한 것이며, 1회 생성 후 이 컬럼에 캐시해
-- 재요청마다 재호출하지 않는다. match_score.explanation은 002에서 이미
-- "설명문(LLM 생성 가능)"으로 비워둔 컬럼을 그대로 사용.
-- ============================================================

ALTER TABLE farm
    ADD COLUMN IF NOT EXISTS ai_summary      TEXT,         -- 리포트 요약문(LLM 생성)
    ADD COLUMN IF NOT EXISTS ai_risk_notes   TEXT,          -- 리스크 설명문(LLM 생성)
    ADD COLUMN IF NOT EXISTS ai_generated_at TIMESTAMPTZ;   -- 생성 시각 (NULL이면 미생성 → 생성 트리거)

-- 검증:
-- SELECT ai_summary, ai_risk_notes, ai_generated_at FROM farm WHERE id = 1;
