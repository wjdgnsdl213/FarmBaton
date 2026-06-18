"""팜바톤 FastAPI 앱 진입점."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(override=True)  # .env 우선 (외부 환경변수 따옴표 오염 방지)

import json
import os
import urllib.parse
import urllib.request

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db import get_db
from backend.app.routers import farms, young_farmers
from backend.app.routers.farms import KNN_DISTANCE_WARN_KM

app = FastAPI(
    title="팜바톤 API",
    description="고령 농가 승계 진단·매칭 플랫폼",
    version="0.1.0",
)

_default_origins = ["http://localhost:5173", "http://localhost:3000"]
_extra = os.getenv("ALLOWED_ORIGINS", "")  # 콤마 구분, 예: https://farmbaton.vercel.app
_origins = _default_origins + [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(farms.router)
app.include_router(young_farmers.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/geocode")
def geocode(address: str, crop_code: str = "APPLE", conn=Depends(get_db)):
    """주소 → 좌표 + 필지 면적 자동 취득.

    1. V-World 지오코딩 (PARCEL → ROAD 재시도)
    2. fn_farm_card → KNN 폴백으로 가장 가까운 과수원 필지 면적 취득
    반환: {lon, lat, area_m2?, sido?, sigungu?}
    """
    key = os.getenv("VWORLD_API_KEY", "")
    if not key:
        raise HTTPException(503, "VWORLD_API_KEY not configured")

    # ── 1. 지오코딩 ──────────────────────────────────────────────────
    lon = lat = None
    for addr_type in ("PARCEL", "ROAD"):
        params = urllib.parse.urlencode({
            "service": "address", "request": "getcoord",
            "crs": "EPSG:4326", "address": address,
            "type": addr_type, "key": key,
            "format": "json", "simple": "false",
        })
        try:
            with urllib.request.urlopen(
                f"https://api.vworld.kr/req/address?{params}", timeout=8
            ) as resp:
                data = json.loads(resp.read())
            if data["response"]["status"] == "OK":
                pt = data["response"]["result"]["point"]
                lon, lat = float(pt["x"]), float(pt["y"])
                break
        except Exception:
            continue

    if lon is None:
        raise HTTPException(404, "주소를 찾을 수 없습니다.")

    result: dict = {"lon": lon, "lat": lat}

    # ── 2. 필지 KNN 탐색 → 면적 자동 취득 ───────────────────────────
    try:
        with conn.cursor() as cur:
            # fn_farm_card (ST_Contains) 우선 시도 — 정확 포함이라 거리 경고 불필요
            cur.execute(
                "SELECT parcel_id, sido, sigungu, bjd_cd, area_m2 "
                "FROM fn_farm_card(%s, %s, %s::crop_code_t)",
                (lon, lat, crop_code),
            )
            row = cur.fetchone()
            dist_km = None

            if not row:
                # KNN 폴백 — 같은 시도로 스코프를 좁혀 오매칭 방지
                sido_hint = _extract_sido_from_address(address)
                if sido_hint:
                    cur.execute("""
                        SELECT p.id, p.sido, p.sigungu, p.bjd_cd, p.area_m2,
                               ST_Distance(
                                   p.geom::geography,
                                   ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography
                               ) / 1000.0 AS dist_km
                        FROM parcel p WHERE p.sido = %s
                        ORDER BY p.geom <-> ST_SetSRID(ST_MakePoint(%s,%s),4326)
                        LIMIT 1
                    """, (lon, lat, sido_hint, lon, lat))
                    row = cur.fetchone()
                if not row:
                    # 최후 폴백: 전역 KNN (시도 추정조차 안 된 경우)
                    cur.execute("""
                        SELECT p.id, p.sido, p.sigungu, p.bjd_cd, p.area_m2,
                               ST_Distance(
                                   p.geom::geography,
                                   ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography
                               ) / 1000.0 AS dist_km
                        FROM parcel p
                        ORDER BY p.geom <-> ST_SetSRID(ST_MakePoint(%s,%s),4326)
                        LIMIT 1
                    """, (lon, lat, lon, lat))
                    row = cur.fetchone()
                if row:
                    dist_km = row[5]

        if row:
            sido, sigungu, area_m2 = row[1], row[2], row[4]
            result["area_m2"] = float(area_m2)
            result["sido"] = sido or ""
            result["sigungu"] = sigungu or ""
            if dist_km is not None and dist_km > KNN_DISTANCE_WARN_KM:
                result["warning"] = (
                    f"입력 좌표와 가장 가까운 과수원 필지가 {dist_km:.1f}km 떨어져 있습니다. "
                    "면적·지가가 실제 필지와 다를 수 있습니다."
                )
    except Exception:
        conn.rollback()  # 필지 취득 실패해도 좌표는 반환

    return result


def _extract_sido_from_address(address: str) -> str | None:
    mapping = {"충북": "충북", "충청북도": "충북",
                "경북": "경북", "경상북도": "경북",
                "충남": "충남", "충청남도": "충남"}
    for k, v in mapping.items():
        if k in address:
            return v
    return None
