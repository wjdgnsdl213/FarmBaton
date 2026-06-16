"""Load fruit income coefficients into income_coef.

Source CSVs are prepared from the agricultural product income survey:
- data/csv/fruit_metrics.csv: income metric rows
- data/csv/fruit_costs_long.csv: gross revenue total rows

Default behavior is a dry run. Use --load to write to PostgreSQL.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


BASE_YEAR = 2024
CROP_CODE_BY_KEY = {
    "사과": "APPLE",
    "복숭아": "PEACH",
    "포도": "GRAPE",
}

METRICS_FILE = "fruit_metrics.csv"
COSTS_FILE = "fruit_costs_long.csv"

REQUIRED_METRIC_COLUMNS = {
    "year",
    "crop_key",
    "crop_name",
    "basis",
    "source_file",
    "source_csv",
    "source_row_1based",
    "metric_code",
    "metric_name_ko",
    "value_numeric",
    "unit",
}
REQUIRED_COST_COLUMNS = {
    "year",
    "crop_key",
    "crop_name",
    "basis",
    "source_file",
    "source_csv",
    "source_row_1based",
    "item_code",
    "item_name_ko",
    "amount_krw",
}


@dataclass(frozen=True)
class SourceRef:
    source_file: str
    source_csv: str
    source_row_1based: int
    field: str


@dataclass(frozen=True)
class IncomeCoefRow:
    crop_code: str
    crop_key: str
    crop_name: str
    avg_income_10a: Decimal
    avg_gross_10a: Decimal
    base_year: int
    source_refs: str


class DataError(RuntimeError):
    """Raised when source data is missing or inconsistent."""


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract 10a income coefficients and upsert income_coef."
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=project_root() / "data" / "csv",
        help="Directory containing fruit_metrics.csv and fruit_costs_long.csv.",
    )
    parser.add_argument(
        "--base-year",
        type=int,
        default=BASE_YEAR,
        help="Survey year to load. Default: 2024.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate CSVs and print rows without writing to DB. This is the default.",
    )
    mode.add_argument(
        "--load",
        action="store_true",
        help="Upsert rows into income_coef using DATABASE_URL.",
    )
    return parser.parse_args()


def read_csv(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    if not path.exists():
        raise DataError(f"missing source file: {path}")

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise DataError(f"empty CSV or missing header: {path}")

        missing = sorted(required_columns - set(reader.fieldnames))
        if missing:
            raise DataError(f"{path.name} missing columns: {', '.join(missing)}")

        return list(reader)


def decimal_from_row(row: dict[str, str], column: str, label: str) -> Decimal:
    value = (row.get(column) or "").strip()
    if value == "":
        raise DataError(f"blank numeric value for {label}.{column}")

    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise DataError(f"invalid numeric value for {label}.{column}: {value}") from exc


def int_from_row(row: dict[str, str], column: str, label: str) -> int:
    value = (row.get(column) or "").strip()
    if value == "":
        raise DataError(f"blank integer value for {label}.{column}")

    try:
        return int(value)
    except ValueError as exc:
        raise DataError(f"invalid integer value for {label}.{column}: {value}") from exc


def select_one(
    rows: Iterable[dict[str, str]],
    *,
    crop_key: str,
    year: int,
    code_column: str,
    code_value: str,
) -> dict[str, str]:
    matches = [
        row
        for row in rows
        if row["crop_key"] == crop_key
        and row["year"] == str(year)
        and row[code_column] == code_value
    ]

    if not matches:
        raise DataError(
            f"missing row: crop_key={crop_key}, year={year}, "
            f"{code_column}={code_value}"
        )
    if len(matches) > 1:
        raise DataError(
            f"duplicate rows: crop_key={crop_key}, year={year}, "
            f"{code_column}={code_value}, count={len(matches)}"
        )
    return matches[0]


def make_source_refs(income_row: dict[str, str], gross_row: dict[str, str]) -> str:
    refs = {
        "avg_income_10a": SourceRef(
            source_file=income_row["source_file"],
            source_csv=income_row["source_csv"],
            source_row_1based=int_from_row(
                income_row, "source_row_1based", "income source"
            ),
            field="fruit_metrics.value_numeric(metric_code=income)",
        ).__dict__,
        "avg_gross_10a": SourceRef(
            source_file=gross_row["source_file"],
            source_csv=gross_row["source_csv"],
            source_row_1based=int_from_row(
                gross_row, "source_row_1based", "gross source"
            ),
            field="fruit_costs_long.amount_krw(item_code=gross_revenue_total)",
        ).__dict__,
    }
    return json.dumps(refs, ensure_ascii=False, sort_keys=True)


def build_rows(csv_dir: Path, base_year: int) -> list[IncomeCoefRow]:
    metrics = read_csv(csv_dir / METRICS_FILE, REQUIRED_METRIC_COLUMNS)
    costs = read_csv(csv_dir / COSTS_FILE, REQUIRED_COST_COLUMNS)

    output: list[IncomeCoefRow] = []
    for crop_key, crop_code in CROP_CODE_BY_KEY.items():
        income_row = select_one(
            metrics,
            crop_key=crop_key,
            year=base_year,
            code_column="metric_code",
            code_value="income",
        )
        gross_row = select_one(
            costs,
            crop_key=crop_key,
            year=base_year,
            code_column="item_code",
            code_value="gross_revenue_total",
        )

        if income_row["unit"] != "KRW/10a":
            raise DataError(
                f"unexpected income unit for {crop_key}: {income_row['unit']}"
            )
        if income_row["basis"] != "년/10a" or gross_row["basis"] != "년/10a":
            raise DataError(
                f"unexpected basis for {crop_key}: "
                f"income={income_row['basis']}, gross={gross_row['basis']}"
            )

        output.append(
            IncomeCoefRow(
                crop_code=crop_code,
                crop_key=crop_key,
                crop_name=income_row["crop_name"],
                avg_income_10a=decimal_from_row(
                    income_row, "value_numeric", f"{crop_key} income"
                ),
                avg_gross_10a=decimal_from_row(
                    gross_row, "amount_krw", f"{crop_key} gross"
                ),
                base_year=base_year,
                source_refs=make_source_refs(income_row, gross_row),
            )
        )

    return output


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


def upsert_rows(rows: list[IncomeCoefRow], database_url: str) -> None:
    sql = """
        INSERT INTO income_coef (
            crop_code,
            avg_income_10a,
            avg_gross_10a,
            base_year,
            source_refs
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (crop_code) DO UPDATE SET
            avg_income_10a = EXCLUDED.avg_income_10a,
            avg_gross_10a = EXCLUDED.avg_gross_10a,
            base_year = EXCLUDED.base_year,
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
                            row.avg_income_10a,
                            row.avg_gross_10a,
                            row.base_year,
                            row.source_refs,
                        ),
                    )
    finally:
        conn.close()


def print_rows(rows: list[IncomeCoefRow]) -> None:
    print("crop_code,crop_key,crop_name,avg_income_10a,avg_gross_10a,base_year")
    for row in rows:
        print(
            ",".join(
                [
                    row.crop_code,
                    row.crop_key,
                    row.crop_name,
                    str(row.avg_income_10a),
                    str(row.avg_gross_10a),
                    str(row.base_year),
                ]
            )
        )


def main() -> int:
    args = parse_args()

    try:
        rows = build_rows(args.csv_dir, args.base_year)
        print_rows(rows)

        if not args.load:
            print(f"DRY RUN: validated {len(rows)} rows. No DB changes.")
            return 0

        load_dotenv(project_root() / ".env")
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise DataError("DATABASE_URL is missing. Set it in .env or environment.")

        upsert_rows(rows, database_url)
        print(f"Loaded {len(rows)} rows into income_coef.")
        return 0
    except DataError as exc:
        print(f"[DATA ERROR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
