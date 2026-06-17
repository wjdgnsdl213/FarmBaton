"""팜바톤 FastAPI 앱 진입점."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(override=True)  # .env 우선 (외부 환경변수 따옴표 오염 방지)

import json
import os
import urllib.parse
import urllib.request

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routers import farms, young_farmers

app = FastAPI(
    title="팜바톤 API",
    description="고령 농가 승계 진단·매칭 플랫폼",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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
def geocode(address: str):
    """주소 → WGS84 좌표 (V-World 프록시). PARCEL → ROAD 순 재시도."""
    key = os.getenv("VWORLD_API_KEY", "")
    if not key:
        raise HTTPException(503, "VWORLD_API_KEY not configured")

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
                return {"lon": float(pt["x"]), "lat": float(pt["y"])}
        except Exception:
            continue

    raise HTTPException(404, "주소를 찾을 수 없습니다.")
