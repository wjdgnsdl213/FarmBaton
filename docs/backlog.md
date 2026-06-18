# Backlog

스코프 밖 개선점·후속 작업 기록용. 구현은 여기 적힌 뒤 별도 승인 후 진행.

## KAMIS price_trend 재실행 필요 (계절성)

- **무엇**: `etl/05_price_trend.py --load` 재실행 — PEACH, GRAPE
- **왜**: 2026-06-18 실행 시 KAMIS에 복숭아(백도)·포도(샤인머스켓 등 전 품종) 거래 데이터가 전혀 없어 두 작목은 skip됨. 사과(후지)만 적재됨(trend_index=0.930). 저온저장으로 연중 유통되는 사과와 달리 복숭아·포도는 통상 7~8월 이후 출하되는 계절 과수라 시즌 전엔 KAMIS 시세 자체가 없음.
- **언제**: 복숭아·포도 출하 시작 후(대략 7월 이후) 1회 재실행. 이후 시세 변동 반영을 위해 주기적 재실행 고려.
- **현재 상태**: PEACH/GRAPE는 `price_trend` 테이블에 행 없음 → `db_loader.py`의 기존 폴백(`trend_index=1.0`)이 적용되어 데모는 정상 동작.

## [FIXED] 좌표 없이 등록 시 토지가가 0원으로 떨어짐

- **무엇**: `backend/app/services/db_loader.py:_load_land` — `bjd_cd`가 없으면(`FarmerPage.tsx`에서 위치검색 없이 면적만 수동 입력한 경우, 또는 V-World 장애 시) `official_price_m2=0.0` 반환 → 인수 검토가가 `0~0만원`으로 표시됨.
- **왜**: V-World가 죽었을 때 "정적 폴백으로 화면이 끝까지 돈다"는 게 CLAUDE.md rule 3의 요구사항인데, 실제로는 크래시 대신 **신뢰할 수 없는 0원**을 확신 있게 보여줌. 크래시보다 더 위험한 실패 모드(발표 중 들통나지 않고 틀린 값이 나감).
- **수정**: sido 단위 평균 공시지가로 폴백 (구현 완료, 아래 참고).

## [FIXED] 필지 KNN 매칭에 거리 제한 없음

- **무엇**: `backend/app/routers/farms.py:_call_farm_card`의 2차 KNN 폴백이 거리 무관하게 무조건 가장 가까운 과수원 필지를 반환. 서울 좌표로 테스트 시 67km 떨어진 천안 필지를 경고 없이 매칭함.
- **왜**: 주소 오타·V-World 오인식 시 전혀 다른 동네의 면적·지가가 조용히 붙을 위험. `/api/geocode`의 폴백은 sido로 스코프를 좁혀 더 안전한데 `farms.py`는 그 패턴이 빠져 있었음.
- **수정**: sido 스코프 추가 + 거리 임계값(20km) 초과 시 명시적 warning (구현 완료, 아래 참고).

## [FIXED] facility_std.csv와 실제 DB 코드 불일치

- **무엇**: `db/seed/facility_std.csv`는 `GH_SINGLE`/`COLD_STORAGE`/`WAREHOUSE` 코드를 쓰는데 실제 Supabase DB는 `VINYL_HOUSE_SINGLE`/`COLD_STORAGE_SMALL`/`FARM_WAREHOUSE_PANEL`/`FARM_WAREHOUSE_GENERAL`을 씀.
- **왜**: 앱은 DB만 읽으므로 지금 당장 장애는 아니지만, CSV로 재시딩하면 기존 `farm_asset.facility_code` 참조가 깨짐. 문서(CSV)와 운영 데이터가 분기된 상태.
- **수정**: CSV를 실제 DB 코드로 동기화 (구현 완료, 아래 참고).
