# 팜바톤 가치평가·매칭 산식 (docs/formula.md)

> 이 문서는 가치평가/매칭 계산의 **단일 진실 원천**이다.
> backend/app/services/valuation.py, matching.py 는 이 문서를 그대로 구현한다.
> 계수·단가는 코드에 하드코딩하지 않고 DB 기준 테이블(001)을 참조한다.
> **모든 계산은 결정론적 Python. LLM 호출 금지.** (LLM은 설명문 생성에만)
> 표기는 항상 "인수 검토가 범위(참고용 추정)" — "감정가" 금지.

---

## 0. 입력 / 출력

**입력**
- 공공데이터 자동: 필지 면적(`area_m2`), 토지 단가(공시지가·실거래), 10a당 소득(`income_coef`), 시세지수(`price_trend`)
- 경영주 입력: 작목, 수령(`tree_age`), 재식밀도(선택), 시설 목록(종류·면적·연도·상태), 판로·매출(선택), 승계조건

**출력 (farm 테이블 캐시)**
- `est_income_min/max` 예상 연소득 범위
- `est_value_min/max` 인수 검토가 범위
- `confidence_grade` 신뢰도 등급(A~D)

기준 단위: 면적은 ㎡로 통일. 10a = 1,000㎡ ≈ 991.7㎡(실무 환산 1,000 사용). 금액은 원(KRW), 최종 표시는 만원 반올림.

---

## 1. 예상 연소득 (income)

```
base_income = income_coef.avg_income_10a × (area_m2 / 1000)
age_coef    = fn_orchard_age_coef(crop, tree_age)        -- 001의 곡선 함수
trend       = price_trend.trend_index                     -- 평년=1.0
skill_adj   = 숙련도 보정 (아래)

est_income_point = base_income × age_coef × trend × skill_adj
```

**숙련도 보정 `skill_adj`** — 개별 농가 기술·품질 편차 반영. 사용자가 입력하는
값은 조수입(매출)이고 기준값은 농업소득이므로, 작목별 평균 소득률로 같은 단위로
환산한 뒤 비교한다.

```
income_rate     = income_coef.avg_income_10a / income_coef.avg_gross_10a
observed_income = annual_revenue × income_rate
skill_adj       = clamp(observed_income / base_income, 0.7, 1.3)
```

- `avg_gross_10a`가 없으면 매출 보정을 적용하지 않고 `1.0`을 사용한다.
- 매출 미제출: `1.0` 고정 (평균 가정)
- 매출 제출: 평균 대비 ±30% 이내로 제한한다(과신 방지).

**범위 산출** — 점추정에 불확실성 밴드 적용:
```
band = income_band_by_grade(confidence_grade)   -- D:±25%, C:±18%, B:±12%, A:±8%
est_income_min = est_income_point × (1 - band)
est_income_max = est_income_point × (1 + band)
```

---

## 2. 토지 기준가 (land)

```
unit = COALESCE(deal_price_m2, official_price_m2 / official_to_market)
land_value_point = area_m2 × unit
```

- `official_to_market = 0.65` — 공시지가는 통상 시세의 60~70%. 실거래가 없을 때만 보정 적용. **실거래(deal_price_m2)가 있으면 보정하지 않는다.**
- `deal_price_m2` = 법정동·지목별 실거래 단가의 **중앙값** (ETL 적재 시 집계).
  평균이 아닌 중앙값인 이유: 소필지 고단가 거래(도로 편입 등)가 평균을 왜곡 —
  실거래 20만건 LOO 백테스트에서 과수원 중앙오차 24.2%→18.5% 개선 확인
  (2026-07, `etl/07_backtest_land.py`, `docs/backtest_land_report.md`).
- 실거래 표본이 빈약(`deal_sample_cnt < 3`)하면 신뢰도 등급 한 단계 하향.
- 범위: `land_min = ×0.9`, `land_max = ×1.1` (지가 자체 변동폭).

---

## 3. 시설 잔존가 (facility)

농장의 모든 `farm_asset`에 대해 합산:

```
new_cost  = fn_facility_new_cost(facility_code, area_m2)     -- 001 함수
elapsed   = current_year - installed_year
dep_ratio = GREATEST(salvage_rate, 1 - elapsed / useful_life_years)
cond_mult = facility_condition.multiplier(condition_grade)   -- A1.0 B0.85 C0.6

asset_residual = new_cost × dep_ratio × cond_mult
facility_value = Σ asset_residual
```

- `installed_year` 미상이면 `dep_ratio = 0.5` 가정 + 신뢰도 하향.
- 범위: `facility_min = ×0.85`, `facility_max = ×1.05` (상태 평가 주관성).

---

## 4. 영업권 (goodwill) — 가장 보수적으로

판로·매출 자료 수준에 따라 차등. **자료 없으면 0에서 시작.**

```
if 매출 3년 제출:   goodwill = est_income_point × clamp(multiple, 1.0, 2.0)
elif 매출 1년 제출: goodwill = est_income_point × 0.5
else:               goodwill = 0
```

추가로 판로 안정성 가산(상한 있음):
- 계약재배 승계 가능: `+ est_income_point × 0.3`
- 직거래 채널 승계 가능: `+ est_income_point × 0.2`
- 공판장 출하만: `+ 0`
- 가산 합계는 `est_income_point × 0.5`로 캡.

> 영업권은 범위로만 제시하고 "자료 제출·실사 시 정밀화" 라벨 필수.

---

## 5. 인수 검토가 범위 (총합)

```
value_min = land_min + facility_min + goodwill_min - risk_discount_max
value_max = land_max + facility_max + goodwill_max - risk_discount_min
```

**리스크 할인 `risk_discount`** — 확인 안 된 위험을 검토가에서 차감(보수적):
- 시설 노후도 미확인(installed_year 결측 자산 존재): 시설가의 10~20%
- 최근 매출 자료 없음: 영업권 전액 불확실 → 이미 0이므로 추가 없음
- 권리관계(근저당 등) 미확인: 토지가의 0~5%
- 경제수령 초과 과수(tree_age > economic_life): 갱신비용 명목 토지가의 0~5%

```
value_min = MAX(value_min, land_min)   -- 하한은 최소 토지가(나무·시설이 음수 기여 방지)
```

최종 표시: 만원 단위 반올림, 항상 `min ~ max` 범위. 단일 숫자 표기 금지.

---

## 6. 신뢰도 등급 (confidence_grade)

| 등급 | 조건 | 표시 문구 |
|---|---|---|
| A | 매출 3년+시설목록+사진+권리관계+실사 | 실사 기반 추정 |
| B | 매출 일부+시설자료+인터뷰 | 농가 제출자료 기반 추정 |
| C | 공공데이터+기본 설문(수령·시설 입력) | 사전 검토용 추정 |
| D | 주소·면적만 | 참고용 자동 추정 |

자동 산출은 B부터 시작하며, `매출자료 + 설치연도가 확인된 시설목록`이 모두
있으면 B, 그 외 기본 설문은 C로 둔다. A는 사진·권리관계·현장 실사가 모두
필요하므로 자동 부여하지 않는다. 하향 트리거: 실거래 표본<3,
installed_year 결측, 공시지가만 존재 → 한 단계씩 down(최저 D).

---

## 7. 매칭 점수 (matching) — farm × young_farmer, 만점 100

```
region     = 20  if pref_sido == farm.sido            else (10 if 인접도 else 0)
crop       = 20  if pref_crop == farm.crop_code        else 0
capital    = 20  × clamp(available_capital / value_min, 0, 1)   -- 자본이 검토가 하한 충족도
experience = 15  × clamp(experience_years / 5, 0, 1)
succession = 15  if pref_succession == farm.succession_type else (8 if 호환 else 0)
policy     = 10  if (policy_fund and value_min within 정책자금 한도) else 5 if policy_fund else 0

risk_penalty = 0
  + 10 if available_capital < value_min × 0.5      -- 자본 현저 부족
  + 5  if (farm.crop_code 고난도 and experience_years == 0)

total = region+crop+capital+experience+succession+policy - risk_penalty   -- floor 0
```

- 승계방식 호환: JOINT↔MENTORING, LEASE↔JOINT 등은 부분점수(8). SALE↔LEASE는 0.
- 정책자금 한도: 청년창업농 융자 한도 등 정책 RAG 기준값(상수로 시작, 7월 RAG 연계).
- 양방향: 같은 점수를 청년농 화면(농장 추천)·농가 화면(후보 추천) 양쪽에서 사용.

---

## 8. 테스트 케이스 (pytest 우선 작성)

valuation.py 구현 **전에** 아래를 테스트로 고정한다.

| # | 시나리오 | 기대 |
|---|---|---|
| T1 | 사과 7년생 5,000㎡, 시설 없음, 매출 없음, 실거래 있음 | age_coef=1.0, goodwill=0, value_min≥land_min |
| T2 | 사과 3년생 5,000㎡ vs 7년생 동일조건 | 3년생 income·value가 7년생보다 작음 |
| T3 | 복숭아 3년생 | age_coef>0 (절벽 아님, 보정 확인) |
| T4 | 포도 25년생(경제수령 18 초과) | age_coef=post_life(0.35), 리스크할인 적용 |
| T5 | 저온저장고 10평 5년 경과 상태B | residual = new×(1-5/10)×0.85 |
| T6 | installed_year 결측 자산 포함 | dep_ratio=0.5, grade 하향 |
| T7 | 공시지가만(실거래 없음) | unit=official/0.65, grade 하향 |
| T8 | area_m2=0, tree_age=0 등 경계 | 0 division 없이 안전 반환 |
| T9 | value_min ≥ land_min 항상 성립 | 음수 기여 차단 검증 |
| T10 | 매칭: 완전일치 청년농 | total ≈ 95~100 |

---

## 9. 미확정 / 7월 보정 TODO

- [ ] `official_to_market` 0.65 — 3개 도 실거래/공시지가 비율 실측으로 보정
- [ ] 영업권 multiple 상한 2.0 — 농업 사업양수도 관행 확인
- [ ] 정책자금 한도 상수 — RAG 연계 시 동적화
- [x] skill_adj 매출→실측소득 환산식 — 소득조사의 작목별 평균 소득률 적용
