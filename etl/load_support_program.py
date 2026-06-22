"""Load support_program.csv into the support_program table.

Source CSV: db/seed/support_program.csv
Required columns: program_code, name, target_sido, target_crop, target_role,
description, amount_text, apply_url, source_refs
(target_sido/target_crop may be blank = NULL = 전국/전체 작목)

Default behavior is a dry run. Use --load to write to PostgreSQL.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

REQUIRED_COLUMNS = {
    "program_code", "name", "target_sido", "target_crop", "target_role",
    "description", "amount_text", "apply_url", "source_refs",
}
VALID_ROLES = {"YOUNG", "FARMER", "ANY"}
VALID_CROPS = {"APPLE", "PEACH", "GRAPE"}


class DataError(RuntimeError):
    pass


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate/load support_program.csv")
    parser.add_argument(
        "--csv-path", type=Path,
        default=project_root() / "db" / "seed" / "support_program.csv",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--load", action="store_true")
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise DataError(f"missing source file: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise DataError(f"empty CSV or missing header: {path}")
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames))
        if missing:
            raise DataError(f"{path.name} missing columns: {', '.join(missing)}")
        return list(reader)


def validate_rows(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise DataError("CSV has no data rows")
    for i, row in enumerate(rows, start=2):  # 1-based + header
        if not row["program_code"].strip():
            raise DataError(f"row {i}: blank program_code")
        if not row["name"].strip():
            raise DataError(f"row {i}: blank name")
        role = row["target_role"].strip()
        if role not in VALID_ROLES:
            raise DataError(f"row {i}: invalid target_role '{role}' (expected {VALID_ROLES})")
        crop = row["target_crop"].strip()
        if crop and crop not in VALID_CROPS:
            raise DataError(f"row {i}: invalid target_crop '{crop}' (expected blank or {VALID_CROPS})")
        if not row["description"].strip():
            raise DataError(f"row {i}: blank description")
        if not row["amount_text"].strip():
            raise DataError(f"row {i}: blank amount_text")
        if not row["source_refs"].strip():
            raise DataError(f"row {i}: blank source_refs")


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def upsert_rows(rows: list[dict[str, str]], database_url: str) -> None:
    import psycopg2

    sql = """
        INSERT INTO support_program (
            program_code, name, target_sido, target_crop, target_role,
            description, amount_text, apply_url, source_refs
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (program_code) DO UPDATE SET
            name = EXCLUDED.name,
            target_sido = EXCLUDED.target_sido,
            target_crop = EXCLUDED.target_crop,
            target_role = EXCLUDED.target_role,
            description = EXCLUDED.description,
            amount_text = EXCLUDED.amount_text,
            apply_url = EXCLUDED.apply_url,
            source_refs = EXCLUDED.source_refs
    """
    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(sql, (
                        row["program_code"].strip(),
                        row["name"].strip(),
                        row["target_sido"].strip() or None,
                        row["target_crop"].strip() or None,
                        row["target_role"].strip(),
                        row["description"].strip(),
                        row["amount_text"].strip(),
                        row["apply_url"].strip() or None,
                        row["source_refs"].strip(),
                    ))
    finally:
        conn.close()


def main() -> int:
    args = parse_args()
    try:
        rows = read_rows(args.csv_path)
        validate_rows(rows)
        for row in rows:
            print(f"{row['program_code']}: {row['name']} (sido={row['target_sido'] or '전국'}, crop={row['target_crop'] or '전체'})")

        if not args.load:
            print(f"DRY RUN: validated {len(rows)} rows. No DB changes.")
            return 0

        load_dotenv_file(project_root() / ".env")
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise DataError("DATABASE_URL is missing. Set it in .env or environment.")

        upsert_rows(rows, database_url)
        print(f"Loaded {len(rows)} rows into support_program.")
        return 0
    except DataError as exc:
        print(f"[DATA ERROR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
