-- ============================================================
-- 006_price_trend_normal_year.sql
-- price_trend에 KAMIS "평년가" 컬럼 추가
-- 작성: 2026-06-24
-- 선행: 002_core_schema.sql
--
-- KAMIS Open-API(periodProductList)에는 다년 평년 통계 엔드포인트가 없어
-- trend_index(전년 동기 비교 proxy)만 적재해 왔음(docs/handoff.md 참고).
-- KAMIS 웹사이트(API 아님)의 "소매가격 > 기간별" 화면에는 공식 "평년"
-- 행이 있고, "5개년 중 최고·최저 제외 3개년 평균"으로 명시돼 있음 —
-- 사용자가 직접 사과/복숭아/포도 3개 화면을 받아 db/seed/*.xls(HTML
-- export)로 제공. etl/06_normal_year_price.py가 이 정적 파일을 적재.
--
-- 가치평가 계산(valuation.py)에는 쓰지 않음 — PDF 리포트의 참고용
-- 시세 설명문에만 노출(rule 1: 수치 계산에 LLM/추가 변수 도입 금지).
-- 포도는 KAMIS 자체가 평년값을 "-"로 비워둠(변동성 과다) → NULL 유지.
-- ============================================================

ALTER TABLE price_trend
    ADD COLUMN IF NOT EXISTS normal_year_price NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS price_unit TEXT,
    ADD COLUMN IF NOT EXISTS normal_year_source TEXT;

COMMENT ON COLUMN price_trend.normal_year_price IS
    'KAMIS 소매가격 화면의 "평년" 값(5개년 중 최고·최저 제외 3개년 평균). 데이터 없으면 NULL(예: GRAPE).';
COMMENT ON COLUMN price_trend.price_unit IS
    '평년가 단위 라벨 (예: 10개, 2kg) — KAMIS 화면 캡션 그대로.';
COMMENT ON COLUMN price_trend.normal_year_source IS
    '평년가 출처 메모(조회 화면·품목/품종/등급·다운로드 일자).';

-- 검증:
-- SELECT crop_code, trend_index, normal_year_price, price_unit FROM price_trend;
