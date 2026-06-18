"""Fetch KAMIS retail prices and upsert price_trend.trend_index.

For each of the 3 target crops (APPLE/PEACH/GRAPE), calls the KAMIS
periodProductList API for the most-traded representative variety, comparing
the most recent 30 days against the same 30-day window one year earlier.
There is no true "평년"(multi-year normal) endpoint in KAMIS Open-API, so the
year-over-year ratio is used as the closest available proxy, clamped to
[0.7, 1.3] to avoid overcorrecting on short-term volatility.

Default behavior is a dry run. Use --load to write to PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

KAMIS_ENDPOINT = "https://www.kamis.or.kr/service/price/xml.do"
RECENT_WINDOW_DAYS = 30
RETAIL_PRODUCT_CLASS = "01"
RETAIL_GRADE = "04"  # 상품. NOTE: the simplified "0/1/2" shown on the KAMIS
# website UI does not work as an API parameter value -- passing "0" returns
# error_code "001" (no data) for every query. "04" is the value the server
# itself defaults to when p_productrankcode is omitted, confirmed by
# live testing against the production endpoint.
FRUIT_CATEGORY = "400"

# crop_code -> (item_code, kind_code, variety label for source_refs)
CROPS = {
    "APPLE": ("411", "05", "후지"),
    "PEACH": ("413", "01", "백도"),
    "GRAPE": ("414", "12", "샤인머스켓"),
}

TREND_MIN = Decimal("0.7")
TREND_MAX = Decimal("1.3")
ROUND3 = Decimal("0.001")


class DataError(RuntimeError):
    """Raised when KAMIS data is missing or inconsistent."""


@dataclass(frozen=True)
class PriceTrendRow:
    crop_code: str
    trend_index: Decimal
    volatility: Decimal
    base_period: str
    source_refs: str


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch KAMIS retail prices and upsert price_trend."
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Reference date (YYYY-MM-DD) to treat as 'today'. Default: actual today.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print rows without writing to DB. This is the default.",
    )
    mode.add_argument(
        "--load",
        action="store_true",
        help="Upsert rows into price_trend using DATABASE_URL.",
    )
    return parser.parse_args()


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
            if key and key not in os.environ:
                os.environ[key] = value


def fetch_period_prices(
    cert_key: str,
    cert_id: str,
    item_code: str,
    kind_code: str,
    start: date,
    end: date,
) -> list[Decimal]:
    params = {
        "action": "periodProductList",
        "p_cert_key": cert_key,
        "p_cert_id": cert_id,
        "p_returntype": "json",
        "p_productclscode": RETAIL_PRODUCT_CLASS,
        "p_itemcategorycode": FRUIT_CATEGORY,
        "p_itemcode": item_code,
        "p_kindcode": kind_code,
        "p_productrankcode": RETAIL_GRADE,
        "p_startday": start.isoformat(),
        "p_endday": end.isoformat(),
    }
    url = f"{KAMIS_ENDPOINT}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except Exception as exc:
        raise DataError(f"KAMIS request failed: {exc}") from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise DataError(f"KAMIS response was not valid JSON: {exc}") from exc

    data = payload.get("data")
    if isinstance(data, list):
        code = data[0] if data else None
        if code == "001":
            raise DataError(
                f"KAMIS returned no data for item_code={item_code} "
                f"kind_code={kind_code} {start}~{end}"
            )
        raise DataError(f"KAMIS returned error code: {data}")

    if not isinstance(data, dict) or data.get("error_code") != "000":
        raise DataError(f"KAMIS returned unexpected payload: {payload}")

    prices: list[Decimal] = []
    for item in data.get("item", []):
        raw_price = str(item.get("price", "")).replace(",", "").strip()
        if raw_price in ("", "-"):
            continue
        try:
            prices.append(Decimal(raw_price))
        except Exception:
            continue

    if not prices:
        raise DataError(
            f"KAMIS returned zero usable price points for item_code={item_code} "
            f"kind_code={kind_code} {start}~{end}"
        )
    return prices


def clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(high, value))


def build_row(
    crop_code: str,
    item_code: str,
    kind_code: str,
    variety: str,
    cert_key: str,
    cert_id: str,
    as_of: date,
) -> PriceTrendRow:
    recent_end = as_of
    recent_start = as_of - timedelta(days=RECENT_WINDOW_DAYS - 1)
    prior_end = recent_end - timedelta(days=365)
    prior_start = recent_start - timedelta(days=365)

    recent_prices = fetch_period_prices(
        cert_key, cert_id, item_code, kind_code, recent_start, recent_end
    )
    prior_prices = fetch_period_prices(
        cert_key, cert_id, item_code, kind_code, prior_start, prior_end
    )

    recent_avg = sum(recent_prices) / len(recent_prices)
    prior_avg = sum(prior_prices) / len(prior_prices)
    if prior_avg == 0:
        raise DataError(f"prior-year average price was zero for {crop_code}")

    raw_trend = recent_avg / prior_avg
    trend_index = clamp(raw_trend, TREND_MIN, TREND_MAX).quantize(
        ROUND3, rounding=ROUND_HALF_UP
    )

    if len(recent_prices) > 1:
        recent_mean = float(recent_avg)
        cov = statistics.stdev(float(p) for p in recent_prices) / recent_mean
        volatility = Decimal(str(cov)).quantize(ROUND3, rounding=ROUND_HALF_UP)
    else:
        volatility = Decimal("0.000")

    base_period = (
        f"{recent_start.isoformat()}~{recent_end.isoformat()} 평균 vs "
        f"{prior_start.isoformat()}~{prior_end.isoformat()} 평균 (전년 동기 비교, "
        f"진짜 5개년 평년 데이터는 KAMIS Open-API에 없음)"
    )
    source_refs = json.dumps(
        {
            "api": "KAMIS periodProductList",
            "item_code": item_code,
            "kind_code": kind_code,
            "variety": variety,
            "product_class": "01(소매)",
            "product_rank_code": RETAIL_GRADE,
            "raw_trend_before_clamp": str(raw_trend),
            "recent_sample_count": len(recent_prices),
            "prior_sample_count": len(prior_prices),
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    return PriceTrendRow(
        crop_code=crop_code,
        trend_index=trend_index,
        volatility=volatility,
        base_period=base_period,
        source_refs=source_refs,
    )


def build_rows(
    cert_key: str, cert_id: str, as_of: date
) -> tuple[list[PriceTrendRow], dict[str, str]]:
    rows = []
    skipped: dict[str, str] = {}
    for crop_code, (item_code, kind_code, variety) in CROPS.items():
        try:
            rows.append(
                build_row(
                    crop_code, item_code, kind_code, variety, cert_key, cert_id, as_of
                )
            )
        except DataError as exc:
            skipped[crop_code] = str(exc)
    return rows, skipped


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


def upsert_rows(rows: list[PriceTrendRow], database_url: str) -> None:
    sql = """
        INSERT INTO price_trend (
            crop_code,
            trend_index,
            volatility,
            base_period,
            source_refs
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (crop_code) DO UPDATE SET
            trend_index = EXCLUDED.trend_index,
            volatility = EXCLUDED.volatility,
            base_period = EXCLUDED.base_period,
            source_refs = EXCLUDED.source_refs
    """

    conn = connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        sql,
                        (
                            row.crop_code,
                            row.trend_index,
                            row.volatility,
                            row.base_period,
                            row.source_refs,
                        ),
                    )
    finally:
        conn.close()


def print_rows(rows: list[PriceTrendRow]) -> None:
    print("crop_code,trend_index,volatility,base_period")
    for row in rows:
        print(f"{row.crop_code},{row.trend_index},{row.volatility},{row.base_period}")


def main() -> int:
    args = parse_args()

    try:
        load_dotenv(project_root() / ".env")
        cert_key = os.environ.get("KAMIS_CERT_KEY", "").strip()
        cert_id = os.environ.get("KAMIS_CERT_ID", "").strip()
        if not cert_key or not cert_id:
            raise DataError(
                "KAMIS_CERT_KEY / KAMIS_CERT_ID is missing. Set both in .env."
            )

        as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

        rows, skipped = build_rows(cert_key, cert_id, as_of)
        print_rows(rows)
        for crop_code, reason in skipped.items():
            print(f"[SKIPPED] {crop_code}: {reason}", file=sys.stderr)

        if not rows:
            raise DataError("No crops returned usable KAMIS data. Nothing to do.")

        if not args.load:
            print(
                f"DRY RUN: fetched {len(rows)} row(s), skipped {len(skipped)}. "
                "No DB changes."
            )
            return 0

        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise DataError("DATABASE_URL is missing. Set it in .env or environment.")

        upsert_rows(rows, database_url)
        print(
            f"Loaded {len(rows)} row(s) into price_trend "
            f"(skipped {len(skipped)}: {', '.join(skipped) or 'none'})."
        )
        return 0
    except DataError as exc:
        print(f"[DATA ERROR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
