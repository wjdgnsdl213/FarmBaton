# V-World 국내 우회 프록시 셋업 가이드

해외 클라우드(Railway) IP는 V-World가 국외반출 제한법으로 차단한다. 이 프록시를
**국내 ISP 회선에 연결된 기기**(라즈베리파이 등)에서 띄우고 Tailscale Funnel로
노출하면, V-World가 보는 아웃바운드 IP가 국내가 되어 차단을 우회한다.

> 이 디렉터리의 코드는 본 프로젝트 backend 패키지와 **독립**이다. Pi에는
> `fastapi`, `uvicorn` 두 패키지만 설치하면 된다.

전체 그림:

```
Railway 백엔드 ──HTTPS──▶ Tailscale Funnel(고정주소) ──▶ Pi(127.0.0.1:8000) ──▶ api.vworld.kr
   (해외)          VWORLD_PROXY_URL/_TOKEN          이 프록시          집 ISP IP(국내) ✅
```

---

## 0. 준비물

- 국내 인터넷에 연결된, 항상 켜둘 수 있는 리눅스 기기 (라즈베리파이 권장,
  쓰던 우분투 PC도 무방). **핵심 조건은 "한국 ISP 회선"** 하나뿐.
- V-World 인증키 (`.env`의 `VWORLD_API_KEY`와 동일한 키).

---

## 1. 프록시 코드 배치 + 가상환경

```bash
# Pi에서
mkdir -p ~/farmbaton-proxy && cd ~/farmbaton-proxy
# 이 디렉터리(proxy/)의 vworld_proxy.py, requirements.txt, .env.example,
# vworld-proxy.service 를 이 경로로 복사 (scp / git clone 등)

python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 2. 환경변수 설정

```bash
cp .env.example .env
# 토큰 생성 (백엔드와 동일 값을 쓸 것이니 출력값을 메모)
python3 -c "import secrets; print(secrets.token_hex(32))"
nano .env   # VWORLD_API_KEY, VWORLD_PROXY_TOKEN 채우기
```

## 3. 로컬 동작 확인 (Funnel 붙이기 전)

```bash
set -a; source .env; set +a
./venv/bin/uvicorn vworld_proxy:app --host 127.0.0.1 --port 8000 &

curl localhost:8000/health
# {"status":"ok"}

curl -H "Authorization: Bearer $VWORLD_PROXY_TOKEN" \
  "localhost:8000/geocode?address=충북 충주시 엄정면 미내리 123&type=PARCEL"
```

✅ **검증 핵심**: 위 응답의 `response.status`가 `"OK"`이고 `point` 좌표가
나오면 — **이 기기의 국내 IP는 V-World에 차단되지 않은 것**이다(= 우회 성공
증명). 만약 502/차단이 뜨면 이 회선도 막힌 것이니 다른 국내 회선을 시도한다.

확인 후 백그라운드 uvicorn은 종료: `kill %1`

## 4. systemd 등록 (재부팅 자동 구동)

```bash
sudo cp vworld-proxy.service /etc/systemd/system/
# User / WorkingDirectory 경로가 실제와 다르면 먼저 수정
sudo systemctl daemon-reload
sudo systemctl enable --now vworld-proxy
sudo systemctl status vworld-proxy     # active(running) 확인
```

## 5. Tailscale Funnel 로 외부 노출

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # 브라우저 인증 (무료 Personal 플랜)
sudo tailscale funnel 8000 # 127.0.0.1:8000 을 공개 HTTPS로 노출
sudo tailscale funnel status
# https://<기기명>.<tailnet>.ts.net  ← 이 주소가 고정 VWORLD_PROXY_URL 이 된다
```

원격에서 확인:

```bash
curl https://<기기명>.<tailnet>.ts.net/health   # {"status":"ok"}
```

## 6. Railway 백엔드 연결

Railway 대시보드(또는 CLI)에서 두 환경변수 등록 — 이 순간부터 프록시 경유로
전환되며, **백엔드 재배포는 불필요**(다음 요청부터 적용):

```
VWORLD_PROXY_URL   = https://<기기명>.<tailnet>.ts.net/geocode
VWORLD_PROXY_TOKEN = (3번에서 생성한 토큰, Pi의 .env와 동일 값)
```

> 보안상 V-World 키(`VWORLD_API_KEY`)는 **Railway에서 제거**해도 된다(프록시가
> 보유). 백엔드는 `VWORLD_PROXY_URL`이 있으면 키 없이도 동작한다.

## 7. 최종 검증 (production)

폴백 CSV(`db/seed/geocode_fallback.csv`)에 **없는** 주소로 좌표가 나오면 성공:

```bash
curl "https://backend-production-a7818.up.railway.app/api/geocode?address=<폴백에 없는 국내 주소>"
# {"lon":..., "lat":..., ...}  ← 프록시 경유로 V-World 실시간 응답
```

---

## 장애 시 동작 (안전장치)

프록시가 꺼지거나 터널이 끊겨도 **데모는 죽지 않는다**. 백엔드는
`프록시 → 정적 폴백 CSV → 404` 순으로 떨어지므로, 데모 9개 주소는 항상 동작한다.
프록시를 완전히 끄려면 Railway에서 `VWORLD_PROXY_URL`만 지우면 즉시 기존
직접호출 방식으로 되돌아간다(코드 변경 불필요).
