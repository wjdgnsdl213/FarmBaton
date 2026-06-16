-- ============================================================
-- 001_reference_tables.sql
-- 팜바톤 기준 테이블 최종 합본 (Supabase / PostgreSQL)
-- 작성: 2026-06-12
--
-- [합본 원칙]
--  · 뼈대: RDA 경제성 분석 기준자료집 + 지자체 고시 단가 앵커링 버전
--  · 보강 1: 과수 전용 시설 3종(비가림·덕·지주) 추가 — confidence LOW,
--    지자체 단가 확인 시 갱신
--  · 보강 2: 창고를 구조별 2행으로 분리 — 부동산원 평균(RC 포함)의
--    과대평가 위험 차단, 위저드에서 구조 선택 입력
--  · 보강 3: 복숭아 유목기 램프 자체 보정(3/3 → 3/5) — RDA 표의
--    "2년생 0 → 3년생 1.0" 절벽 제거
--  · 보강 4: post_life_coeff 추가 — 내용연수 초과 과수원의 가치가
--    0으로 떨어지는 비현실 방지 (갱신 권장 라벨과 함께 0.35 적용)
--
-- [제출 전 검증 TODO]
--  [ ] RDA 2025 경제성 분석 기준자료집 원문에서 대식물 내용연수 표 대조
--  [ ] 부동산원 건물신축단가표에서 경량철골 창고 값 확인 → PANEL 행 갱신
--  [ ] 비가림·덕·지주: AgriX 과수고품질시설현대화 또는 지자체 고시 단가 확인
-- ============================================================

-- ────────────────────────────────────────────────
-- 0. 출처 레지스트리
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS source_ref (
    ref_code   TEXT PRIMARY KEY,
    ref_desc   TEXT NOT NULL
);

INSERT INTO source_ref VALUES
('SRC_RDA_DIAG_2024',            '농사로 농업경영 표준진단표(122종), 2024-06 게시'),
('SRC_RDA_ECON_2025',            '농사로 2025 농업과학기술 경제성 분석 기준자료집 (시설 내용연수, 대식물 결과·성목수령·내용연수)'),
('SRC_AGRIX_FRUIT_MODERNIZATION','AgriX 과수고품질시설현대화 지침 (실단가 검토 원칙, 비가림·관수관비 지원항목)'),
('SRC_GUNSAN_2026_VINYL',        '군산시 2026 지역특화품목 비닐하우스 지원: 단동 33,000원/㎡, 연동 130,000원/㎡'),
('SRC_GIMCHEON_2026_COLD',       '김천시 2026 농가형 저온저장고 지원: 2,800천원/평'),
('SRC_REB_2025_WAREHOUSE',       '한국부동산원 건물신축단가표, 2025 창고 용도 평균 860,857원/㎡'),
('SRC_JEJU_2025_IRRIGATION',     '제주 2025 시설현대화: 관수시설 기계부+라인부 단가표'),
('SRC_MARKET_EST_2026',          '자체 시장 시공가 조사 기반 추정치 (2026-06, 공적 단가 확인 시 대체)')
ON CONFLICT (ref_code) DO NOTHING;

-- ────────────────────────────────────────────────
-- 1. 시설 표준단가 facility_std
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facility_std (
    facility_code          TEXT PRIMARY KEY,
    facility_name          TEXT NOT NULL,
    facility_variant       TEXT NOT NULL,
    cost_model             TEXT NOT NULL,           -- 계산식 설명용
    base_cost_krw          NUMERIC(14,2) NOT NULL DEFAULT 0,  -- 개소당 고정비
    unit_cost_krw          NUMERIC(14,2) NOT NULL,            -- 단위당 단가
    cost_unit              TEXT NOT NULL,           -- KRW_PER_M2 | KRW_PER_PYEONG
    useful_life_years      NUMERIC(5,1) NOT NULL,
    salvage_rate           NUMERIC(3,2) NOT NULL DEFAULT 0.05,
    standard_year          INTEGER NOT NULL,
    confidence             TEXT NOT NULL,           -- HIGH | MEDIUM | LOW
    source_refs            TEXT NOT NULL,
    notes                  TEXT
);

INSERT INTO facility_std
(facility_code, facility_name, facility_variant, cost_model, base_cost_krw,
 unit_cost_krw, cost_unit, useful_life_years, salvage_rate, standard_year,
 confidence, source_refs, notes) VALUES
('VINYL_HOUSE_SINGLE', '비닐하우스', '내재해형 단동 기본형',
 'area_m2 * unit', 0, 33000, 'KRW_PER_M2', 10, 0.05, 2026,
 'HIGH', 'SRC_GUNSAN_2026_VINYL;SRC_RDA_ECON_2025',
 '관수·자동개폐기 포함 신축 지원 기준'),

('VINYL_HOUSE_MULTI', '비닐하우스', '연동',
 'area_m2 * unit', 0, 130000, 'KRW_PER_M2', 15, 0.05, 2026,
 'HIGH', 'SRC_GUNSAN_2026_VINYL;SRC_RDA_ECON_2025',
 '군산시 연동 기준단가'),

('COLD_STORAGE_SMALL', '저온저장고', '농가형',
 'area_pyeong * unit', 0, 2800000, 'KRW_PER_PYEONG', 10, 0.10, 2026,
 'MEDIUM', 'SRC_GIMCHEON_2026_COLD',
 '약 846,807원/㎡ 상당. 정밀평가 시 건물/냉동설비 분리 권장'),

('FARM_WAREHOUSE_PANEL', '창고', '판넬·경량철골 (농가 일반)',
 'area_m2 * unit', 0, 350000, 'KRW_PER_M2', 20, 0.10, 2026,
 'LOW', 'SRC_MARKET_EST_2026;SRC_RDA_ECON_2025',
 '농가 창고 기본값. 부동산원 경량철골 값 확인 후 갱신할 것'),

('FARM_WAREHOUSE_GENERAL', '창고', '일반 구조 평균 (RC 포함)',
 'area_m2 * unit', 0, 860857, 'KRW_PER_M2', 20, 0.10, 2025,
 'MEDIUM', 'SRC_REB_2025_WAREHOUSE',
 '부동산원 창고 용도 평균. RC 포함 평균이라 판넬 창고에 적용 시 과대평가 — 위저드에서 구조 미상일 때만 사용'),

('IRRIGATION_DRIP_AUTO', '관수시설', '하우스 자동 점적관수',
 'base + area_m2 * unit', 4297000, 830.2, 'KRW_PER_M2', 8, 0.00, 2025,
 'HIGH', 'SRC_JEJU_2025_IRRIGATION;SRC_RDA_ECON_2025',
 '수동 점적: 1,337,520 + 810.2/㎡, 자동 관수관비: 6,909,000 + 1,026.2/㎡'),

('RAIN_SHELTER', '비가림 시설', '과수 비가림 (포도 등)',
 'area_m2 * unit', 0, 25000, 'KRW_PER_M2', 10, 0.05, 2026,
 'LOW', 'SRC_MARKET_EST_2026;SRC_AGRIX_FRUIT_MODERNIZATION',
 'AgriX 지원항목 존재. 지자체 고시 단가 확인 시 갱신'),

('TRELLIS_GRAPE', '덕 시설', '포도 평덕',
 'area_m2 * unit', 0, 4000, 'KRW_PER_M2', 15, 0.05, 2026,
 'LOW', 'SRC_MARKET_EST_2026',
 '10a당 약 300~500만원 환산'),

('TRELLIS_APPLE', '지주 시설', '사과 밀식 지주·와이어',
 'area_m2 * unit', 0, 2000, 'KRW_PER_M2', 15, 0.05, 2026,
 'LOW', 'SRC_MARKET_EST_2026',
 '10a당 약 150~250만원 환산')
ON CONFLICT (facility_code) DO NOTHING;

-- 시설 상태등급 보정 (위저드 입력: 상/중/하)
CREATE TABLE IF NOT EXISTS facility_condition (
    grade       CHAR(1) PRIMARY KEY,    -- A=상, B=중, C=하
    multiplier  NUMERIC(3,2) NOT NULL
);
INSERT INTO facility_condition VALUES ('A',1.00),('B',0.85),('C',0.60)
ON CONFLICT (grade) DO NOTHING;

-- 신축비 계산 함수 (㎡ 입력 통일, 평 단가는 내부 환산)
CREATE OR REPLACE FUNCTION fn_facility_new_cost(p_code TEXT, p_area_m2 NUMERIC)
RETURNS NUMERIC LANGUAGE sql STABLE AS $$
    SELECT ROUND(
        f.base_cost_krw
        + CASE f.cost_unit
            WHEN 'KRW_PER_M2'     THEN p_area_m2 * f.unit_cost_krw
            WHEN 'KRW_PER_PYEONG' THEN (p_area_m2 / 3.3058) * f.unit_cost_krw
          END)
    FROM facility_std f WHERE f.facility_code = p_code;
$$;

-- 잔존가 = fn_facility_new_cost(code, area)
--          × GREATEST(salvage_rate, 1 - 경과연수/내용연수)
--          × facility_condition.multiplier
-- (애플리케이션 valuation.py에서 조합)

-- ────────────────────────────────────────────────
-- 2. 과수 수령 곡선 orchard_age_curve_std
-- ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orchard_age_curve_std (
    crop_code           TEXT PRIMARY KEY,
    crop_name           TEXT NOT NULL,
    rda_basis           TEXT NOT NULL,
    fruiting_age_year   INTEGER NOT NULL,
    mature_age_year     INTEGER NOT NULL,
    economic_life_year  INTEGER NOT NULL,
    old_start_age_year  INTEGER NOT NULL,   -- floor(economic_life*0.75)+1
    young_start_coeff   NUMERIC(4,2),
    young_gamma         NUMERIC(4,2),
    mature_coeff        NUMERIC(4,2) NOT NULL DEFAULT 1.00,
    old_end_coeff       NUMERIC(4,2) NOT NULL DEFAULT 0.60,
    old_gamma           NUMERIC(4,2) NOT NULL DEFAULT 1.20,
    post_life_coeff     NUMERIC(4,2) NOT NULL DEFAULT 0.35, -- 내용연수 초과(갱신 권장)
    curve_version       TEXT NOT NULL,
    source_refs         TEXT NOT NULL,
    notes               TEXT
);

INSERT INTO orchard_age_curve_std
(crop_code, crop_name, rda_basis, fruiting_age_year, mature_age_year,
 economic_life_year, old_start_age_year, young_start_coeff, young_gamma,
 mature_coeff, old_end_coeff, old_gamma, post_life_coeff,
 curve_version, source_refs, notes) VALUES
('APPLE', '사과', 'RDA 반밀식 50~99주/10a',
 3, 6, 16, 13, 0.35, 1.20, 1.00, 0.60, 1.20, 0.35,
 'v2_merged_2026', 'SRC_RDA_ECON_2025',
 'RDA 표는 소식/반밀식/밀식/초밀식 구분. 기본값 반밀식, 재식밀도 입력 받으면 행 확장'),

('PEACH', '복숭아', 'RDA 기본 + 자체 램프 보정',
 3, 5, 24, 19, 0.50, 1.20, 1.00, 0.60, 1.20, 0.35,
 'v2_merged_2026', 'SRC_RDA_ECON_2025;SRC_MARKET_EST_2026',
 'RDA 원표는 결실=성목=3년이나 절벽 방지 위해 성목 5년 램프로 자체 보정. 발표 시 보정 사실 명시'),

('GRAPE', '포도', 'RDA 기본',
 3, 7, 18, 14, 0.35, 1.20, 1.00, 0.60, 1.20, 0.35,
 'v2_merged_2026', 'SRC_RDA_ECON_2025',
 '노지/시설·품종(샤인머스캣 등) 세분화 필요 시 행 확장')
ON CONFLICT (crop_code) DO NOTHING;

-- 곡선 함수 (계산의 단일 진실 원천)
CREATE OR REPLACE FUNCTION fn_orchard_age_coef(p_crop TEXT, p_age INTEGER)
RETURNS NUMERIC LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN p_age < c.fruiting_age_year THEN 0.00
        WHEN p_age < c.mature_age_year THEN ROUND(
            c.young_start_coeff + (1 - c.young_start_coeff)
            * POWER((p_age - c.fruiting_age_year)::numeric
                    / (c.mature_age_year - c.fruiting_age_year), c.young_gamma), 2)
        WHEN p_age < c.old_start_age_year THEN c.mature_coeff
        WHEN p_age <= c.economic_life_year THEN ROUND(
            1 - (1 - c.old_end_coeff)
            * POWER((p_age - c.old_start_age_year)::numeric
                    / (c.economic_life_year - c.old_start_age_year), c.old_gamma), 2)
        ELSE c.post_life_coeff
    END
    FROM orchard_age_curve_std c
    WHERE c.crop_code = p_crop;
$$;

-- 구간표 뷰 (UI·발표용: "5년생 사과 = 0.71" 형태로 노출)
CREATE OR REPLACE VIEW v_orchard_age_band AS
SELECT c.crop_code,
       c.crop_name,
       s.age,
       fn_orchard_age_coef(c.crop_code, s.age) AS yield_coef
FROM orchard_age_curve_std c
CROSS JOIN LATERAL generate_series(0, c.economic_life_year + 10) AS s(age);

-- 검증 쿼리 예시:
-- SELECT * FROM v_orchard_age_band WHERE crop_code='APPLE' ORDER BY age;
-- SELECT fn_facility_new_cost('COLD_STORAGE_SMALL', 33);  -- 10평 저온저장고
