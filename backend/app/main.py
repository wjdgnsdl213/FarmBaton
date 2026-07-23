"""팜바톤 FastAPI 앱 진입점."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(override=True)  # .env 우선 (외부 환경변수 따옴표 오염 방지)

import csv
import json
import math
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


def _build_vworld_reverse_request(
    lon: float, lat: float, key: str, proxy_url: str, proxy_token: str
) -> urllib.request.Request:
    """현재 좌표를 주소로 바꾸는 V-World 요청을 만든다.

    프록시가 설정된 경우에는 같은 프록시의 /reverse 엔드포인트를 사용한다.
    키가 없더라도 정적 데모 좌표 폴백은 이후 단계에서 시도한다.
    """
    if proxy_url:
        base_url = proxy_url.rstrip("/").rsplit("/", 1)[0]
        params = urllib.parse.urlencode({"lon": lon, "lat": lat})
        req = urllib.request.Request(f"{base_url}/reverse?{params}")
        if proxy_token:
            req.add_header("Authorization", f"Bearer {proxy_token}")
        return req
    params = urllib.parse.urlencode({
        "service": "address", "request": "getaddress", "version": "2.0",
        "crs": "epsg:4326", "point": f"{lon},{lat}", "type": "both",
        "zipcode": "false", "simple": "false", "format": "json", "key": key,
    })
    return urllib.request.Request(f"https://api.vworld.kr/req/address?{params}")


def _extract_reverse_address(data: dict) -> str | None:
    """V-World getaddress 응답의 후보 주소에서 사람이 읽을 수 있는 주소를 꺼낸다."""
    result = data.get("response", {}).get("result", [])
    candidates = result if isinstance(result, list) else [result]
    for candidate in candidates:
        if isinstance(candidate, dict):
            text = candidate.get("text") or candidate.get("address")
            if isinstance(text, str) and text.strip():
                return " ".join(text.split())
    return None


def _find_static_reverse_address(lon: float, lat: float, max_distance_m: float = 120) -> str | None:
    """데모 주소 좌표와 120m 이내일 때만 정적 주소 폴백을 반환한다.

    임의 위치에 가까운 주소를 채우지 않도록 작은 반경만 허용한다.
    """
    nearest: tuple[str, float] | None = None
    lat_scale = 111_320
    lon_scale = lat_scale * math.cos(math.radians(lat))
    for address, (fb_lon, fb_lat) in _GEOCODE_FALLBACK.items():
        distance_m = math.hypot((fb_lon - lon) * lon_scale, (fb_lat - lat) * lat_scale)
        if nearest is None or distance_m < nearest[1]:
            nearest = (address, distance_m)
    return nearest[0] if nearest and nearest[1] <= max_distance_m else None

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


@app.get("/api/reverse-geocode")
def reverse_geocode(lat: float, lon: float):
    """현재 좌표를 농장 주소 입력란에 넣을 수 있는 주소로 변환한다.

    브라우저의 위치 권한은 사용자가 버튼을 누른 경우에만 요청한다. V-World 또는
    국내 프록시를 우선 사용하고, 데모 CSV 좌표와 120m 이내일 때만 정적 폴백을
    허용한다. 그 외 실패 시 임의 주소를 채우지 않고 수동 입력을 안내한다.
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(422, "위치 좌표 형식이 올바르지 않습니다.")

    key = os.getenv("VWORLD_API_KEY", "")
    proxy_url = os.getenv("VWORLD_PROXY_URL", "").strip()
    proxy_token = os.getenv("VWORLD_PROXY_TOKEN", "").strip()
    address = None
    source = ""

    if key or proxy_url:
        try:
            req = _build_vworld_reverse_request(lon, lat, key, proxy_url, proxy_token)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            if data.get("response", {}).get("status") == "OK":
                address = _extract_reverse_address(data)
                source = "vworld"
        except Exception as exc:  # noqa: BLE001 - 수동 주소 입력 경로로 안전하게 폴백
            print(f"[reverse-geocode] V-World call failed err={exc!r}")

    if not address:
        address = _find_static_reverse_address(lon, lat)
        if address:
            source = "static"

    if not address:
        raise HTTPException(404, "현재 위치의 주소를 찾지 못했습니다. 주소를 직접 입력해주세요.")

    return {"address": address, "lat": lat, "lon": lon, "source": source}


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
