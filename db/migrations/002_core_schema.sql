-- ============================================================
-- 002_core_schema.sql
-- 팜바톤 본체 스키마 (Supabase / PostgreSQL + PostGIS)
-- 작성: 2026-06-12
-- 선행: 001_reference_tables.sql (facility_std, orchard_age_curve_std 등)
--
-- 사전 1회: CREATE EXTENSION IF NOT EXISTS postgis;
-- 좌표계 규칙: 모든 geometry는 EPSG:4326 저장 (SHP 5186 → 적재 시 변환)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ────────────────────────────────────────────────
-- 공통 enum
-- ────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE crop_code_t       AS ENUM ('APPLE','PEACH','GRAPE');
    CREATE TYPE succession_type_t AS ENUM ('SALE','LEASE','JOINT','MENTORING'); -- 매도/임대/공동경영/멘토후독립
    CREATE TYPE timing_t          AS ENUM ('NOW','WITHIN_1Y','WITHIN_3Y','WITHIN_5Y');
    CREATE TYPE confidence_t      AS ENUM ('A','B','C','D'); -- 리포트 신뢰도 등급
    CREATE TYPE listing_status_t  AS ENUM ('DRAFT','ACTIVE','MATCHED','CLOSED');
    CREATE TYPE user_role_t       AS ENUM ('FARMER','YOUNG','ADMIN');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ────────────────────────────────────────────────
-- 1. 사용자
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_user (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role        user_role_t NOT NULL,
    name        TEXT,
    phone       TEXT,
    is_demo     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ────────────────────────────────────────────────
-- 2. 팜맵 필지 (ETL 적재 대상, 읽기 전용 성격)
--    SHP 원본 5186 → 4326 변환 적재. 과수원 분류만 보관.
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS parcel (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pnu           TEXT,                       -- 필지고유번호(있으면)
    bjd_cd        TEXT,                       -- 법정동코드 (지가 조인 키)
    sido          TEXT NOT NULL,              -- 충북/경북/충남
    sigungu       TEXT,
    fmap_category TEXT,                       -- 팜맵 분류(과수원 등)
    area_m2       NUMERIC(12,2) NOT NULL,
    geom          geometry(MultiPolygon,4326) NOT NULL,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_parcel_geom ON parcel USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_parcel_bjd  ON parcel (bjd_cd);

-- ────────────────────────────────────────────────
-- 3. 지가 (ETL 적재: 공시지가 + 실거래 보정값)
--    법정동코드 + 지목 기준 집계. 실거래가는 CSV 적재본만 사용.
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS land_price (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bjd_cd            TEXT NOT NULL,
    jimok             TEXT NOT NULL,          -- 과수원/전/답
    official_price_m2 NUMERIC(14,2),          -- 개별공시지가 원/㎡
    deal_price_m2     NUMERIC(14,2),          -- 실거래 평균 원/㎡ (보정용)
    deal_sample_cnt   INTEGER DEFAULT 0,
    base_year         INTEGER NOT NULL,
    UNIQUE (bjd_cd, jimok, base_year)
);
CREATE INDEX IF NOT EXISTS idx_landprice_key ON land_price (bjd_cd, jimok);

-- ────────────────────────────────────────────────
-- 4. 작목별 소득계수 (ETL 적재: 농산물소득조사)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS income_coef (
    crop_code        crop_code_t PRIMARY KEY,
    avg_income_10a   NUMERIC(14,2) NOT NULL,  -- 10a당 평균 농업소득(원)
    avg_gross_10a    NUMERIC(14,2),           -- 10a당 조수입(참고)
    base_year        INTEGER NOT NULL,
    source_refs      TEXT NOT NULL
);

-- ────────────────────────────────────────────────
-- 5. 시세 보정 (ETL 적재: KAMIS, 작목별 최근 추세)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS price_trend (
    crop_code      crop_code_t PRIMARY KEY,
    trend_index    NUMERIC(5,3) NOT NULL DEFAULT 1.000, -- 평년=1.0
    volatility     NUMERIC(5,3),
    base_period    TEXT,
    source_refs    TEXT NOT NULL
);

-- ────────────────────────────────────────────────
-- 6. 농장 (경영주 등록 본체)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS farm (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id         BIGINT REFERENCES app_user(id),
    parcel_id        BIGINT REFERENCES parcel(id),
    address          TEXT NOT NULL,
    sido             TEXT NOT NULL,
    sigungu          TEXT,
    bjd_cd           TEXT,
    area_m2          NUMERIC(12,2) NOT NULL,
    crop_code        crop_code_t NOT NULL,
    tree_age         INTEGER,                 -- 수령(경영주 입력)
    planting_density TEXT,                    -- 재식밀도(사과 등, 선택)
    -- 판로(선택 입력)
    sales_channel    TEXT,                    -- 계약재배/직거래/공판장
    annual_revenue   NUMERIC(14,2),           -- 최근 매출(선택, 영업권 산정용)
    -- 승계 조건
    succession_type  succession_type_t,
    timing           timing_t,
    mentoring_months INTEGER DEFAULT 0,
    desired_price    NUMERIC(14,2),           -- 경영주 호가
    -- 평가 결과(엔진 산출 캐시)
    est_value_min    NUMERIC(14,2),
    est_value_max    NUMERIC(14,2),
    est_income_min   NUMERIC(14,2),
    est_income_max   NUMERIC(14,2),
    confidence_grade confidence_t DEFAULT 'D',
    -- 운영
    status           listing_status_t NOT NULL DEFAULT 'DRAFT',
    is_demo          BOOLEAN NOT NULL DEFAULT FALSE, -- 시드 농장 식별
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_farm_filter ON farm (status, sido, crop_code);

-- ────────────────────────────────────────────────
-- 7. 농장 자산(시설) — facility_std 참조
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS farm_asset (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    farm_id         BIGINT NOT NULL REFERENCES farm(id) ON DELETE CASCADE,
    facility_code   TEXT NOT NULL REFERENCES facility_std(facility_code),
    area_m2         NUMERIC(12,2) NOT NULL,
    installed_year  INTEGER,
    condition_grade CHAR(1) REFERENCES facility_condition(grade) DEFAULT 'B',
    residual_value  NUMERIC(14,2)            -- 엔진 산출 캐시
);
CREATE INDEX IF NOT EXISTS idx_asset_farm ON farm_asset (farm_id);

-- ────────────────────────────────────────────────
-- 8. 청년농 프로필
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS young_farmer_profile (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id             BIGINT REFERENCES app_user(id),
    pref_sido           TEXT,
    pref_crop           crop_code_t,
    available_capital   NUMERIC(14,2),
    experience_years    INTEGER DEFAULT 0,
    policy_fund         BOOLEAN DEFAULT FALSE,   -- 정책자금 신청 가능
    pref_succession     succession_type_t,
    risk_appetite       TEXT,                    -- LOW/MID/HIGH
    is_demo             BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ────────────────────────────────────────────────
-- 9. 매칭 점수 (엔진 산출, farm × young_farmer)
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS match_score (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    farm_id          BIGINT NOT NULL REFERENCES farm(id) ON DELETE CASCADE,
    young_farmer_id  BIGINT NOT NULL REFERENCES young_farmer_profile(id) ON DELETE CASCADE,
    total_score      NUMERIC(5,1) NOT NULL,
    region_score     NUMERIC(4,1),    -- /20
    crop_score       NUMERIC(4,1),    -- /20
    capital_score    NUMERIC(4,1),    -- /20
    experience_score NUMERIC(4,1),    -- /15
    succession_score NUMERIC(4,1),    -- /15
    policy_score     NUMERIC(4,1),    -- /10
    risk_penalty     NUMERIC(4,1) DEFAULT 0,
    explanation      TEXT,            -- 설명문(LLM 생성 가능)
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (farm_id, young_farmer_id)
);
CREATE INDEX IF NOT EXISTS idx_match_farm  ON match_score (farm_id, total_score DESC);
CREATE INDEX IF NOT EXISTS idx_match_young ON match_score (young_farmer_id, total_score DESC);

-- ────────────────────────────────────────────────
-- 10. 상담 신청 + 전문가 디렉터리
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS consult_request (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    farm_id          BIGINT NOT NULL REFERENCES farm(id),
    young_farmer_id  BIGINT NOT NULL REFERENCES young_farmer_profile(id),
    message          TEXT,
    status           TEXT NOT NULL DEFAULT 'REQUESTED', -- REQUESTED/ACCEPTED/DECLINED
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS expert_directory (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    expert_type   TEXT NOT NULL,    -- 공인중개사/법무사/농업기술센터/농어촌공사
    name          TEXT NOT NULL,
    sido          TEXT NOT NULL,
    sigungu       TEXT,
    phone         TEXT,
    address       TEXT,
    source_refs   TEXT              -- 부동산중개업소 공공데이터 등
);
CREATE INDEX IF NOT EXISTS idx_expert_region ON expert_directory (sido, sigungu, expert_type);

-- ────────────────────────────────────────────────
-- 11. 농장카드 결합 함수 (P1 졸업 시험)
--   주소→좌표는 앱(V-World)에서 처리 후 lon/lat 전달.
--   여기서는 좌표 기반 필지 공간조인 + 지가/계수 결합.
-- ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_farm_card(p_lon NUMERIC, p_lat NUMERIC, p_crop crop_code_t)
RETURNS TABLE (
    parcel_id        BIGINT,
    sido             TEXT,
    sigungu          TEXT,
    bjd_cd           TEXT,
    area_m2          NUMERIC,
    fmap_category    TEXT,
    official_price_m2 NUMERIC,
    deal_price_m2    NUMERIC,
    land_base_value  NUMERIC,        -- 토지 기준가(실거래 우선, 없으면 공시지가)
    income_10a       NUMERIC
) LANGUAGE sql STABLE AS $$
    SELECT
        p.id, p.sido, p.sigungu, p.bjd_cd, p.area_m2, p.fmap_category,
        lp.official_price_m2,
        lp.deal_price_m2,
        ROUND(p.area_m2 * COALESCE(lp.deal_price_m2, lp.official_price_m2)),
        ic.avg_income_10a
    FROM parcel p
    LEFT JOIN land_price lp
           ON lp.bjd_cd = p.bjd_cd AND lp.jimok = '과수원'
    LEFT JOIN income_coef ic
           ON ic.crop_code = p_crop
    WHERE ST_Contains(p.geom, ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326))
    ORDER BY p.area_m2 DESC
    LIMIT 1;
$$;

-- 검증:
-- SELECT * FROM fn_farm_card(127.926, 36.991, 'APPLE');  -- 충북 충주 인근 예시 좌표
