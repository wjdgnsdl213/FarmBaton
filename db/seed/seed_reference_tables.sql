-- ============================================================
-- 팜바톤 정적 기준 테이블 (시설 표준단가 / 과수 수령 보정계수)
-- 작성: 2026-06 | PostgreSQL (Supabase) 기준
--
-- [출처 및 정밀도 메모]
-- · 시설 단가: 시장 시공가 조사치(비닐하우스 평당 8~11만원 등)의
--   보수적 중간값. 제출 전 농진청 농축산물소득자료집의
--   "감가상각비 산정 기준"과 대조하여 보정할 것.
-- · 내용연수: 농진청 소득조사 감가상각 관행 기준(비닐하우스 10년,
--   판넬건물 20년, 관수 8년 등)에 맞춘 값.
-- · 수령 계수: 과수 재배 일반론(결실 시작·성목기·경제수령)을
--   구간 계수로 변환한 자체 설계값. 발표 시 "농진청 재배기술
--   자료 기반 자체 산정 계수"로 표기.
-- ============================================================

CREATE TABLE IF NOT EXISTS facility_std (
    facility_code      VARCHAR(20) PRIMARY KEY,
    facility_name      VARCHAR(60)  NOT NULL,
    unit               VARCHAR(10)  NOT NULL DEFAULT 'm2',
    std_unit_cost_krw  INTEGER      NOT NULL,   -- 표준 설치단가(원/㎡)
    useful_life_years  SMALLINT     NOT NULL,   -- 내용연수
    salvage_rate       NUMERIC(3,2) NOT NULL DEFAULT 0.05, -- 잔존가율
    note               TEXT
);

CREATE TABLE IF NOT EXISTS orchard_age_coef (
    crop_code   VARCHAR(10) NOT NULL,
    crop_name   VARCHAR(20) NOT NULL,
    age_from    SMALLINT    NOT NULL,
    age_to      SMALLINT    NOT NULL,
    yield_coef  NUMERIC(3,2) NOT NULL,  -- 성목기=1.00 기준 소득 계수
    phase       VARCHAR(30),
    note        TEXT,
    PRIMARY KEY (crop_code, age_from)
);

-- 시설 상태등급 보정 (경영주 입력: 상/중/하)
CREATE TABLE IF NOT EXISTS facility_condition (
    grade       CHAR(1) PRIMARY KEY,   -- A=상, B=중, C=하
    multiplier  NUMERIC(3,2) NOT NULL
);
INSERT INTO facility_condition VALUES ('A',1.00),('B',0.85),('C',0.60)
ON CONFLICT (grade) DO NOTHING;

-- CSV 적재 (Supabase SQL Editor에서는 Table Editor 임포트 권장,
-- 로컬 psql 기준):
-- \copy facility_std     FROM 'facility_std.csv'     CSV HEADER;
-- \copy orchard_age_coef FROM 'orchard_age_coef.csv' CSV HEADER;

-- ============================================================
-- 활용 예시 1: 시설 잔존가 계산
--   잔존가 = 단가 × 면적 × MAX(잔존가율, 1 - 경과연수/내용연수)
--            × 상태등급 보정
-- ============================================================
-- SELECT f.facility_name,
--        f.std_unit_cost_krw * a.area_m2
--          * GREATEST(f.salvage_rate,
--                     1 - (EXTRACT(YEAR FROM now()) - a.installed_year)::numeric
--                         / f.useful_life_years)
--          * c.multiplier AS residual_value_krw
-- FROM   farm_asset a
-- JOIN   facility_std f      ON f.facility_code = a.facility_code
-- JOIN   facility_condition c ON c.grade = a.condition_grade;

-- ============================================================
-- 활용 예시 2: 수령 보정 소득 추정
--   예상소득 = 10a당 평균소득(소득조사) × 면적(10a) × 수령계수
-- ============================================================
-- SELECT i.avg_income_per_10a * (p.area_m2 / 991.7) * o.yield_coef
--          AS est_annual_income_krw
-- FROM   farm p
-- JOIN   income_coef i ON i.crop_code = p.crop_code
-- JOIN   orchard_age_coef o
--        ON o.crop_code = p.crop_code
--       AND p.tree_age BETWEEN o.age_from AND o.age_to;
