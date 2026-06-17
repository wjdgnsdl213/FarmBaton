"""Build and optionally load land_price from official land prices and deals.

Inputs are discovered from data/csv by CSV headers:
- official land price CSVs: bjd_cd, base year, jimok, official price
- land trade CSV: legal-dong address, jimok, contract area, deal amount
- legal-dong CSV: active legal-dong name to 10-digit code mapping

Default behavior is a dry run. Use --load to upsert into PostgreSQL.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable


COL_ADDR = "\uc2dc\uad70\uad6c"
COL_AMOUNT = "\uac70\ub798\uae08\uc561(\ub9cc\uc6d0)"
COL_AREA = "\uacc4\uc57d\uba74\uc801"
COL_BJD = "\ubc95\uc815\ub3d9\ucf54\ub4dc"
COL_CANCEL_DATE = "\ud574\uc81c\uc0ac\uc720\ubc1c\uc0dd\uc77c"
COL_CONTRACT_YM = "\uacc4\uc57d\ub144\uc6d4"
COL_DATA_DATE = "\ub370\uc774\ud130\uae30\uc900\uc77c\uc790"
COL_DELETED_AT = "\uc0ad\uc81c\uc77c\uc790"
COL_EUPMYEONDONG = "\uc74d\uba74\ub3d9\uba85"
COL_JIMOK = "\uc9c0\ubaa9"
COL_LEE = "\ub9ac\uba85"
COL_OFFICIAL_PRICE = "\uacf5\uc2dc\uc9c0\uac00"
COL_SIDO_NAME = "\uc2dc\ub3c4\uba85"
COL_SIGUNGU_NAME = "\uc2dc\uad70\uad6c\uba85"
COL_YEAR = "\uae30\uc900\uc5f0\ub3c4"

JIMOKS = frozenset(
    [
        "\uacfc\uc218\uc6d0",  # orchard
        "\uc804",  # dry field
        "\ub2f5",  # paddy field
    ]
)
PROVINCE_BY_PREFIX = {
    "43": "\ucda9\uccad\ubd81\ub3c4",
    "44": "\ucda9\uccad\ub0a8\ub3c4",
    "47": "\uacbd\uc0c1\ubd81\ub3c4",
}
TARGET_PREFIXES = frozenset(PROVINCE_BY_PREFIX)
TARGET_PROVINCES = frozenset(PROVINCE_BY_PREFIX.values())

LEGAL_REQUIRED_COLUMNS = frozenset(
    [COL_BJD, COL_SIDO_NAME, COL_SIGUNGU_NAME, COL_EUPMYEONDONG, COL_LEE, COL_DELETED_AT]
)
OFFICIAL_REQUIRED_COLUMNS = frozenset([COL_BJD, COL_YEAR, COL_JIMOK, COL_OFFICIAL_PRICE])
TRADE_REQUIRED_COLUMNS = frozenset(
    [COL_ADDR, COL_JIMOK, COL_CONTRACT_YM, COL_AREA, COL_AMOUNT]
)

MONEY_QUANT = Decimal("0.01")
ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")
NO_TEMP_ALTERNATIVE = "\uc5c6\uc74c \u2014 \ub300\uae30"


@dataclass(frozen=True)
class CsvSource:
    path: Path
    encoding: str
    columns: frozenset[str]


@dataclass(frozen=True)
class LandPriceRow:
    bjd_cd: str
    jimok: str
    official_price_m2: Decimal | None
    deal_price_m2: Decimal | None
    deal_sample_cnt: int
    base_year: int


class DataError(RuntimeError):
    """Raised when required source data is missing or inconsistent."""


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate official/deal land prices and upsert land_price."
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=project_root() / "data" / "csv",
        help="Directory containing land trade, official land price, and legal-dong CSVs.",
    )
    parser.add_argument(
        "--legal-dong-file",
        type=Path,
        help="Optional explicit legal-dong CSV path.",
    )
    parser.add_argument(
        "--trade-file",
        type=Path,
        help="Optional explicit land trade CSV path.",
    )
    parser.add_argument(
        "--official-file",
        action="append",
        dest="official_files",
        type=Path,
        help="Optional official land price CSV path. Repeat for multiple files.",
    )
    parser.add_argument(
        "--base-year",
        type=int,
        help="Official land price base year to load. Defaults to latest year found.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Number of sample output rows to print.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate CSVs and print aggregated rows without writing to DB. Default.",
    )
    mode.add_argument(
        "--load",
        action="store_true",
        help="Upsert rows into land_price using DATABASE_URL.",
    )
    return parser.parse_args()


def data_request(what: str, where: str, why: str, alternative: str) -> str:
    return (
        "[\ub370\uc774\ud130 \uc694\uccad]\n"
        f"- \ubb34\uc5c7\uc774: {what}\n"
        f"- \uc5b4\ub514\uc11c: {where}\n"
        f"- \uc65c: {why}\n"
        f"- \uc784\uc2dc \ub300\uc548: {alternative}"
    )


def sniff_csv(path: Path) -> CsvSource:
    if not path.exists():
        raise DataError(f"missing source file: {path}")

    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    raise DataError(f"empty CSV or missing header: {path}")
                return CsvSource(
                    path=path,
                    encoding=encoding,
                    columns=frozenset(reader.fieldnames),
                )
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    raise DataError(f"cannot decode CSV: {path} ({last_error})")


def read_csv(source: CsvSource) -> Iterable[dict[str, str]]:
    with source.path.open("r", encoding=source.encoding, newline="") as f:
        yield from csv.DictReader(f)


def discover_sources(
    csv_dir: Path,
    *,
    legal_dong_file: Path | None,
    trade_file: Path | None,
    official_files: list[Path] | None,
) -> tuple[CsvSource, CsvSource, list[CsvSource]]:
    if not csv_dir.exists():
        raise DataError(
            data_request(
                "data/csv directory with land price source CSVs",
                "Project data/csv directory",
                "ETL cannot discover official land price, land trade, and legal-dong files.",
                NO_TEMP_ALTERNATIVE,
            )
        )

    if legal_dong_file:
        legal_source = sniff_csv(resolve_source_path(csv_dir, legal_dong_file))
        validate_columns(legal_source, LEGAL_REQUIRED_COLUMNS, "legal-dong CSV")
    else:
        legal_candidates = [
            source
            for source in map(sniff_csv, sorted(csv_dir.glob("*.csv")))
            if LEGAL_REQUIRED_COLUMNS.issubset(source.columns)
        ]
        if len(legal_candidates) != 1:
            raise DataError(
                data_request(
                    "One legal-dong CSV with legal code/name/delete-date columns",
                    "Ministry legal-dong CSV or data/csv",
                    "Land trade rows need text legal-dong addresses mapped to 10-digit bjd_cd.",
                    NO_TEMP_ALTERNATIVE,
                )
            )
        legal_source = legal_candidates[0]

    if trade_file:
        trade_source = sniff_csv(resolve_source_path(csv_dir, trade_file))
        validate_columns(trade_source, TRADE_REQUIRED_COLUMNS, "land trade CSV")
    else:
        trade_candidates = [
            source
            for source in map(sniff_csv, sorted(csv_dir.glob("*.csv")))
            if TRADE_REQUIRED_COLUMNS.issubset(source.columns)
        ]
        if len(trade_candidates) != 1:
            raise DataError(
                data_request(
                    "One land trade CSV with address, jimok, contract area, and deal amount",
                    "MOLIT land trade CSV merged for Chungbuk/Chungnam/Gyeongbuk",
                    "deal_price_m2 cannot be computed without land trade source rows.",
                    NO_TEMP_ALTERNATIVE,
                )
            )
        trade_source = trade_candidates[0]

    if official_files:
        official_sources = [
            sniff_csv(resolve_source_path(csv_dir, path)) for path in official_files
        ]
        for source in official_sources:
            validate_columns(source, OFFICIAL_REQUIRED_COLUMNS, "official land price CSV")
    else:
        official_sources = [
            source
            for source in map(sniff_csv, sorted(csv_dir.glob("*.csv")))
            if OFFICIAL_REQUIRED_COLUMNS.issubset(source.columns)
        ]
        if not official_sources:
            raise DataError(
                data_request(
                    "Official land price CSV containing bjd_cd, jimok, base year, official price",
                    "Official land price dataset for Chungbuk/Chungnam/Gyeongbuk",
                    "official_price_m2 cannot be computed without the official price column.",
                    NO_TEMP_ALTERNATIVE,
                )
            )

    return legal_source, trade_source, official_sources


def resolve_source_path(csv_dir: Path, path: Path) -> Path:
    return path if path.is_absolute() else csv_dir / path


def validate_columns(source: CsvSource, required: frozenset[str], label: str) -> None:
    missing = sorted(required - source.columns)
    if missing:
        raise DataError(f"{label} missing columns: {', '.join(missing)}")


def decimal_from_text(value: str | None) -> Decimal | None:
    text = (value or "").strip().replace(",", "")
    if text in {"", "-"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def int_from_text(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text.isdigit():
        return None
    return int(text)


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def normalize_address(value: str) -> str:
    return "".join(value.split())


def is_cancelled(row: dict[str, str]) -> bool:
    value = (row.get(COL_CANCEL_DATE) or "").strip()
    return value not in {"", "-"}


def build_legal_maps(source: CsvSource) -> tuple[dict[str, str], dict[str, str], Counter[str]]:
    exact: dict[str, str] = {}
    normalized: dict[str, str] = {}
    stats: Counter[str] = Counter()

    for row in read_csv(source):
        stats["legal.rows.total"] += 1
        if (row.get(COL_DELETED_AT) or "").strip():
            stats["legal.rows.deleted"] += 1
            continue

        bjd_cd = (row.get(COL_BJD) or "").strip()
        if len(bjd_cd) != 10 or not bjd_cd.isdigit():
            stats["legal.rows.bad_code"] += 1
            continue

        parts = [
            row.get(COL_SIDO_NAME),
            row.get(COL_SIGUNGU_NAME),
            row.get(COL_EUPMYEONDONG),
            row.get(COL_LEE),
        ]
        full_name = " ".join((part or "").strip() for part in parts if (part or "").strip())
        if not full_name:
            stats["legal.rows.blank_name"] += 1
            continue

        existing = exact.get(full_name)
        if existing and existing != bjd_cd:
            raise DataError(f"ambiguous legal-dong name: {full_name}")
        exact[full_name] = bjd_cd

        normalized_name = normalize_address(full_name)
        existing_normalized = normalized.get(normalized_name)
        if existing_normalized and existing_normalized != bjd_cd:
            raise DataError(f"ambiguous normalized legal-dong name: {full_name}")
        normalized[normalized_name] = bjd_cd
        stats["legal.rows.active_mapped"] += 1

    return exact, normalized, stats


def map_bjd_cd(
    address: str,
    exact: dict[str, str],
    normalized: dict[str, str],
) -> str | None:
    return exact.get(address) or normalized.get(normalize_address(address))


def build_official_groups(
    sources: list[CsvSource],
) -> tuple[dict[tuple[str, str, int], tuple[Decimal, int]], Counter[str], int]:
    sums: defaultdict[tuple[str, str, int], list[Decimal | int]] = defaultdict(
        lambda: [Decimal("0"), 0]
    )
    stats: Counter[str] = Counter()
    years: Counter[int] = Counter()
    target_prefixes_seen: set[str] = set()

    for source in sources:
        stats["official.files"] += 1
        stats[f"official.file.{source.path.name}.encoding.{source.encoding}"] += 1
        for row in read_csv(source):
            stats["official.rows.total"] += 1
            bjd_cd = (row.get(COL_BJD) or "").strip()
            if len(bjd_cd) != 10 or not bjd_cd.isdigit():
                stats["official.rows.bad_bjd_cd"] += 1
                continue

            prefix = bjd_cd[:2]
            if prefix not in TARGET_PREFIXES:
                stats["official.rows.outside_region"] += 1
                continue

            year = int_from_text(row.get(COL_YEAR))
            if year is None:
                stats["official.rows.bad_base_year"] += 1
                continue
            years[year] += 1

            price = decimal_from_text(row.get(COL_OFFICIAL_PRICE))
            if price is None or price <= 0:
                stats["official.rows.bad_price"] += 1
                continue

            jimok = (row.get(COL_JIMOK) or "").strip()
            if jimok not in JIMOKS:
                stats["official.rows.skipped_jimok"] += 1
                continue

            target_prefixes_seen.add(prefix)
            stats[f"official.rows.jimok.{jimok}"] += 1
            if row.get(COL_DATA_DATE):
                stats[f"official.data_date.{row[COL_DATA_DATE].strip()}"] += 1

            key = (bjd_cd, jimok, year)
            sums[key][0] = sums[key][0] + price
            sums[key][1] = int(sums[key][1]) + 1

    missing_prefixes = TARGET_PREFIXES - target_prefixes_seen
    if missing_prefixes:
        missing_names = ", ".join(PROVINCE_BY_PREFIX[p] for p in sorted(missing_prefixes))
        raise DataError(
            data_request(
                f"Official land price rows for {missing_names}",
                "Official land price CSVs for all MVP provinces",
                "land_price must cover Chungbuk, Chungnam, and Gyeongbuk.",
                NO_TEMP_ALTERNATIVE,
            )
        )
    if not years:
        raise DataError(
            data_request(
                "Official land price base year values",
                "Official land price CSV 기준연도 column",
                "land_price.base_year cannot be selected without 기준연도.",
                NO_TEMP_ALTERNATIVE,
            )
        )

    latest_year = max(years)
    stats.update({f"official.base_year.{year}": count for year, count in years.items()})
    return {key: (values[0], int(values[1])) for key, values in sums.items()}, stats, latest_year


def build_trade_groups(
    source: CsvSource,
    exact_legal: dict[str, str],
    normalized_legal: dict[str, str],
) -> tuple[dict[tuple[str, str], tuple[Decimal, int]], Counter[str], list[tuple[str, int]]]:
    sums: defaultdict[tuple[str, str], list[Decimal | int]] = defaultdict(
        lambda: [Decimal("0"), 0]
    )
    stats: Counter[str] = Counter()
    unmatched: Counter[str] = Counter()
    target_prefixes_seen: set[str] = set()

    stats[f"trade.file.{source.path.name}.encoding.{source.encoding}"] += 1
    for row in read_csv(source):
        stats["trade.rows.total"] += 1
        address = (row.get(COL_ADDR) or "").strip()
        if not any(address.startswith(name) for name in TARGET_PROVINCES):
            stats["trade.rows.outside_region"] += 1
            continue

        jimok = (row.get(COL_JIMOK) or "").strip()
        if jimok not in JIMOKS:
            stats["trade.rows.skipped_jimok"] += 1
            continue

        if is_cancelled(row):
            stats["trade.rows.cancelled"] += 1
            continue

        bjd_cd = map_bjd_cd(address, exact_legal, normalized_legal)
        if not bjd_cd:
            stats["trade.rows.unmatched_legal_dong"] += 1
            unmatched[address] += 1
            continue

        prefix = bjd_cd[:2]
        if prefix not in TARGET_PREFIXES:
            stats["trade.rows.mapped_outside_region"] += 1
            continue

        area_m2 = decimal_from_text(row.get(COL_AREA))
        deal_amount_manwon = decimal_from_text(row.get(COL_AMOUNT))
        if area_m2 is None or area_m2 <= 0:
            stats["trade.rows.bad_area"] += 1
            continue
        if deal_amount_manwon is None or deal_amount_manwon <= 0:
            stats["trade.rows.bad_amount"] += 1
            continue
        if int_from_text(row.get(COL_CONTRACT_YM)) is None:
            stats["trade.rows.bad_contract_ym"] += 1
            continue

        price_m2 = deal_amount_manwon * Decimal("10000") / area_m2
        key = (bjd_cd, jimok)
        sums[key][0] = sums[key][0] + price_m2
        sums[key][1] = int(sums[key][1]) + 1
        target_prefixes_seen.add(prefix)
        stats[f"trade.rows.jimok.{jimok}"] += 1

    missing_prefixes = TARGET_PREFIXES - target_prefixes_seen
    if missing_prefixes:
        missing_names = ", ".join(PROVINCE_BY_PREFIX[p] for p in sorted(missing_prefixes))
        raise DataError(
            data_request(
                f"Land trade rows for {missing_names}",
                "MOLIT land trade CSV for all MVP provinces",
                "deal_price_m2 must be computed from Chungbuk, Chungnam, and Gyeongbuk trades.",
                NO_TEMP_ALTERNATIVE,
            )
        )

    return (
        {key: (values[0], int(values[1])) for key, values in sums.items()},
        stats,
        unmatched.most_common(20),
    )


def build_rows(
    csv_dir: Path,
    *,
    legal_dong_file: Path | None = None,
    trade_file: Path | None = None,
    official_files: list[Path] | None = None,
    base_year: int | None = None,
) -> tuple[list[LandPriceRow], dict[str, object]]:
    legal_source, trade_source, official_sources = discover_sources(
        csv_dir,
        legal_dong_file=legal_dong_file,
        trade_file=trade_file,
        official_files=official_files,
    )

    exact_legal, normalized_legal, legal_stats = build_legal_maps(legal_source)
    official_groups, official_stats, latest_year = build_official_groups(official_sources)
    selected_year = base_year or latest_year
    trade_groups, trade_stats, top_unmatched = build_trade_groups(
        trade_source,
        exact_legal,
        normalized_legal,
    )

    selected_official = {
        (bjd_cd, jimok): (sum_price, count)
        for (bjd_cd, jimok, year), (sum_price, count) in official_groups.items()
        if year == selected_year
    }
    if not selected_official:
        raise DataError(f"no official land price rows for base_year={selected_year}")

    keys = sorted(set(selected_official) | set(trade_groups))
    rows: list[LandPriceRow] = []
    for key in keys:
        official_sum_count = selected_official.get(key)
        deal_sum_count = trade_groups.get(key)
        official_price = (
            money(official_sum_count[0] / official_sum_count[1])
            if official_sum_count
            else None
        )
        deal_price = (
            money(deal_sum_count[0] / deal_sum_count[1]) if deal_sum_count else None
        )
        rows.append(
            LandPriceRow(
                bjd_cd=key[0],
                jimok=key[1],
                official_price_m2=official_price,
                deal_price_m2=deal_price,
                deal_sample_cnt=deal_sum_count[1] if deal_sum_count else 0,
                base_year=selected_year,
            )
        )

    stats = Counter()
    stats.update(legal_stats)
    stats.update(official_stats)
    stats.update(trade_stats)
    stats["output.rows"] = len(rows)
    stats["output.rows.with_official_price"] = sum(1 for row in rows if row.official_price_m2 is not None)
    stats["output.rows.with_deal_price"] = sum(1 for row in rows if row.deal_price_m2 is not None)
    stats["output.rows.with_both_prices"] = sum(
        1
        for row in rows
        if row.official_price_m2 is not None and row.deal_price_m2 is not None
    )

    report = {
        "base_year": selected_year,
        "sources": {
            "legal_dong": str(legal_source.path),
            "land_trade": str(trade_source.path),
            "official_land_price": [str(source.path) for source in official_sources],
        },
        "stats": dict(sorted(stats.items())),
        "top_unmatched_trade_addresses": top_unmatched,
    }
    return rows, report


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


UPSERT_CHUNK = 200


def upsert_rows(rows: list[LandPriceRow], database_url: str) -> tuple[int, list[tuple]]:
    upsert_tmpl = (
        "INSERT INTO land_price "
        "(bjd_cd, jimok, official_price_m2, deal_price_m2, deal_sample_cnt, base_year) "
        "VALUES {placeholders} "
        "ON CONFLICT (bjd_cd, jimok, base_year) DO UPDATE SET "
        "official_price_m2 = EXCLUDED.official_price_m2, "
        "deal_price_m2 = EXCLUDED.deal_price_m2, "
        "deal_sample_cnt = EXCLUDED.deal_sample_cnt"
    )
    count_sql = "SELECT COUNT(*) FROM land_price WHERE base_year = %s"
    sample_sql = """
        SELECT bjd_cd, jimok, official_price_m2, deal_price_m2, deal_sample_cnt, base_year
        FROM land_price
        WHERE base_year = %s
        ORDER BY bjd_cd, jimok
        LIMIT 10
    """

    conn = connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                for i in range(0, len(rows), UPSERT_CHUNK):
                    chunk = rows[i : i + UPSERT_CHUNK]
                    placeholders = ",".join(["(%s,%s,%s,%s,%s,%s)"] * len(chunk))
                    params: list = []
                    for row in chunk:
                        params.extend(
                            [
                                row.bjd_cd,
                                row.jimok,
                                row.official_price_m2,
                                row.deal_price_m2,
                                row.deal_sample_cnt,
                                row.base_year,
                            ]
                        )
                    cur.execute(upsert_tmpl.format(placeholders=placeholders), params)
                cur.execute(count_sql, (rows[0].base_year,))
                loaded_count = cur.fetchone()[0]
                cur.execute(sample_sql, (rows[0].base_year,))
                sample = cur.fetchall()
        return loaded_count, sample
    finally:
        conn.close()


def format_decimal(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def print_rows(rows: list[LandPriceRow], limit: int) -> None:
    print("bjd_cd,jimok,official_price_m2,deal_price_m2,deal_sample_cnt,base_year")
    for row in rows[:limit]:
        print(
            ",".join(
                [
                    row.bjd_cd,
                    row.jimok,
                    format_decimal(row.official_price_m2),
                    format_decimal(row.deal_price_m2),
                    str(row.deal_sample_cnt),
                    str(row.base_year),
                ]
            )
        )


def main() -> int:
    args = parse_args()

    try:
        rows, report = build_rows(
            args.csv_dir,
            legal_dong_file=args.legal_dong_file,
            trade_file=args.trade_file,
            official_files=args.official_files,
            base_year=args.base_year,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        print_rows(rows, args.sample_limit)

        if not args.load:
            print(f"DRY RUN: validated {len(rows)} rows. No DB changes.")
            return 0

        load_dotenv(project_root() / ".env")
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise DataError("DATABASE_URL is missing. Set it in .env or environment.")

        loaded_count, sample = upsert_rows(rows, database_url)
        print(f"Loaded {len(rows)} rows into land_price.")
        print(f"SELECT COUNT(*) FROM land_price WHERE base_year = {rows[0].base_year};")
        print(loaded_count)
        print("sample rows:")
        for item in sample:
            print(item)
        return 0
    except DataError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
