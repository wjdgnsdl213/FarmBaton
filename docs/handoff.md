# 작업 인수인계 (Handoff)

마지막 갱신: 2026-06-25. 다른 도구(Codex 등)로 작업을 넘기거나, 다음 세션에서
이어서 진행할 때 이 문서부터 읽을 것. CLAUDE.md의 스코프·규칙은 그대로 유효함.

> ⚠️ **동시 작업 주의**: 같은 작업 디렉터리에서 다른 도구(Codex 추정)가 병행
> 커밋한 사례가 있었음(아래 V-World 프록시 `6e1641e`). 그쪽 `git add` 때 내가
> 수정 중이던 `main.py`까지 함께 커밋돼 섞인 적 있음. 작업 전 `git log`·
> `git status`로 최신 상태 확인하고, 수정 후 즉시 커밋해 휩쓸림을 줄일 것.

## 1. 현재 단계

- 마감: **2026-06-30**
- CLAUDE.md 체크리스트 기준 P0~P3 완료, P4(배포) 운영 중. 베타 피드백 반영
  + 마무리 단계. 적용된 마이그레이션: 001~008 (007 평년가, 008 채팅).
- production URL: **https://farmbaton.vercel.app** (백엔드:
  `https://backend-production-a7818.up.railway.app`)

## 1-1. 이번 세션(2026-06-25)에서 완료한 작업 (커밋 순)

1. **`f556288` PDF 레이아웃 개선** — 강제 2페이지(min-height) → `@page` 여백 +
   자연 흐름으로 1페이지 하단 공백 제거. 섹션을 얇은 테두리 카드로 구분(그림자·
   굵은 선 없이). 시나리오 표를 1페이지로 이동. 인수 검토가 1억 미만이면 억 대신
   만원 표기(`_build_report_context`의 조건 분기).
2. **`423f850` 상담 인앱화** — 상담 신청은 **로그인 청년농만**(익명 폐지), 전화
   연결(`tel:`)·전화번호 입력/저장 폐지(개인정보·신뢰도). 농장주 상담함
   (`list_consult_requests`)에 신청 청년농의 매칭 프로필+점수 포함. 대시보드의
   "상담 신청 보기"+"매칭된 청년농 보기" 버튼 2개 → **"청년농 관리" 하나로 결합**
   (상담 신청 + 매칭 후보 2그룹). `ConsultRequestCreate`/`Detail` 스키마 변경
   (contact_phone 제거, 매칭 필드 추가).
3. **`6e1641e` V-World 국내 우회 프록시 (동시 작업, 내가 만든 커밋 아님)** —
   `proxy/`(국내 기기에서 띄우는 V-World 중계 FastAPI) + `main.py` 지오코딩이
   `VWORLD_PROXY_URL` 설정 시 프록시 경유. **환경변수 미설정이면 기존 직접호출
   그대로**(기본 비활성). 셋업은 `proxy/README.md` 참고. (아래 섹션 7 참고)
4. **`ab586a7` 상담 수락 후 인앱 채팅** — 수락(ACCEPTED)된 상담 1건 = 대화방
   1개. 마이그레이션 008 `chat_message`. `chat.py`: GET/POST
   `/api/consult-requests/{id}/messages` (당사자만, 수락 전 전송 409, 응답
   `mine` 플래그는 요청자 관점). 청년농 본인 상담함 `GET
   /api/young-farmers/me/consult-requests`. 프론트: 공용 `ChatPanel`(4초 폴링).
   (참고: 채팅 진입은 아래 5번에서 "대화" 메뉴로 이동함)
5. **`a06c9bb` 양면 대화 — 매칭 후보 계정화 + 농장주 발신 + 채팅 별도 메뉴**
   — "매칭 후보(미신청)"가 읽기전용 죽은 정보(후보 72명 전원 익명=연락 불가)
   였던 문제 해결.
   - **C1 매칭 로그인 필수화**: `create_young_farmer` 익명 경로 폐지(YOUNG
     로그인만), `/young`을 `RequireAuth role="YOUNG"`로 게이트 → 게스트는
     로그인, 농장주는 "청년농 전용" RoleNotice. **이슈3(농장주 재로그인 버그)
     동시 해결.** 매칭 풀이 계정 보유자만 남음.
   - **C2 농장주 발신 대화**: 마이그레이션 009 `consult_request.initiated_by`
     (YOUNG/FARMER) + `(farm_id, young_farmer_id)` 유니크. `POST
     /api/farms/{id}/conversations` → status=ACCEPTED·initiated_by=FARMER 대화방
     생성(중복 시 같은 방, 계정 없는 후보는 409). 매칭 후보 카드 "대화 신청".
     **상담 신청 인박스는 `initiated_by='YOUNG'`만** 표시(농장주 발신은 대화에만).
   - **C3 채팅 별도 "대화" 메뉴**: `GET /api/conversations`(역할 무관 대화 목록),
     `ConversationsPage`(좌측 목록 + 우측 `ChatPanel`), nav "대화"(양 역할).
     상담 카드·`/my-requests`에서 인라인 채팅 제거 → "대화" 메뉴로 일원화.
     매칭 후보는 접기/펴기(기본 접힘)로 길이 문제 해소.
   - **C0 데이터**: 익명 청년농 프로필 72개 정리 + 데모 계정 시딩(아래 섹션 8).

→ 전부 production 배포·검증 완료(2페이지 PDF·만원 표기·채팅·익명 매칭 403·
대화 라우트·폰트 임베딩 확인). pytest 55개 통과. 적용 마이그레이션 001~009.

## 2. 직전 세션(2026-06-24)에서 완료한 작업 (커밋 순)

1. **`757b330` 랜딩 인트로 애니메이션** — 합의된 감성 문구("떠나는 농장의
   가치를 이어갑니다 / 경험은 남기고, 청년의 꿈은 자라납니다.")를 전체화면
   오버레이로 표시. 처음엔 1.7초·단색 그린이었으나 피드백 반영해 **3초 +
   블러 처리한 농장사진 배경(`hero-farm.jpg`)**으로 변경. `sessionStorage`
   (`fb_intro_shown`)로 세션당 1회, `prefers-reduced-motion`이면 숨김.
   (`LandingPage.tsx` `useIntro` 훅 + `.lp-intro` CSS)
2. **`47d156d` PDF 평년가(3개년 평균) 기능** — 지난 세션 막혔던 "3년 평균"
   이슈 해결(아래 섹션 3 참고). KAMIS *웹사이트* 엑셀다운로드의 공식 "평년"
   값을 정적 파일로 적재. 마이그레이션 `006`, ETL `etl/06_normal_year_price.py`,
   PDF "시세 참고" 행 추가. 가치평가 계산엔 안 씀(rule 1), 결정론적 설명문만.
3. **`591ca64`/`a35456c` 농가등록·청년농 페이지 풀와이드 리디자인** — 좁은
   720px 폼 → 랜딩처럼 풀블리드 히어로 + 폼/결과 폭 제한(`.page-wrap`).
   매칭 카드 2열 그리드(`.match-grid`), 가치평가 결과 4열. 페이지별 히어로
   사진 적용(농가=과수 농가주 `hero-farmer.jpg`, 청년농=세대 핸드오버
   `hero-young.jpg`). 청년농 히어로는 사진 가독성 위해 라임 카드 → 짙은
   올리브 오버레이+흰 텍스트로 변경. (덤: 결과 스크롤 시 sticky nav가 카드
   가리던 버그 `.scroll-anchor`로 수정)
4. **`6efb9ba` 히어로 사진 크롭 조정** — 인물 머리가 위로 잘려서 히어로
   높이 키우고 `object-position` 수직값 낮춤.
5. **`bddc4b5` 상담 수락 후속 기능** — "수락만 되고 다음이 없다"는 피드백.
   수락 시 `farm.status`를 **MATCHED로 자동 전환**(대시보드에 "매칭완료"
   태그), 연락처를 **`tel:` 링크**로 바꿔 즉시 전화 연결. 응답에
   `farm_status` 필드 추가(`ConsultRequestResponse`). "매칭된 청년농 보기"는
   익명 프로필이라 액션 불가임을 명시하는 안내문구 추가.
6. **`8994bbe` 매칭 카드 팝업 모달** — 클릭 시 카드가 길게 펼쳐져 나머지
   결과를 가리던 문제. 시설현황·지원사업·PDF·상담폼을 `createPortal` 기반
   모달(`.modal-backdrop`/`.modal-panel`)로 이동.
7. **`504a756` CTA 색상 그린 통일 + 정책자금 도움말** — 테라코타 CTA가 전체
   그린 톤과 부조화 → `--accent`를 생기 있는 그린(`#2e9e57`, hover `#1f6b3a`)
   으로 교체(nav/히어로/하단 CTA 일괄). "정책자금 신청 예정" 체크박스 기능
   설명이 화면에 없어 한 줄 도움말 추가.
8. **`81d75e9` PDF 리포트 관점별 차별화** — "AI 활용이 미약하다"는 피드백.
   `report.pdf?audience=farmer|young`으로 같은 수치를 받아 **서술 관점만**
   분기(농장주=매도 준비·시설 가치 어필·협상 자료, 청년농=자본 회수·정책자금·
   영농 체크리스트). AI 출력에 `advice`(관점별 조언) 섹션 신설로 분량 보강
   (`max_tokens` 500→900). 숫자는 동일·서술만 분기라 rule 1 안전. 마이그레이션
   `007`로 `(farm_id, audience)`별 캐시 테이블 `report_narrative` 신설(관점별
   1회 생성 후 캐시). 프론트: 농가 등록=farmer, 청년농 매칭 모달=young 링크.
9. **`d34493a` 역할 선택 회원가입 + 청년농 로그인** — 회원가입 시 농장주/
   청년농 역할 선택, 청년농도 로그인 가능. **로그인한 청년농은 본인 계정
   정보로 상담 신청**(이름·연락처 자동) → 농장주가 실명 계정과 함께 신청 수신.
   기존 경로 비파괴: 익명 청년농 매칭 데모는 그대로 동작. 상세는 아래 섹션 4.

모두 `git push` + Railway(`railway up --service backend --ci`, 백엔드 변경
있는 커밋만) + Vercel(`cd frontend && rm -rf .vercel/output dist &&
vercel --prod --yes`)로 배포 완료, production URL에서 동작 확인까지 마침.

## 3. [해결됨] PDF "3년 평균" 기능 — KAMIS 웹사이트 평년가로 우회

지난 세션엔 "KAMIS Open-API에 다년 평년 통계 엔드포인트가 없다"며 막혀
옵션 A/B/C만 정리해뒀음. **이번 세션에 옵션 D를 찾음:**

- KAMIS *웹사이트*("소매가격 > 기간별/연간") 화면에 공식 **"평년"** 행이
  있고, 화면 안내문에 정의가 명시됨: **"5년간(금년 제외) 최고·최저 제외
  3개년 평균"** — 사용자가 원했던 "3년 평균"과 정확히 일치.
- Open-API가 아니라 **엑셀다운로드**(HTML 테이블을 `.xls`로 저장)로 받는
  정적 데이터. 이미 쓰는 실거래가 CSV·소득조사 등과 같은 정적 패턴이라
  rule 3 위반 아님. 사용자가 사과/복숭아/포도 3개 화면을 직접 받아
  `db/seed/kamis_normal_year_{apple,peach,grape}.xls`로 제공.
- **검증**: 받은 파일의 `<title>`이 "친환경농산물"로 잘못 찍혀 있어 확인이
  필요했으나, 라이브 KAMIS API(`p_productrankcode=04`)로 2025년 평균을
  직접 계산해 사이트 표와 대조 → 사과/복숭아=상품, 포도=L과 표가 일반
  소매가와 일치함을 확인(친환경 아님, 템플릿 오류였음).
- **구현**: 마이그레이션 `006_price_trend_normal_year.sql`로 `price_trend`에
  `normal_year_price`/`price_unit`/`normal_year_source` 컬럼 추가(운영 DB
  적용 완료). `etl/06_normal_year_price.py`가 정적 파일 파싱 → 적재. PDF
  핵심수치 섹션에 "시세 참고" 행 추가(`farms.py:_build_normal_year_text`,
  결정론적 텍스트, LLM 미사용). **가치평가 산식은 안 건드림.**
- **포도 예외**: KAMIS 자체가 변동성 과다로 평년값을 "-"로 비워둠 →
  `normal_year_price=NULL` 유지, PDF엔 "산출하지 못했습니다" 문구로 명시.

## 4. 인증·역할 모델 (커밋 `a06c9bb` 이후 현재 상태 — 완전 계정 기반)

청년농 측까지 **완전히 계정 기반**으로 정착. 익명 경로는 모두 폐지됨.

- `app_user.role`(FARMER/YOUNG/ADMIN). 회원가입에 role 선택(`auth.py register`),
  로그인 역할 무관(응답에 `role`). `me`는 role/phone 반환.
- `get_current_user_optional`(auth.py) — 토큰 있으면 `(user_id, role)`, 없으면 None.
- **매칭(`create_young_farmer`)·상담(`create_consult_request`) 모두 로그인 YOUNG
  필수** (익명 경로 폐지). 매칭은 본인 프로필 1개 upsert, 상담은 본인 프로필
  검증 + 계정 이름만 저장(전화번호 비저장·비노출). 같은 농장 재신청은 기존
  대화 재사용(`uq_consult_farm_young`).
- **대화 모델**: `consult_request`가 곧 대화방. `initiated_by`(YOUNG=청년농 신청,
  FARMER=농장주 발신). 농장주 발신은 즉시 ACCEPTED. 상담 인박스
  (`list_consult_requests`)는 `initiated_by='YOUNG'`만, "대화"(`/api/conversations`)는
  양쪽 ACCEPTED 전부.
- **채팅 권한**(`chat.py _authorize`): 농장 소유 FARMER 또는 신청 YOUNG 본인만.
  수락 전 전송 409. `mine` 플래그는 요청자 관점.
- 프론트 라우트 가드: `/farmer`·`/dashboard` = FARMER, `/young`·`/my-requests` =
  YOUNG, `/conversations` = 로그인 누구나(`RequireAuth`). 역할 불일치 시 RoleNotice
  ("전용 메뉴"). nav: FARMER=내 농장/대화, YOUNG=청년농 매칭(/young)/내 상담/대화.

## 4-1. 데모 계정 (production, 시연용 — 정리 대상 아님)

공통 비밀번호 **`farmbaton!2026`**. C0(`a06c9bb`)에서 시딩, `demo.*@farmbaton.kr`.

- `demo.farmer@farmbaton.kr` (정현우) — 충북 사과 농장 보유(ACTIVE).
- `demo.young1@farmbaton.kr`(김서준, 충북/사과/2억/5년/매도),
  `demo.young2`(이도윤, 경북/포도/1.2억/2년/임대),
  `demo.young3`(박하은, 충남/복숭아/1.5억/3년/공동경영),
  `demo.young4`(최지호, 충북/사과/3억/8년/멘토후독립).
- 매칭 풀 = 이 청년농 4명(전원 계정 보유). 정현우↔김서준 사이에 농장주 발신
  데모 대화 1건(메시지 2개) 존재.

## 5. 아직 안 한 것 / 다음 논의

- **농장 구인구직 기능** — 사용자가 제안(현재는 승계만, 농장 노동 구인구직도?).
  **다음 세션에서 다시 논의하기로 함**(이번엔 미착수). 내 평가: 6/30 전에는
  비권장(CLAUDE.md 스코프 밖, 가치평가/매칭 엔진 재사용 불가한 다른 도메인,
  마감 리스크). 역할 계정·매칭 인프라는 좋은 토대라 대회 후 확장 후보. 결정
  전까지 구현 보류.
- **V-World 프록시 국내 기기 실제 가동** — 코드(`proxy/`)·백엔드 연동은 완료
  (6e1641e). 남은 건 **국내 기기에서 `proxy/` 실행 + Tailscale Funnel 등으로
  노출 + Railway 환경변수 `VWORLD_PROXY_URL`/`VWORLD_PROXY_TOKEN` 설정**(물리
  세팅, 사용자 몫). 설정 전까지는 정적 폴백으로 데모 동작(섹션 7).
- **PDF AI 추가 보강** — 관점별 차별화로 분량·AI 활용은 충분. 더 한다면 모델
  티어 업 정도. 우선순위 낮음.
- **채팅 고도화(7월)** — 현재 4초 폴링·읽음표시 없음. 실서비스화하면 웹소켓·
  읽음·알림 고려. 데모엔 현재로 충분. (농장주→매칭후보 발신 채팅은 a06c9bb로
  완료 — 이전 "보류" 항목 해소됨.)

## 6. 검토했으나 안 하기로 한 것 (재논의 방지)

- **희망 지역·작목 하드 필터링** — 현재는 필터가 아니라 가중치 점수(일치
  시 +20점, `valuation.py:350,353`)로 전체를 점수순 정렬. 사용자가 하드
  필터로 바꾸는 걸 고민했으나, **시드 매물이 10개 안팎이라 필터 시 빈 화면
  위험** + "가까운 대안 제시"라는 매칭 본질에 안 맞아 **현재 방식 유지로
  결정**. (절충안: 프론트에서 점수 0 농장만 숨기는 토글은 가능하나 스코프
  추가라 보류)

## 7. 운영 환경 참고 (자주 까먹는 것들)

- **로컬과 production이 같은 Supabase DB를 공유함.** 로컬 backend를 띄워서
  테스트해도 운영 데이터에 직접 쓰임 — 테스트 후 꼭 정리할 것. 테스트
  계정은 식별 가능한 이메일(`*_test_*@example.com`류) 사용.
- **Railway 배포**: git push 자동배포가 불안정 — 수동
  `railway up --service backend --ci` 우선. 프론트만 바뀐 커밋은 Vercel만
  배포하면 됨(백엔드 재배포 불필요).
- **Vercel 배포**: Root Directory가 `.`여야 로컬 CLI 배포
  (`cd frontend && vercel --prod --yes`)가 정상. `frontend`로 바꾸면 경로가
  두 번 겹쳐 깨짐.
- **V-World 지오코딩 — IP 차단 + 프록시 우회 준비됨.** Railway IP를 502 차단
  (V-World 공식 답변: 국외반출 제한, 국내 서버 필요). **우회 프록시 구현 완료**
  (`proxy/`, 6e1641e): 국내 기기에서 V-World 중계 FastAPI를 띄우고 Tailscale
  Funnel로 노출 → Railway에 `VWORLD_PROXY_URL`/`VWORLD_PROXY_TOKEN` 설정 시
  프록시 경유 호출(키는 프록시 기기에만). **환경변수 미설정 시 기존 직접호출
  그대로**. 셋업 가이드 `proxy/README.md`. 아직 국내 기기 미가동이라, 현재는
  정적 폴백(`db/seed/geocode_fallback.csv`, 9개 데모 주소)으로 데모 동작 —
  대회 제출까지 충분.
- **로컬 backend 포트 "유령 LISTEN"** — PID가 죽었는데 OS가 포트(8000)를
  안 놔주는 경우 있음. 같은 포트 재시도 대신 `taskkill //PID <pid> //F`로
  죽이거나 다른 포트로 띄울 것.
- **한글 인라인 인자 인코딩** — bash/python에 한글을 인라인으로 넘기면 깨짐
  (cp949 콘솔). Playwright 등 한글 셀렉터 쓸 땐 `.py` 파일로 저장 후
  `PYTHONUTF8=1 python file.py`로 실행.
