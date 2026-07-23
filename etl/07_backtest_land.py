"""토지 기준가 산식 백테스트 — 실거래 개별 건 vs 팜바톤 추정 범위.

발표 보완용 검증 스크립트 (2026-07 서면검토 지적 ④ 대응).

방법 (Leave-One-Out):
  각 실거래 건 T (법정동 D, 지목 J)에 대해
  1) D·J의 동(洞) 평균 단가를 T를 제외하고 재계산 (순환논리 방지)
  2) 팜바톤 산식 적용: point = T.area × LOO평균, 범위 = point×0.9 ~ point×1.1
     (backend/app/services/valuation.py calc_land_value와 동일)
  3) 실제 거래금액이 [min, max] 안이면 적중(hit)
  공시지가 폴백 경로(official / OFFICIAL_TO_MARKET)도 동일 방식으로 검증.

필터·집계는 etl/02_landprice.py의 함수를 그대로 import해 재사용한다
(적재본과 동일한 해제거래 제외·법정동 매핑·단가 계산 보장).

실행:  python etl/07_backtest_land.py            # 콘솔 요약
       python etl/07_backtest_land.py --report   # docs/backtest_land_report.md 생성
"""

from __future__ import annotations

import argparse
import importlib.util
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data" / "csv"

# ── 02_landprice.py 모듈 로드 (파일명이 숫자로 시작해 importlib 사용) ────────
_spec = importlib.util.spec_from_file_location("landprice_etl", ROOT / "etl" / "02_landprice.py")
_lp = importlib.util.module_from_spec(_spec)
sys.modules["landprice_etl"] = _lp  # dataclass가 모듈을 sys.modules에서 찾음
_spec.loader.exec_module(_lp)

# valuation.py와 동일한 상수 (import 시 psycopg2 의존이 없어 직접 import)
sys.path.insert(0, str(ROOT))
from backend.app.services.valuation import OFFICIAL_TO_MARKET  # noqa: E402

RANGE_LO = 0.9  # calc_land_value: min = point*0.9
RANGE_HI = 1.1  # calc_land_value: max = point*1.1

JIMOK_ORCHARD = "과수원"


@dataclass
class Deal:
    bjd_cd: str
    jimok: str
    province: str
    area_m2: Decimal
    amount_krw: Decimal   # 실제 거래금액(원)
    price_m2: Decimal     # 단가(원/㎡)


def collect_deals() -> list[Deal]:
    """02_landprice.py와 동일한 필터로 개별 거래 건을 수집한다."""
    legal_source, trade_source, _ = _lp.discover_sources(CSV_DIR, legal_dong_file=None, trade_file=None, official_files=None)
    exact_legal, normalized_legal, _ = _lp.build_legal_maps(legal_source)

    deals: list[Deal] = []
    for row in _lp.read_csv(trade_source):
        address = (row.get(_lp.COL_ADDR) or "").strip()
        if not any(address.startswith(name) for name in _lp.TARGET_PROVINCES):
            continue
        jimok = (row.get(_lp.COL_JIMOK) or "").strip()
        if jimok not in _lp.JIMOKS:
            continue
        if _lp.is_cancelled(row):
            continue
        bjd_cd = _lp.map_bjd_cd(address, exact_legal, normalized_legal)
        if not bjd_cd or bjd_cd[:2] not in _lp.TARGET_PREFIXES:
            continue
        area = _lp.decimal_from_text(row.get(_lp.COL_AREA))
        amount_manwon = _lp.decimal_from_text(row.get(_lp.COL_AMOUNT))
        if area is None or area <= 0 or amount_manwon is None or amount_manwon <= 0:
            continue
        if _lp.int_from_text(row.get(_lp.COL_CONTRACT_YM)) is None:
            continue
        amount_krw = amount_manwon * Decimal("10000")
        deals.append(Deal(
            bjd_cd=bjd_cd,
            jimok=jimok,
            province=_lp.PROVINCE_BY_PREFIX[bjd_cd[:2]],
            area_m2=area,
            amount_krw=amount_krw,
            price_m2=amount_krw / area,
        ))
    return deals


def load_official_prices() -> dict[tuple[str, str], Decimal]:
    """최신 기준연도 개별공시지가 (bjd_cd, jimok) → 원/㎡ 평균."""
    _, _, official_sources = _lp.discover_sources(CSV_DIR, legal_dong_file=None, trade_file=None, official_files=None)
    groups, _, latest_year = _lp.build_official_groups(official_sources)
    return {
        (bjd, jimok): total / count
        for (bjd, jimok, year), (total, count) in groups.items()
        if year == latest_year and count > 0
    }


@dataclass
class Result:
    n: int = 0
    hits: int = 0
    apes: list[float] = None  # absolute % error of point estimate

    def __post_init__(self):
        if self.apes is None:
            self.apes = []

    def add(self, point: Decimal, actual: Decimal) -> None:
        self.n += 1
        lo, hi = point * Decimal(str(RANGE_LO)), point * Decimal(str(RANGE_HI))
        if lo <= actual <= hi:
            self.hits += 1
        self.apes.append(abs(float(point) - float(actual)) / float(actual) * 100)

    @property
    def coverage(self) -> float:
        return self.hits / self.n * 100 if self.n else 0.0

    @property
    def median_ape(self) -> float:
        return statistics.median(self.apes) if self.apes else 0.0


def run_backtest(deals: list[Deal], official: dict[tuple[str, str], Decimal]):
    # 동·지목별 (단가합, 건수) — LOO 계산용
    sums: dict[tuple[str, str], list] = defaultdict(lambda: [Decimal("0"), 0])
    for d in deals:
        key = (d.bjd_cd, d.jimok)
        sums[key][0] += d.price_m2
        sums[key][1] += 1

    # 결과 버킷: (지목, 경로, 표본구간)
    loo_results: dict[tuple[str, str], Result] = defaultdict(Result)   # (jimok, "n>=3"|"n<3")
    official_results: dict[str, Result] = defaultdict(Result)          # jimok

    for d in deals:
        key = (d.bjd_cd, d.jimok)
        total, n = sums[key]
        # ── 실거래 경로 (LOO) ──
        if n >= 2:
            loo_unit = (total - d.price_m2) / (n - 1)
            point = d.area_m2 * loo_unit
            seg = "n>=3" if (n - 1) >= 3 else "n<3"
            loo_results[(d.jimok, seg)].add(point, d.amount_krw)
        # ── 공시지가 폴백 경로 ──
        off = official.get(key)
        if off is not None and off > 0:
            point = d.area_m2 * off / Decimal(str(OFFICIAL_TO_MARKET))
            official_results[d.jimok].add(point, d.amount_krw)

    return loo_results, official_results


def fmt_row(label: str, r: Result) -> str:
    return f"| {label} | {r.n:,} | {r.coverage:.1f}% | {r.median_ape:.1f}% |"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="docs/backtest_land_report.md 생성")
    args = parser.parse_args()

    deals = collect_deals()
    official = load_official_prices()
    loo, off = run_backtest(deals, official)

    orchard = [d for d in deals if d.jimok == JIMOK_ORCHARD]
    lines: list[str] = []
    w = lines.append

    w("# 토지 기준가 백테스트 결과")
    w("")
    w(f"- 검증 대상: 충북·경북·충남 실거래 {len(deals):,}건 (과수원 {len(orchard):,}건)")
    w("- 기간: 2023-06-17 ~ 2026-06-16 (국토부 실거래가, 해제거래 제외)")
    w("- 방법: Leave-One-Out — 각 거래를 제외하고 동(洞) 평균 단가를 재계산한 뒤,")
    w("  팜바톤 토지 산식(면적×단가, ±10% 범위)이 실제 거래금액을 포함하는지 판정")
    w("- 적중률 = 실제 거래가가 팜바톤 '인수 검토가 범위(토지)' 안에 들어온 비율")
    w("- 중앙오차 = 점추정 대비 실거래가의 절대 오차율 중앙값")
    w("")
    w("## 실거래 보정 경로 (동일 법정동 실거래 표본 사용 시)")
    w("")
    w("| 구간 | 검증 건수 | 범위 적중률 | 중앙오차 |")
    w("|---|---:|---:|---:|")
    for jimok in ("과수원", "전", "답"):
        for seg, seg_label in (("n>=3", "표본 3건 이상"), ("n<3", "표본 1~2건")):
            r = loo.get((jimok, seg))
            if r and r.n:
                w(fmt_row(f"{jimok} · {seg_label}", r))
    w("")
    w("## 공시지가 폴백 경로 (공시지가 ÷ 0.65)")
    w("")
    w("| 지목 | 검증 건수 | 범위 적중률 | 중앙오차 |")
    w("|---|---:|---:|---:|")
    for jimok in ("과수원", "전", "답"):
        r = off.get(jimok)
        if r and r.n:
            w(fmt_row(jimok, r))
    w("")
    w("> 주: 토지 부분만의 검증이다. 인수 검토가 전체(시설 잔존가·영업권 포함)의")
    w("> 범위는 이보다 넓으며, 시설·영업권은 실사 시 정밀화 대상이다.")

    report = "\n".join(lines)
    if args.report:
        out = ROOT / "docs" / "backtest_land_report.md"
        out.write_text(report + "\n", encoding="utf-8")
        print(f"saved: {out}")
    # 콘솔 (Windows cp949 콘솔 대비 ASCII-safe 출력)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(report)


if __name__ == "__main__":
    main()
