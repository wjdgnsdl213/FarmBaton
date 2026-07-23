"""V-World 국내 우회 프록시 — 라즈베리파이/국내 리눅스 기기에서 구동.

배경
----
해외 클라우드(Railway)의 IP는 V-World가 공간정보관리법 16조(국외반출 제한)에
따라 자동 차단한다(502). 특정 IP 화이트리스트도 불가하다는 게 V-World 공식
답변이다. 따라서 **국내 ISP 회선에 연결된 기기**에서 이 프록시를 띄우고
Tailscale Funnel 등으로 외부에 노출하면, V-World가 보는 *아웃바운드 출발지
IP*가 국내가 되어 차단을 우회한다. (인바운드 터널과 무관하게 아웃바운드는
이 기기의 집 ISP IP로 나간다.)

설계 원칙
--------
- V-World 키는 **이 기기에만** 둔다. Railway 백엔드엔 키를 두지 않는다.
- 공유 시크릿 토큰(Authorization: Bearer)으로 인증해 무단 사용을 막는다.
- 응답은 V-World 원본 JSON을 **그대로** 반환한다 → 백엔드의 기존 파싱 로직
  (`data["response"]["status"]` …)을 한 줄도 바꿀 필요가 없다.

이 파일은 본 프로젝트의 backend 패키지에 의존하지 않는 **독립 실행 앱**이다
(DB·Anthropic 등 불필요). Pi에는 fastapi + uvicorn 두 패키지만 설치하면 된다.

실행 (자세한 셋업은 proxy/README.md 참고)
    export VWORLD_API_KEY=...        # data.go.kr / V-World 발급 키
    export VWORLD_PROXY_TOKEN=...    # 임의의 긴 난수 (백엔드와 동일 값)
    uvicorn vworld_proxy:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import FastAPI, Header, HTTPException, Query, Response

app = FastAPI(title="FarmBaton V-World Proxy", version="1.0.0")

_VWORLD_URL = "https://api.vworld.kr/req/address"


@app.get("/health")
def health():
    """Tailscale Funnel / 모니터링용 헬스체크 (인증 불필요)."""
    return {"status": "ok"}


@app.get("/geocode")
def geocode(
    address: str = Query(..., min_length=1),
    type: str = Query("PARCEL"),
    authorization: str | None = Header(default=None),
):
    """주소 → V-World getcoord 호출 후 원본 JSON 그대로 반환.

    백엔드(Railway)는 ?address=&type= 만 보내고 Authorization 헤더로 인증한다.
    V-World 키와 나머지 고정 파라미터는 이 프록시가 채운다.
    """
    # ── 인증: 토큰은 반드시 설정돼 있어야 한다(미설정 시 무단 공개 방지) ──
    token = os.getenv("VWORLD_PROXY_TOKEN", "")
    if not token:
        raise HTTPException(503, "VWORLD_PROXY_TOKEN not configured on proxy host")
    if authorization != f"Bearer {token}":
        raise HTTPException(401, "unauthorized")

    key = os.getenv("VWORLD_API_KEY", "")
    if not key:
        raise HTTPException(503, "VWORLD_API_KEY not configured on proxy host")

    params = urllib.parse.urlencode({
        "service": "address", "request": "getcoord",
        "crs": "EPSG:4326", "address": address,
        "type": type, "key": key,
        "format": "json", "simple": "false",
    })
    try:
        with urllib.request.urlopen(f"{_VWORLD_URL}?{params}", timeout=8) as resp:
            body = resp.read()
        # V-World 원본 JSON을 그대로 패스스루 (백엔드 파싱 호환)
        return Response(content=body, media_type="application/json")
    except urllib.error.HTTPError as e:
        # V-World가 이 기기 IP마저 차단하면 여기로 떨어진다 → 우회 실패 신호
        raise HTTPException(502, f"V-World HTTPError {e.code}")
    except Exception as e:  # noqa: BLE001  데모 안정성 우선, 원인 메시지만 전달
        raise HTTPException(502, f"V-World call failed: {e!r}")


@app.get("/reverse")
def reverse_geocode(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    authorization: str | None = Header(default=None),
):
    """좌표 → 주소 V-World getaddress 호출 후 원본 JSON을 반환한다."""
    token = os.getenv("VWORLD_PROXY_TOKEN", "")
    if not token:
        raise HTTPException(503, "VWORLD_PROXY_TOKEN not configured on proxy host")
    if authorization != f"Bearer {token}":
        raise HTTPException(401, "unauthorized")

    key = os.getenv("VWORLD_API_KEY", "")
    if not key:
        raise HTTPException(503, "VWORLD_API_KEY not configured on proxy host")

    params = urllib.parse.urlencode({
        "service": "address", "request": "getaddress", "version": "2.0",
        "crs": "epsg:4326", "point": f"{lon},{lat}", "type": "both",
        "zipcode": "false", "simple": "false", "format": "json", "key": key,
    })
    try:
        with urllib.request.urlopen(f"{_VWORLD_URL}?{params}", timeout=8) as resp:
            body = resp.read()
        return Response(content=body, media_type="application/json")
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"V-World HTTPError {e.code}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"V-World call failed: {e!r}")
