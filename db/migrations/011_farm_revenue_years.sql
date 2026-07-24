-- ============================================================
-- 011_farm_revenue_years.sql
-- 매출 자료 기간(없음/1년/3년) 저장
-- 선행: 002_core_schema.sql
-- ============================================================

ALTER TABLE farm
    ADD COLUMN IF NOT EXISTS revenue_years SMALLINT NOT NULL DEFAULT 0;

UPDATE farm
SET revenue_years = 1
WHERE annual_revenue IS NOT NULL
  AND revenue_years = 0;

ALTER TABLE farm
    DROP CONSTRAINT IF EXISTS ck_farm_revenue_years;

ALTER TABLE farm
    ADD CONSTRAINT ck_farm_revenue_years
    CHECK (revenue_years IN (0, 1, 3));

-- 검증:
-- SELECT revenue_years, COUNT(*) FROM farm GROUP BY revenue_years ORDER BY revenue_years;
