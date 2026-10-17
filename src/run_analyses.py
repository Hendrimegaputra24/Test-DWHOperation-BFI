#!/usr/bin/env python3
"""Jalankan semua file SQL di dbt/analyses, tampilkan ringkasan, simpan hasilnya sebagai CSV.

Contoh:  python src/run_analyses.py
Hasil :  docs/analysis_results/<nama_analisis>.csv
"""
import argparse, csv, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyses-dir", default=str(ROOT / "dbt" / "analyses"))
    ap.add_argument("--out-dir", default=str(ROOT / "docs" / "analysis_results"))
    args = ap.parse_args()

    import psycopg
    load_env_file(ROOT / ".env")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(Path(args.analyses_dir).glob("*.sql"))
    if not files:
        print("Tidak ada file analisis di", args.analyses_dir)
        return 1

    with psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    ) as conn:
        for f in files:
            with conn.cursor() as cur:
                cur.execute(f.read_text(encoding="utf-8"))
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
            with open(out / f"{f.stem}.csv", "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh); w.writerow(cols); w.writerows(rows)
            print(f"\n== {f.stem}  ({len(rows)} baris) ==")
            print(" | ".join(cols))
            for r in rows[:8]:
                print(" | ".join("" if v is None else str(v) for v in r))
            if len(rows) > 8:
                print(f"... (+{len(rows) - 8} baris lagi di CSV)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
