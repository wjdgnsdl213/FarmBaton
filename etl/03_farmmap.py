"""Load farmmap SHP parcels (orchard classification only) into the parcel table.

Source SHP files (auto-discovered under data/shp):
  FARM_MAP_A/FARM_1.shp  — 경북 일부
  FARM_MAP_A/FARM_2.shp  — 경북 전체
  FARM_MAP_B/FARM_7.shp  — 충남 주요
  FARM_MAP_B/FARM_8.shp  — 충북·충남·경북 혼합

Filter  : INTPR_CD == '03' (과수) AND province prefix in {43=충북, 44=충남, 47=경북}
CRS     : EPSG:5179 → EPSG:4326 (geometry stored as MultiPolygon 4326)
Default : dry-run (validate only).  --load: TRUNCATE parcel + INSERT.
          --append: INSERT without TRUNCATE (incremental update).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import Generator

import geopandas as gpd
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.validation import make_valid

# ── constants ──────────────────────────────────────────────────────────────

TARGET_SHP_REL = [
    "FARM_MAP_A/FARM_1.shp",
    "FARM_MAP_A/FARM_2.shp",
    "FARM_MAP_B/FARM_7.shp",
    "FARM_MAP_B/FARM_8.shp",
]

ORCHARD_CODE = "03"
TARGET_PROV = {"43": "충북", "44": "충남", "47": "경북"}

COL_BJD        = "법정동코드"
COL_SIGUNGU_NM = "시군구명"
COL_DELETED_AT = "삭제일자"

ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")
CHUNK = 200   # rows per INSERT; geometry data is large so keep small

INSERT_SQL_TMPL = (
    "INSERT INTO parcel (pnu, bjd_cd, sido, sigungu, fmap_category, area_m2, geom) "
    "VALUES {ph}"
)
ROW_PH = "(%s,%s,%s,%s,%s,%s,ST_GeomFromWKB(decode(%s,'hex'),4326))"


# ── helpers ────────────────────────────────────────────────────────────────

class DataError(RuntimeError):
    pass


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load farmmap SHP → parcel table.")
    p.add_argument("--shp-dir", type=Path, default=project_root() / "data" / "shp")
    p.add_argument("--csv-dir", type=Path, default=project_root() / "data" / "csv")
    p.add_argument("--legal-dong-file", type=Path,
                   help="Explicit legal-dong CSV path (relative to --csv-dir or absolute).")
    p.add_argument("--sample-limit", type=int, default=5)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--load", action="store_true",
                      help="TRUNCATE parcel then INSERT all rows.")
    mode.add_argument("--append", action="store_true",
                      help="INSERT without TRUNCATE (incremental).")
    return p.parse_args()


def sniff_encoding(path: Path) -> str:
    for enc in ENCODINGS:
        try:
            with path.open("r", encoding=enc) as f:
                f.read(4096)
            return enc
        except UnicodeDecodeError:
            continue
    raise DataError(f"cannot decode: {path}")


def build_sigungu_map(legal_dong_path: Path) -> dict[str, str]:
    """Return {5-digit sigungu code → sigungu name} from active legal-dong rows."""
    enc = sniff_encoding(legal_dong_path)
    mapping: dict[str, str] = {}
    with legal_dong_path.open("r", encoding=enc, newline="") as f:
        for row in csv.DictReader(f):
            bjd = (row.get(COL_BJD) or "").strip()
            if len(bjd) != 10 or not bjd.isdigit():
                continue
            if (row.get(COL_DELETED_AT) or "").strip():
                continue
            nm = (row.get(COL_SIGUNGU_NM) or "").strip()
            if nm:
                mapping.setdefault(bjd[:5], nm)
    return mapping


def discover_legal_dong(csv_dir: Path, explicit: Path | None) -> Path:
    if explicit:
        return explicit if explicit.is_absolute() else csv_dir / explicit
    required = {COL_BJD, COL_SIGUNGU_NM, COL_DELETED_AT}
    for cand in sorted(csv_dir.glob("*.csv")):
        try:
            enc = sniff_encoding(cand)
            with cand.open("r", encoding=enc, newline="") as f:
                hdr = set(csv.DictReader(f).fieldnames or [])
            if required.issubset(hdr):
                return cand
        except Exception:
            continue
    raise DataError(
        "[데이터 요청]\n"
        "- 무엇이: 법정동코드·시군구명·삭제일자 컬럼을 가진 법정동 CSV\n"
        "- 어디서: data/csv/ 디렉터리\n"
        "- 왜: sigungu 이름 매핑 필요\n"
        "- 임시 대안: --legal-dong-file 로 직접 지정"
    )


def to_multipolygon(geom) -> MultiPolygon | None:
    """Convert any geometry to MultiPolygon; return None if no polygon content."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, GeometryCollection):
        polys: list[Polygon] = []
        for g in geom.geoms:
            if isinstance(g, Polygon):
                polys.append(g)
            elif isinstance(g, MultiPolygon):
                polys.extend(g.geoms)
        return MultiPolygon(polys) if polys else None
    return None


def iter_shp(
    shp_path: Path,
    sigungu_map: dict[str, str],
    stats: Counter,
) -> Generator[dict, None, None]:
    """Yield one parcel dict per qualifying feature in shp_path."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gdf = gpd.read_file(shp_path)

    total = len(gdf)
    stats[f"shp.{shp_path.name}.rows_read"] += total

    gdf = gdf[gdf["INTPR_CD"] == ORCHARD_CODE]
    stats[f"shp.{shp_path.name}.rows_orchard"] += len(gdf)

    gdf = gdf[gdf["LGL_EMD_CD"].notna()]
    gdf = gdf[gdf["LGL_EMD_CD"].str[:2].isin(TARGET_PROV)]
    stats[f"shp.{shp_path.name}.rows_target"] += len(gdf)

    if gdf.empty:
        return

    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    pnu_arr     = gdf["PNU_LNM_CD"].to_numpy()
    bjd_arr     = gdf["LGL_EMD_CD"].to_numpy()
    intprnm_arr = gdf["INTPR_NM"].to_numpy()
    area_arr    = gdf["AREA"].to_numpy()
    geom_arr    = gdf.geometry.to_numpy()

    for i in range(len(gdf)):
        geom = geom_arr[i]
        if geom is None or geom.is_empty:
            stats["skip.null_geom"] += 1
            continue
        if not geom.is_valid:
            geom = make_valid(geom)
            stats["fixed.invalid_geom"] += 1
        mp = to_multipolygon(geom)
        if mp is None:
            stats["skip.non_polygon"] += 1
            continue

        bjd_raw = bjd_arr[i]
        bjd_cd  = str(bjd_raw).strip() if bjd_raw is not None and str(bjd_raw) != "nan" else ""
        prov    = bjd_cd[:2] if len(bjd_cd) >= 2 else ""
        sg_code = bjd_cd[:5] if len(bjd_cd) >= 5 else ""
        pnu_raw = pnu_arr[i]
        pnu     = str(pnu_raw).strip() if pnu_raw is not None and str(pnu_raw) != "nan" else None
        nm_raw  = intprnm_arr[i]
        cat     = str(nm_raw).strip() if nm_raw is not None and str(nm_raw) != "nan" else "과수"
        area    = float(area_arr[i]) if area_arr[i] is not None else 0.0

        stats[f"prov.{TARGET_PROV.get(prov, prov)}"] += 1

        yield {
            "pnu":           pnu if pnu else None,
            "bjd_cd":        bjd_cd if bjd_cd else None,
            "sido":          TARGET_PROV.get(prov, ""),
            "sigungu":       sigungu_map.get(sg_code),
            "fmap_category": cat,
            "area_m2":       area,
            "geom_wkb_hex":  mp.wkb_hex,
        }


def all_rows(
    shp_dir: Path,
    sigungu_map: dict[str, str],
    stats: Counter,
    sample: list[dict],
    sample_limit: int,
) -> Generator[dict, None, None]:
    for rel in TARGET_SHP_REL:
        shp_path = shp_dir / rel
        if not shp_path.exists():
            print(f"[WARN] SHP 없음, 건너뜀: {shp_path}", file=sys.stderr)
            continue
        print(f"읽는 중: {shp_path.name} …", file=sys.stderr)
        for row in iter_shp(shp_path, sigungu_map, stats):
            if len(sample) < sample_limit:
                sample.append(row)
            yield row


# ── DB helpers ─────────────────────────────────────────────────────────────

def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def connect(database_url: str):
    try:
        import psycopg
        return psycopg.connect(database_url)
    except ImportError:
        pass
    try:
        import psycopg2
        return psycopg2.connect(database_url)
    except ImportError as exc:
        raise RuntimeError("psycopg or psycopg2 must be installed.") from exc


def insert_chunk(cur, chunk: list[dict]) -> None:
    ph = ",".join([ROW_PH] * len(chunk))
    params: list = []
    for r in chunk:
        params.extend([
            r["pnu"], r["bjd_cd"], r["sido"], r["sigungu"],
            r["fmap_category"], r["area_m2"], r["geom_wkb_hex"],
        ])
    cur.execute(INSERT_SQL_TMPL.format(ph=ph), params)


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()

    if not args.shp_dir.exists():
        print(
            "[데이터 요청]\n"
            f"- 무엇이: {args.shp_dir} 디렉터리\n"
            "- 어디서: 팜맵 SHP 파일 배치\n"
            "- 왜: SHP 디렉터리 없음\n"
            "- 임시 대안: 없음 — 대기",
            file=sys.stderr,
        )
        return 2

    try:
        legal_path = discover_legal_dong(args.csv_dir, args.legal_dong_file)
        print(f"법정동 CSV: {legal_path.name}", file=sys.stderr)
        sigungu_map = build_sigungu_map(legal_path)
        print(f"시군구 매핑: {len(sigungu_map)}개", file=sys.stderr)
    except DataError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    stats: Counter = Counter()
    sample: list[dict] = []
    row_gen = all_rows(args.shp_dir, sigungu_map, stats, sample, args.sample_limit)

    # ── dry-run mode ───────────────────────────────────────────────────────
    if not args.load and not args.append:
        total = sum(1 for _ in row_gen)
        stats["output.total"] = total
        _print_stats(stats)
        print()
        print("=== 샘플 (geom 생략) ===")
        for r in sample:
            print(" ", {k: v for k, v in r.items() if k != "geom_wkb_hex"})
        print(f"\nDRY RUN: {total:,}행 검증 완료. DB 변경 없음.")
        return 0

    # ── load / append mode ─────────────────────────────────────────────────
    load_dotenv(project_root() / ".env")
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL 없음. .env 또는 환경변수에 설정 필요.", file=sys.stderr)
        return 2

    try:
        conn = connect(database_url)
    except Exception as exc:
        print(f"[ERROR] DB 연결 실패: {exc}", file=sys.stderr)
        return 1

    try:
        with conn:
            with conn.cursor() as cur:
                if args.load:
                    cur.execute(
                        "SELECT COUNT(*) FROM farm WHERE parcel_id IS NOT NULL"
                    )
                    farm_ref = cur.fetchone()[0]
                    if farm_ref > 0:
                        print(
                            f"[ERROR] farm 테이블에 parcel_id 참조 {farm_ref}행 존재. "
                            "TRUNCATE 불가 — --append 사용 또는 farm 행 먼저 정리.",
                            file=sys.stderr,
                        )
                        return 2
                    cur.execute("SELECT COUNT(*) FROM parcel")
                    existing = cur.fetchone()[0]
                    if existing:
                        print(
                            f"parcel 기존 {existing:,}행 → TRUNCATE 후 재적재.",
                            file=sys.stderr,
                        )
                    cur.execute("TRUNCATE TABLE parcel RESTART IDENTITY")

                chunk: list[dict] = []
                inserted = 0
                for row in row_gen:
                    chunk.append(row)
                    if len(chunk) >= CHUNK:
                        insert_chunk(cur, chunk)
                        inserted += len(chunk)
                        chunk = []
                        if inserted % 20000 == 0:
                            print(
                                f"  {inserted:,} / (진행중) 삽입 완료 …",
                                file=sys.stderr,
                            )
                if chunk:
                    insert_chunk(cur, chunk)
                    inserted += len(chunk)

                stats["output.total"] = inserted

                cur.execute("SELECT COUNT(*) FROM parcel")
                final_count = cur.fetchone()[0]

                cur.execute(
                    "SELECT sido, COUNT(*) FROM parcel GROUP BY sido ORDER BY sido"
                )
                by_sido = cur.fetchall()

                cur.execute("""
                    SELECT sido, sigungu, bjd_cd, fmap_category,
                           ROUND(area_m2) AS area_m2
                    FROM parcel
                    ORDER BY sido, bjd_cd
                    LIMIT 5
                """)
                db_sample = cur.fetchall()

        _print_stats(stats)
        print(f"\nLoaded {inserted:,}행 → parcel.")
        print(f"SELECT COUNT(*) FROM parcel; → {final_count:,}")
        print("도별 집계:")
        for sido, cnt in by_sido:
            print(f"  {sido}: {cnt:,}")
        print("DB 샘플:")
        for r in db_sample:
            print(" ", r)
        return 0

    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def _print_stats(stats: Counter) -> None:
    print("\n=== 통계 ===")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v:,}")


if __name__ == "__main__":
    raise SystemExit(main())
