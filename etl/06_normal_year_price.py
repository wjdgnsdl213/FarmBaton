"""Load KAMIS "평년"(normal-year) retail price into price_trend.

KAMIS Open-API has no multi-year normal-price endpoint (see 05_price_trend.py's
own comment). The KAMIS *website* ("소매가격 > 기간별") does show an official
"평년" row, defined as "5개년(금년 제외) 중 최고/최저 제외 3개년 평균" — which
is exactly the "3년 평균" the user originally asked for. There is no API for
this, so the 3 screens (사과/후지, 복숭아/백도, 포도/샤인머스켓 — same
item/variety/grade as 05_price_trend.py's CROPS) were downloaded by hand as
"엑셀다운로드" (HTML tables saved with an .xls extension) and committed as
static seed files under db/seed/.

This script parses those static files and upserts only normal_year_price /
price_unit / normal_year_source into price_trend — it never touches
trend_index/volatility/base_period/source_refs, which remain owned by
05_price_trend.py. Not used by valuation.py (rule 1); PDF narrative only.

Default behavior is a dry run. Use --load to write to PostgreSQL.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SEED_FILES = {
    "APPLE": "kamis_normal_year_apple.xls",
    "PEACH": "kamis_normal_year_peach.xls",
    "GRAPE": "kamis_normal_year_grape.xls",
}

_CAPTION_RE = re.compile(r"<caption>(.*?)</caption>", re.S)
_ROW_RE = re.compile(
    r'<th[^>]*class="first[^"]*"[^>]*>\s*([^<]+?)\s*(?:<button|</th>)'
    r".*?<td[^>]*>\s*([\d,]+|-)\s*</td>",
    re.S,
)


class DataError(RuntimeError):
    """Raised when a seed file is missing or doesn't match the expected shape."""


@dataclass(frozen=True)
class NormalYearRow:
    crop_code: str
    normal_year_price: float | None
    price_unit: str
    normal_year_source: str


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_caption(html: str) -> tuple[str, str, str, str]:
    """caption에서 (품목, 품종, 등급, 단위) 추출.

    원문 예: "소매가격<comma 없이 줄바꿈>과일류, 사과, 후지, 상품, 10개<줄바꿈>기간별/연간 가격정보"
    — 첫 조각엔 표 제목("소매가격")이 분류명과 공백으로 붙어 있고, 마지막 조각엔
    단위 뒤에 "기간별/연간 가격정보" 안내문이 공백으로 붙어 있어 콤마 분리만으로는
    바로 못 씀 — 공백 정규화 후 첫/끝 조각만 추가로 잘라낸다.
    """
    m = _CAPTION_RE.search(html)
    if not m:
        raise DataError("caption을 찾을 수 없음 — KAMIS 엑셀다운로드 형식이 바뀌었을 수 있음")
    parts = [re.sub(r"\s+", " ", p).strip() for p in m.group(1).split(",")]
    parts = [p for p in parts if p]
    if len(parts) != 5:
        raise DataError(f"caption 조각 수가 예상(5)과 다름: {parts!r}")
    _category_with_title, item, variety, grade, unit_with_suffix = parts
    unit = unit_with_suffix.split(" ")[0]
    return item, variety, grade, unit


def parse_normal_year_price(html: str) -> float | None:
    """'구분' 열이 '평년'인 행의 '평균' 값. '-'면 None(KAMIS가 산출 못 한 경우, 예: 포도)."""
    rows = _ROW_RE.findall(html)
    for label, value in rows:
        if label.strip() == "평년":
            if value == "-":
                return None
            return float(value.replace(",", ""))
    raise DataError("'평년' 행을 찾을 수 없음 — KAMIS 엑셀다운로드 형식이 바뀌었을 수 있음")


def build_row(crop_code: str, path: Path) -> NormalYearRow:
    if not path.exists():
        raise DataError(f"{path} 없음 — db/seed/에 KAMIS 엑셀다운로드 파일을 먼저 넣어야 함")

    html = path.read_text(encoding="utf-8")
    item, variety, grade, unit = parse_caption(html)
    price = parse_normal_year_price(html)

    source = (
        f"KAMIS 소매가격>기간별/연간 ({item}/{variety}/{grade}/{unit}), "
        f"평년=5개년(금년 제외) 중 최고·최저 제외 3개년 평균, "
        f"수동 다운로드 — {path.name}"
    )
    return NormalYearRow(
        crop_code=crop_code,
        normal_year_price=price,
        price_unit=unit,
        normal_year_source=source,
    )


def build_rows(seed_dir: Path) -> list[NormalYearRow]:
    return [build_row(crop_code, seed_dir / fname) for crop_code, fname in SEED_FILES.items()]


def connect(database_url: str):
    try:
        import psycopg

        return psycopg.connect(database_url)
    except ImportError:
        try:
            import psycopg2

            return psycopg2.connect(database_url)
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL driver not installed. Install psycopg or psycopg2."
            ) from exc


def upsert_rows(rows: list[NormalYearRow], database_url: str) -> None:
    sql = """
        INSERT INTO price_trend (
            crop_code, normal_year_price, price_unit, normal_year_source, source_refs
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (crop_code) DO UPDATE SET
            normal_year_price = EXCLUDED.normal_year_price,
            price_unit = EXCLUDED.price_unit,
            normal_year_source = EXCLUDED.normal_year_source
    """
    # source_refs는 ON CONFLICT의 SET 대상이 아니라 신규 INSERT 경로에서만 쓰이는
    # placeholder — 기존 행(예: APPLE)의 05_price_trend.py 출처 정보를 덮어쓰지 않음.
    placeholder_source_refs = "평년가만 적재됨 — KAMIS 시세지수(trend_index)는 05_price_trend.py 실행 후 채워짐"

    conn = connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        sql,
                        (
                            row.crop_code,
                            row.normal_year_price,
                            row.price_unit,
                            row.normal_year_source,
                            placeholder_source_refs,
                        ),
                    )
    finally:
        conn.close()


def print_rows(rows: list[NormalYearRow]) -> None:
    print("crop_code,normal_year_price,price_unit")
    for row in rows:
        print(f"{row.crop_code},{row.normal_year_price},{row.price_unit}")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in __import__("os").environ:
                __import__("os").environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load KAMIS normal-year ('평년') retail price into price_trend."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="Parse and print rows without writing. Default."
    )
    mode.add_argument(
        "--load", action="store_true", help="Upsert rows into price_trend using DATABASE_URL."
    )
    return parser.parse_args()


def main() -> int:
    import os

    args = parse_args()
    try:
        rows = build_rows(project_root() / "db" / "seed")
        print_rows(rows)

        if not args.load:
            print(f"DRY RUN: parsed {len(rows)} row(s). No DB changes.")
            return 0

        load_dotenv(project_root() / ".env")
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise DataError("DATABASE_URL is missing. Set it in .env or environment.")

        upsert_rows(rows, database_url)
        print(f"Loaded {len(rows)} row(s) into price_trend.")
        return 0
    except DataError as exc:
        print(f"[DATA ERROR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
