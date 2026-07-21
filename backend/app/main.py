"""팜바톤 FastAPI 앱 진입점."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(override=True)  # .env 우선 (외부 환경변수 따옴표 오염 방지)

import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db import get_db
from backend.app.routers import auth, chat, farms, young_farmers
from backend.app.routers.farms import KNN_CONFIDENT_KM

_GEOCODE_FALLBACK_PATH = Path(__file__).resolve().parents[2] / "db" / "seed" / "geocode_fallback.csv"


def _load_geocode_fallback() -> dict[str, tuple[float, float]]:
    """V-World 장애 시 사용할 정적 폴백 — 데모 주소만 사전 좌표 조회해 db/seed/geocode_fallback.csv에 저장."""
    table: dict[str, tuple[float, float]] = {}
    if _GEOCODE_FALLBACK_PATH.exists():
        with open(_GEOCODE_FALLBACK_PATH, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("lon") and row.get("lat"):
                    key = " ".join(row["address"].split())
                    table[key] = (float(row["lon"]), float(row["lat"]))
    return table


_GEOCODE_FALLBACK = _load_geocode_fallback()


def _build_vworld_request(
    address: str, addr_type: str, key: str, proxy_url: str, proxy_token: str
) -> urllib.request.Request:
    """V-World getcoord 요청 객체 생성.

    VWORLD_PROXY_URL 이 설정돼 있으면 국내 우회 프록시(proxy/ 참고)를 경유하고,
    아니면 기존처럼 V-World를 직접 호출한다. 두 경우 모두 응답 JSON 형식은
    동일하므로 호출부 파싱 로직은 바뀌지 않는다. (proxy 미설정 시 = 기존 동작)
    """
    if proxy_url:
        params = urllib.parse.urlencode({"address": address, "type": addr_type})
        req = urllib.request.Request(f"{proxy_url}?{params}")
        if proxy_token:
            req.add_header("Authorization", f"Bearer {proxy_token}")
        return req
    params = urllib.parse.urlencode({
        "service": "address", "request": "getcoord",
        "crs": "EPSG:4326", "address": address,
        "type": addr_type, "key": key,
        "format": "json", "simple": "false",
    })
    return urllib.request.Request(f"https://api.vworld.kr/req/address?{params}")

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

app.include_router(auth.router)
app.include_router(farms.router)
app.include_router(young_farmers.router)
app.include_router(chat.router)
app.include_router(chat.conv_router)


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
    # 국내 우회 프록시(proxy/) 설정 시 키는 프록시가 보유 → 백엔드 키 없어도 됨
    proxy_url = os.getenv("VWORLD_PROXY_URL", "").strip()
    proxy_token = os.getenv("VWORLD_PROXY_TOKEN", "").strip()
    if not key and not proxy_url:
        raise HTTPException(503, "VWORLD_API_KEY 또는 VWORLD_PROXY_URL 미설정")

    # ── 1. 지오코딩 ──────────────────────────────────────────────────
    lon = lat = None
    for addr_type in ("PARCEL", "ROAD"):
        try:
            req = _build_vworld_request(address, addr_type, key, proxy_url, proxy_token)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            status = data["response"]["status"]
            if status == "OK":
                pt = data["response"]["result"]["point"]
                lon, lat = float(pt["x"]), float(pt["y"])
                break
            else:
                print(f"[geocode] V-World status={status} addr_type={addr_type}")
        except urllib.error.HTTPError as e:
            print(f"[geocode] V-World HTTPError {e.code} addr_type={addr_type} body={e.read()[:300]!r}")
        except Exception as e:
            print(f"[geocode] V-World call failed addr_type={addr_type} err={e!r}")

    if lon is None:
        fb_key = " ".join(address.split())
        if fb_key in _GEOCODE_FALLBACK:
            lon, lat = _GEOCODE_FALLBACK[fb_key]
            print(f"[geocode] static fallback hit for {fb_key!r}")

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

        # KNN 매칭이 KNN_CONFIDENT_KM(500m)보다 멀면 "그냥 제일 가까운 과수원"일
        # 뿐 이 좌표가 농지라는 보장이 없음 — 자동 면적 채움 없이 직접 입력 유도
        if row and dist_km is not None and dist_km > KNN_CONFIDENT_KM:
            result["warning"] = (
                "이 위치는 등록된 과수원 필지가 아닌 것 같습니다. 면적을 직접 입력해주세요."
            )
        elif row:
            sido, sigungu, area_m2 = row[1], row[2], row[4]
            result["area_m2"] = float(area_m2)
            result["sido"] = sido or ""
            result["sigungu"] = sigungu or ""
            # 필지 경계(빨간 테두리 표시용) — 이미 찾은 parcel_id로 조회
            with conn.cursor() as cur:
                cur.execute("SELECT ST_AsGeoJSON(geom) FROM parcel WHERE id = %s", (row[0],))
                geom_row = cur.fetchone()
            if geom_row and geom_row[0]:
                result["boundary"] = json.loads(geom_row[0])
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


@app.get("/api/facilities")
def facilities(conn=Depends(get_db)):
    """시설 종류 목록 (facility_std 기준) — 농가 등록 폼의 시설 드롭다운용.

    단가·내용연수 등 기준값은 서버(DB)에만 두고, 프런트엔드에는 선택용
    code·표시라벨만 내려준다(코드 5번 규칙: 기준값 프런트 하드코딩 금지).
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT facility_code, facility_name, facility_variant
                FROM facility_std
                ORDER BY facility_name, facility_variant
            """)
            rows = cur.fetchall()
    except Exception:
        conn.rollback()
        raise HTTPException(503, "시설 기준표를 불러오지 못했습니다.")
    return [
        {
            "facility_code": code,
            "label": f"{name} · {variant}" if variant else name,
        }
        for code, name, variant in rows
    ]
