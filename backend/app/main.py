"""팜바톤 FastAPI 앱 진입점."""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(override=True)  # .env 우선 (외부 환경변수 따옴표 오염 방지)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routers import farms

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


@app.get("/health")
def health():
    return {"status": "ok"}
