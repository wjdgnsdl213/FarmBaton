# 작업 인수인계 (Handoff)

마지막 갱신: 2026-06-24. 다른 도구(Codex 등)로 작업을 넘기거나, 다음 세션에서
이어서 진행할 때 이 문서부터 읽을 것. CLAUDE.md의 스코프·규칙은 그대로 유효함.

## 1. 현재 단계

- 마감: **2026-06-30**
- CLAUDE.md 체크리스트 기준 P0~P3는 기능적으로 완료, P4(배포)는 이미 운영 중
  (Railway 백엔드 + Vercel 프론트). 지금은 베타 피드백 반영 + 마무리 단계.
- production URL: **https://farmbaton.vercel.app** (백엔드:
  `https://backend-production-a7818.up.railway.app`)

## 2. 이번 세션(2026-06-24)에서 완료한 작업 (커밋 순)

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

## 4. 인증·역할 모델 (커밋 `d34493a` 이후 현재 상태)

지난 세션까진 "농가만 로그인, 청년농은 익명"이었으나 이번에 역할 기반으로
확장. **단, 익명 청년농 매칭은 그대로 유지**(MVP 데모 핵심이라 비파괴).

- `app_user.role`(FARMER/YOUNG/ADMIN) enum은 002부터 있었음. 이번에 회원가입에
  role 선택을 붙이고(`auth.py register`), 로그인을 역할 무관으로 바꿈(응답에
  `role` 포함). `me`도 role/phone 반환.
- 새 의존성 `get_current_user_optional`(auth.py) — 토큰 있으면 `(user_id, role)`,
  없으면 None. 로그인 없이도 동작해야 하는 엔드포인트(청년농 매칭·상담)에서 사용.
- `create_young_farmer`: 로그인 YOUNG이면 **본인 계정에 프로필 1개 upsert**
  (재제출 시 같은 id 갱신), 익명이면 기존대로 익명 app_user+프로필 생성.
- `create_consult_request`: 로그인 YOUNG이면 연락처를 **계정 정보(name/phone)로
  권위 있게 덮어씀**(폼 값 무시), 익명이면 폼 입력 사용.
- 프론트: `farmbaton_role` localStorage 저장, `/farmer`·`/dashboard`는 FARMER
  가드(`RequireAuth role="FARMER"`), 로그인 후 role별 라우팅(FARMER→대시보드,
  YOUNG→매칭), nav에서 청년농에겐 "내 농장" 숨김. YoungPage는 로그인 YOUNG이면
  상담폼이 계정 정보 표시로 대체(`/auth/me` 조회).

## 5. 아직 안 한 것 (다음 우선순위)

- **당근마켓식 채팅** (아이디어 1-B) — 역할 로그인이 깔렸으니 다음 후보.
  단 메시지 테이블·폴링/웹소켓·읽음 처리 등 **새 서브시스템**이고 CLAUDE.md
  MVP 스코프(데모 기능 2개) 밖이라 **7월 이후 권장**. 현재는 상담 수락 →
  `tel:` 전화 연결이 그 역할을 대체하고 있어 데모엔 충분.
- **PDF AI 추가 보강** — 관점별 차별화(`81d75e9`)로 분량·AI 활용은 한 단계
  올렸음. 더 한다면 모델 티어 업(현재 `report_ai.py`의 `claude-haiku-4-5`)이나
  섹션 추가. 우선순위는 낮아짐.
- **V-World 국내 서버 우회** (아래 "운영 환경 참고" 절 참고) — 사용자가
  라즈베리파이/Cloudflare Tunnel 방향에 관심. **착수 안 함**(사용자가 "나중에"로 보류).
  진행 시 (1) V-World 호출 중계 FastAPI 프록시 + (2) Railway 백엔드가 그
  프록시를 호출하도록 변경 — 코드는 작성 가능, 파이 물리 세팅은 사용자 몫.

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
- **V-World 지오코딩 — IP 차단 확정.** Railway IP를 502로 차단. 화이트리스트
  요청에 대한 **V-World 공식 답변 도착(2026-06-24)**: "공간정보관리법 16조
  국외반출 제한으로 해외 클라우드는 자동 차단, 특정 IP만 해제 불가, **국내로
  인식되는 서버를 쓰라**." → AWS/GCP 서울 리전도 해외 사업자라 막힐 가능성
  높음. 실질 우회책은 **국내 ISP 회선(가정용 라즈베리파이 등)에서 프록시**.
  현재는 정적 폴백(`db/seed/geocode_fallback.csv`, 9개 데모 주소)으로 데모가
  안 죽게 되어 있어 대회 제출까지는 충분.
- **로컬 backend 포트 "유령 LISTEN"** — PID가 죽었는데 OS가 포트(8000)를
  안 놔주는 경우 있음. 같은 포트 재시도 대신 `taskkill //PID <pid> //F`로
  죽이거나 다른 포트로 띄울 것.
- **한글 인라인 인자 인코딩** — bash/python에 한글을 인라인으로 넘기면 깨짐
  (cp949 콘솔). Playwright 등 한글 셀렉터 쓸 땐 `.py` 파일로 저장 후
  `PYTHONUTF8=1 python file.py`로 실행.
