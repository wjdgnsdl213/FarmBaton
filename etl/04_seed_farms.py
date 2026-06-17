#!/usr/bin/env python
"""
etl/04_seed_farms.py
실존 필지 기반 데모 농장 3개 + 청년농 프로필 3개 삽입.

소유주는 가상 인물 (is_demo=True).  실제 농장명·주소는 필지 좌표 취득에만 사용.

사용법:
  python etl/04_seed_farms.py            # dry-run (지오코딩·필지 미리보기)
  python etl/04_seed_farms.py --load     # DB 삽입
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

import psycopg2
from dotenv import load_dotenv

load_dotenv(override=True)

DATABASE_URL = os.environ["DATABASE_URL"]
VWORLD_KEY = os.environ.get("VWORLD_API_KEY", "")

# ── 데모 농장 정의 ────────────────────────────────────────────────────────────
# 실존 필지 기반, 소유주는 가상 인물 (CLAUDE.md rule-6)
SEED_FARMS = [
    {
        "ref_address": "충청북도 충주시 가주동 483",  # 실주소 (지오코딩용)
        "sido": "충북",
        "crop_code": "APPLE",
        "tree_age": 12,
        "succession_type": "SALE",
        "timing": "WITHIN_1Y",
        "desired_price": 300_000_000,
        "area_m2_fallback": 5_000.0,
        "assets": [
            {"facility_code": "COLD_STORAGE_SMALL", "area_m2": 33.0,
             "installed_year": 2015, "condition_grade": "B"},
            {"facility_code": "TRELLIS_APPLE", "area_m2": 3_000.0,
             "installed_year": 2012, "condition_grade": "C"},
        ],
        # 가상 인물
        "owner_name": "홍길동",
        "owner_phone": "010-0000-0001",
    },
    {
        "ref_address": "경상북도 청도군 화양읍 청려로 1723",
        "sido": "경북",
        "crop_code": "PEACH",
        "tree_age": 8,
        "succession_type": "LEASE",
        "timing": "WITHIN_3Y",
        "desired_price": None,
        "area_m2_fallback": 4_000.0,
        "assets": [
            {"facility_code": "VINYL_HOUSE_SINGLE", "area_m2": 500.0,
             "installed_year": 2018, "condition_grade": "B"},
            {"facility_code": "IRRIGATION_DRIP_AUTO", "area_m2": 4_000.0,
             "installed_year": 2018, "condition_grade": "A"},
        ],
        "owner_name": "이순신",
        "owner_phone": "010-0000-0002",
    },
    {
        "ref_address": "충청남도 천안시 서북구 입장면 신덕리 95-2",
        "sido": "충남",
        "crop_code": "GRAPE",
        "tree_age": 10,
        "succession_type": "JOINT",
        "timing": "WITHIN_3Y",
        "desired_price": None,
        "area_m2_fallback": 3_500.0,
        "assets": [
            {"facility_code": "RAIN_SHELTER", "area_m2": 2_000.0,
             "installed_year": 2016, "condition_grade": "B"},
            {"facility_code": "TRELLIS_GRAPE", "area_m2": 2_000.0,
             "installed_year": 2016, "condition_grade": "B"},
        ],
        "owner_name": "박영희",
        "owner_phone": "010-0000-0003",
    },
]

SEED_YOUNG_FARMERS = [
    {
        "name": "김청년",
        "pref_sido": "충북",
        "pref_crop": "APPLE",
        "available_capital": 150_000_000,
        "experience_years": 3,
        "policy_fund": True,
        "pref_succession": "SALE",
    },
    {
        "name": "이새벽",
        "pref_sido": "경북",
        "pref_crop": "PEACH",
        "available_capital": 80_000_000,
        "experience_years": 1,
        "policy_fund": True,
        "pref_succession": "LEASE",
    },
    {
        "name": "박도전",
        "pref_sido": "충남",
        "pref_crop": "GRAPE",
        "available_capital": 120_000_000,
        "experience_years": 5,
        "policy_fund": False,
        "pref_succession": "JOINT",
    },
]


# ── V-World 지오코딩 ──────────────────────────────────────────────────────────

def _vworld_req(address: str, addr_type: str) -> tuple[float, float] | None:
    params = urllib.parse.urlencode({
        "service": "address",
        "request": "getcoord",
        "crs": "EPSG:4326",
        "address": address,
        "type": addr_type,
        "key": VWORLD_KEY,
        "format": "json",
        "simple": "false",
    })
    with urllib.request.urlopen(
        f"https://api.vworld.kr/req/address?{params}", timeout=10
    ) as resp:
        data = json.loads(resp.read())
    if data["response"]["status"] == "OK":
        pt = data["response"]["result"]["point"]
        return float(pt["x"]), float(pt["y"])
    return None


def geocode(address: str) -> tuple[float, float] | None:
    """주소 -> (lon, lat) WGS84.

    PARCEL(지번) 우선, 실패 시 ROAD(도로명) 재시도.
    """
    if not VWORLD_KEY:
        print("  [WARN] VWORLD_API_KEY 없음 - 지오코딩 건너뜀", file=sys.stderr)
        return None
    for addr_type in ("PARCEL", "ROAD"):
        try:
            coord = _vworld_req(address, addr_type)
            if coord:
                return coord
        except Exception as exc:
            print(f"  [WARN] V-World ({addr_type}) 오류: {exc}", file=sys.stderr)
    print("  [WARN] 지오코딩 실패 (PARCEL+ROAD 모두 불가)", file=sys.stderr)
    return None


# ── 필지 KNN 탐색 ─────────────────────────────────────────────────────────────

def find_parcel(cur, lon: float, lat: float, crop_code: str, sido: str):
    """fn_farm_card → KNN 폴백 순으로 필지 취득.

    Returns (parcel_id, sido, sigungu, bjd_cd, area_m2) or None.
    """
    # 1차: ST_Contains
    cur.execute(
        "SELECT parcel_id, sido, sigungu, bjd_cd, area_m2 "
        "FROM fn_farm_card(%s, %s, %s::crop_code_t)",
        (lon, lat, crop_code),
    )
    row = cur.fetchone()
    if row:
        return row

    # 2차: KNN (같은 시도 우선 + 전체)
    cur.execute("""
        SELECT p.id, p.sido, p.sigungu, p.bjd_cd, p.area_m2
        FROM parcel p
        WHERE p.sido = %s
        ORDER BY p.geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
        LIMIT 1
    """, (sido, lon, lat))
    row = cur.fetchone()
    return row


# ── 가치평가 캐시 ─────────────────────────────────────────────────────────────

def compute_and_cache(farm_id: int, cur):
    """valuation 계산 후 farm 행 캐시 업데이트."""
    # Python 경로가 설정된 상태에서 import
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from backend.app.services.db_loader import load_farm_input
    from backend.app.services.valuation import calc_total_value
    import datetime

    conn = cur.connection
    try:
        farm_input = load_farm_input(farm_id, conn)
        result = calc_total_value(farm_input, datetime.date.today().year)
        cur.execute("""
            UPDATE farm
            SET est_value_min    = %s,
                est_value_max    = %s,
                est_income_min   = %s,
                est_income_max   = %s,
                confidence_grade = %s::confidence_t
            WHERE id = %s
        """, (
            result.est_value_min,
            result.est_value_max,
            result.est_income_min,
            result.est_income_max,
            result.confidence_grade,
            farm_id,
        ))
        return result
    except Exception as exc:
        print(f"  [WARN] 가치평가 실패: {exc}", file=sys.stderr)
        return None


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main(load: bool):
    conn = psycopg2.connect(DATABASE_URL)

    print("=" * 60)
    print("팜바톤 시드 데이터 삽입")
    print("=" * 60)

    results = []

    with conn.cursor() as cur:
        for i, farm_def in enumerate(SEED_FARMS, 1):
            print(f"\n[{i}/3] {farm_def['ref_address']}")

            # ── 지오코딩 ────────────────────────────────────────────────
            coord = geocode(farm_def["ref_address"])
            if coord:
                lon, lat = coord
                print(f"  좌표: lon={lon:.6f}, lat={lat:.6f}")
            else:
                print("  [WARN] 지오코딩 실패 - 필지 검색 불가, 폴백 면적 사용")
                lon = lat = None

            # ── 필지 탐색 ───────────────────────────────────────────────
            parcel_id = bjd_cd = sigungu = None
            area_m2 = farm_def["area_m2_fallback"]
            sido = farm_def["sido"]

            if lon is not None:
                row = find_parcel(cur, lon, lat, farm_def["crop_code"], sido)
                if row:
                    parcel_id, sido, sigungu, bjd_cd, area_m2 = row
                    area_m2 = float(area_m2)
                    print(f"  필지: id={parcel_id}, {sido} {sigungu}, bjd_cd={bjd_cd}, {area_m2:.0f}㎡")
                else:
                    print(f"  [WARN] 필지 미발견 — 폴백 면적 {area_m2:.0f}㎡ 사용")

            results.append({
                "def": farm_def,
                "lon": lon, "lat": lat,
                "parcel_id": parcel_id,
                "bjd_cd": bjd_cd,
                "sigungu": sigungu,
                "sido": sido,
                "area_m2": area_m2,
            })

    if not load:
        print("\n[dry-run] --load 플래그 없음. DB 삽입 건너뜀.")
        conn.close()
        return

    # ── DB 삽입 ──────────────────────────────────────────────────────────
    print("\n-- DB 삽입 시작 --")
    farm_ids = []

    with conn.cursor() as cur:
        # 기존 데모 데이터 삭제 (재실행 안전)
        cur.execute("""
            DELETE FROM app_user
            WHERE name IN %s AND is_demo = TRUE
        """, (tuple(f["def"]["owner_name"] for f in results),))
        cur.execute("""
            DELETE FROM app_user
            WHERE name IN %s AND is_demo = TRUE
        """, (tuple(y["name"] for y in SEED_YOUNG_FARMERS),))

        # ── 농장주(가상 인물) + 농장 삽입 ────────────────────────────
        for r in results:
            fd = r["def"]

            cur.execute("""
                INSERT INTO app_user (role, name, phone, is_demo)
                VALUES ('FARMER', %s, %s, TRUE)
                RETURNING id
            """, (fd["owner_name"], fd["owner_phone"]))
            owner_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO farm (
                    owner_id, parcel_id, address, sido, sigungu, bjd_cd,
                    area_m2, crop_code, tree_age,
                    succession_type, timing, desired_price,
                    status, is_demo
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    'ACTIVE', TRUE
                ) RETURNING id
            """, (
                owner_id, r["parcel_id"], fd["ref_address"],
                r["sido"], r["sigungu"], r["bjd_cd"],
                r["area_m2"], fd["crop_code"], fd["tree_age"],
                fd["succession_type"], fd["timing"], fd.get("desired_price"),
            ))
            farm_id = cur.fetchone()[0]
            farm_ids.append(farm_id)

            for a in fd["assets"]:
                cur.execute("""
                    INSERT INTO farm_asset
                        (farm_id, facility_code, area_m2, installed_year, condition_grade)
                    VALUES (%s, %s, %s, %s, %s)
                """, (farm_id, a["facility_code"], a["area_m2"],
                      a.get("installed_year"), a["condition_grade"]))

            print(f"  farm_id={farm_id} ({fd['crop_code']}, {r['sido']}) 삽입 완료")

        # ── 청년농 프로필 삽입 ────────────────────────────────────────
        young_ids = []
        for y in SEED_YOUNG_FARMERS:
            cur.execute("""
                INSERT INTO app_user (role, name, is_demo)
                VALUES ('YOUNG', %s, TRUE)
                RETURNING id
            """, (y["name"],))
            user_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO young_farmer_profile (
                    user_id, pref_sido, pref_crop,
                    available_capital, experience_years,
                    policy_fund, pref_succession, is_demo
                ) VALUES (%s, %s, %s::crop_code_t, %s, %s, %s, %s::succession_type_t, TRUE)
                RETURNING id
            """, (
                user_id, y["pref_sido"], y["pref_crop"],
                y["available_capital"], y["experience_years"],
                y["policy_fund"], y["pref_succession"],
            ))
            yf_id = cur.fetchone()[0]
            young_ids.append(yf_id)
            print(f"  young_farmer_id={yf_id} ({y['name']}, {y['pref_crop']}) 삽입 완료")

        conn.commit()

        # ── 가치평가 캐시 ──────────────────────────────────────────────
        print("\n-- 가치평가 산출 --")
        for farm_id, r in zip(farm_ids, results):
            result = compute_and_cache(farm_id, cur)
            conn.commit()
            if result:
                print(
                    f"  farm_id={farm_id}: "
                    f"인수검토가 {result.est_value_min/1e8:.2f}억~{result.est_value_max/1e8:.2f}억원 "
                    f"(등급 {result.confidence_grade})"
                )

    conn.close()
    print("\n완료.")
    print(f"농장 farm_id: {farm_ids}")
    print(f"청년농 young_farmer_id: {young_ids}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--load", action="store_true", help="DB에 실제 삽입")
    args = parser.parse_args()
    main(load=args.load)
