-- ============================================================
-- 007_report_narrative_audience.sql
-- 리포트 AI 설명문을 관점(농가/청년농)별로 캐시
-- 작성: 2026-06-24
-- 선행: 003_ai_report_cache.sql
--
-- 같은 농장이라도 PDF를 받는 주체에 따라 설명문 관점이 달라야 함:
--   FARMER(농장주) — 매도 준비·시설 가치 어필·영업권 정밀화 자료
--   YOUNG(청년농)  — 인수 검토·자본 회수·정책자금·영농 시작 체크리스트
-- 003의 farm.ai_summary/ai_risk_notes 단일 컬럼으론 한 관점만 저장 가능해
-- (farm_id, audience) 복합키 캐시 테이블을 새로 둔다. 003 컬럼은 그대로
-- 두되(과거 데이터 보존) 신규 경로는 이 테이블만 사용한다.
--
-- summary/risk_notes/advice 모두 결정론적 계산 결과를 문장화한 것이며
-- (rule 1: 숫자 계산에 LLM 금지), 1회 생성 후 캐시해 재호출하지 않는다.
-- ============================================================

CREATE TABLE IF NOT EXISTS report_narrative (
    farm_id        BIGINT NOT NULL REFERENCES farm(id) ON DELETE CASCADE,
    audience       TEXT NOT NULL CHECK (audience IN ('FARMER', 'YOUNG')),
    summary        TEXT NOT NULL,
    risk_notes     TEXT NOT NULL,
    advice         TEXT NOT NULL,          -- 관점별 조언/다음 단계 (신규)
    is_ai          BOOLEAN NOT NULL DEFAULT FALSE,  -- AI 생성 여부(폴백이면 FALSE)
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (farm_id, audience)
);

-- 검증:
-- SELECT farm_id, audience, is_ai, generated_at FROM report_narrative ORDER BY farm_id;
