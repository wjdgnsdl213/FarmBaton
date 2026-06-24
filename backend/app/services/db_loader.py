"""
DB-aware 팜 데이터 로더.
Supabase(psycopg2 connection)를 조회해 valuation.py의 FarmInput을 반환한다.
수치 계산 없음 — 계수·단가 조회만 담당.
"""
from __future__ import annotations

from backend.app.services.valuation import AssetData, FarmInput, LandData

# bjd_cd 첫 2자리 → 시도 (etl/02_landprice.py의 PROVINCE_BY_PREFIX와 동일 매핑)
_SIDO_TO_BJD_PREFIX = {"충북": "43", "충남": "44", "경북": "47"}


def load_farm_input(farm_id: int, conn) -> FarmInput:
    """farm_id 기반 DB 조회 → FarmInput 반환.

    Raises:
        ValueError: farm row 미존재
    """
    with conn.cursor() as cur:
        # ── 1. 농장 기본 행 ──────────────────────────────────────────
        cur.execute("""
            SELECT crop_code::TEXT, tree_age, area_m2, bjd_cd, sido,
                   annual_revenue, sales_channel
            FROM farm
            WHERE id = %s
        """, (farm_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"farm id={farm_id} not found")
        crop_code, tree_age, area_m2, bjd_cd, sido, annual_revenue, sales_channel = row

        # ── 2. 10a당 소득 ─────────────────────────────────────────────
        cur.execute(
            "SELECT avg_income_10a FROM income_coef WHERE crop_code = %s",
            (crop_code,),
        )
        ic = cur.fetchone()
        income_10a = float(ic[0]) if ic else 0.0

        # ── 3. 수령계수 (DB 곡선 함수) ──────────────────────────────
        cur.execute(
            "SELECT fn_orchard_age_coef(%s, %s)",
            (crop_code, int(tree_age or 0)),
        )
        ac = cur.fetchone()
        age_coef = float(ac[0]) if (ac and ac[0] is not None) else 0.0

        # ── 4. 시세 보정 (price_trend, 없으면 1.0 폴백) ──────────────
        cur.execute(
            "SELECT trend_index FROM price_trend WHERE crop_code = %s",
            (crop_code,),
        )
        pt = cur.fetchone()
        trend_index = float(pt[0]) if pt else 1.0

        # ── 5. 토지 지가 ──────────────────────────────────────────────
        land = _load_land(cur, bjd_cd, float(area_m2), sido)

        # ── 6. 시설 자산 ──────────────────────────────────────────────
        assets = _load_assets(cur, farm_id)

        # ── 7. 판로·영업권 파생 ───────────────────────────────────────
        revenue_years = 1 if annual_revenue is not None else 0
        has_contract = (sales_channel == "계약재배") if sales_channel else False
        has_direct_sales = (sales_channel == "직거래") if sales_channel else False

        return FarmInput(
            crop_code=crop_code,
            tree_age=int(tree_age or 0),
            area_m2=float(area_m2),
            income_10a=income_10a,
            age_coef=age_coef,
            trend_index=trend_index,
            land=land,
            assets=assets,
            annual_revenue=float(annual_revenue) if annual_revenue is not None else None,
            revenue_years=revenue_years,
            has_contract=has_contract,
            has_direct_sales=has_direct_sales,
        )


def load_normal_year_price(crop_code: str, conn) -> tuple[float | None, str | None, str | None]:
    """price_trend.normal_year_price 조회 (PDF 참고용 — 가치평가 계산엔 쓰지 않음).

    KAMIS 평년가(5개년 중 최고·최저 제외 3개년 평균)가 없는 작목(예: GRAPE,
    변동성 과다로 KAMIS 자체가 평년값을 산출 못함)은 (None, unit, source)를
    반환한다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT normal_year_price, price_unit, normal_year_source "
            "FROM price_trend WHERE crop_code = %s",
            (crop_code,),
        )
        row = cur.fetchone()
    if row is None:
        return None, None, None
    price, unit, source = row
    return (float(price) if price is not None else None), unit, source


def _load_land(cur, bjd_cd: str | None, area_m2: float, sido: str | None = None) -> LandData:
    """동(8자리 bjd_cd) 단위 지가 조회. 좌표 미확보 시 시도 단위 평균으로 폴백.

    bjd_cd가 없으면(위치검색 미사용/V-World 장애로 면적만 수동 입력한 경로)
    official_price_m2=0이 되어 인수 검토가가 0원으로 표시되는 문제가 있었음.
    실거래/공시지가 모두 실데이터이므로, 시도 단위로 넓혀서라도 0보다는
    의미 있는 근사값을 반환한다. deal_price_m2를 None으로 남겨 두면
    grade_confidence()가 자동으로 신뢰도를 한 단계 낮춘다.
    """
    if bjd_cd:
        cur.execute("""
            SELECT
                AVG(official_price_m2),
                AVG(CASE WHEN deal_price_m2 IS NOT NULL THEN deal_price_m2 END),
                COALESCE(SUM(deal_sample_cnt), 0)::INTEGER
            FROM land_price
            WHERE LEFT(bjd_cd, 8) = %s
              AND jimok = '과수원'
        """, (bjd_cd,))
        row = cur.fetchone()

        if row and row[0] is not None:
            return LandData(
                area_m2=area_m2,
                official_price_m2=float(row[0]),
                deal_price_m2=float(row[1]) if row[1] is not None else None,
                deal_sample_cnt=int(row[2]) if row[2] else 0,
            )

    # 폴백: 시도 단위 평균 (bjd_cd 미확보 또는 동 단위 데이터 없음)
    bjd_prefix = _SIDO_TO_BJD_PREFIX.get(sido or "")
    if bjd_prefix:
        cur.execute("""
            SELECT AVG(official_price_m2)
            FROM land_price
            WHERE LEFT(bjd_cd, 2) = %s
              AND jimok = '과수원'
        """, (bjd_prefix,))
        row = cur.fetchone()
        if row and row[0] is not None:
            return LandData(area_m2=area_m2, official_price_m2=float(row[0]))

    return LandData(area_m2=area_m2, official_price_m2=0.0)


def _load_assets(cur, farm_id: int) -> list[AssetData]:
    cur.execute("""
        SELECT
            fa.facility_code,
            fa.area_m2,
            fa.installed_year,
            COALESCE(fa.condition_grade, 'B') AS condition_grade,
            fn_facility_new_cost(fa.facility_code, fa.area_m2) AS new_cost,
            fs.useful_life_years,
            fs.salvage_rate
        FROM farm_asset fa
        JOIN facility_std fs ON fs.facility_code = fa.facility_code
        WHERE fa.farm_id = %s
    """, (farm_id,))

    assets = []
    for row in cur.fetchall():
        code, area_m2, installed_year, condition_grade, new_cost, useful_life, salvage_rate = row
        area_f = float(area_m2)
        nc = float(new_cost) if new_cost is not None else 0.0
        # effective per-m2 단가 = fn_facility_new_cost / area_m2
        std_unit = nc / area_f if area_f > 0 else 0.0
        assets.append(AssetData(
            facility_code=code,
            area_m2=area_f,
            installed_year=installed_year,
            condition_grade=condition_grade,
            std_unit_cost_krw=std_unit,
            useful_life_years=int(useful_life),
            salvage_rate=float(salvage_rate),
        ))
    return assets
