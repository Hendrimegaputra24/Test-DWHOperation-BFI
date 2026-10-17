"""Tes statis: API hanya boleh membaca schema gold (syarat soal Part 6)."""
import re
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "api"


def _without_python_imports(text: str) -> str:
    """Buang baris impor Python agar 'from fastapi.x import' tidak dikira referensi tabel SQL."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(("from ", "import ")))


def test_every_table_reference_is_in_gold_schema():
    offenders = []
    for path in API_DIR.glob("*.py"):
        text = _without_python_imports(path.read_text(encoding="utf-8"))
        for schema, table in re.findall(r"\b(?:from|join)\s+([a-z_]+)\.([a-z_]+)", text, flags=re.I):
            if schema.lower() not in ("gold",):
                offenders.append(f"{path.name}: {schema}.{table}")
    assert not offenders, f"Referensi tabel di luar gold: {offenders}"


def test_no_raw_or_silver_mentioned_in_sql():
    for path in API_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(raw|silver)\.[a-z_]+", text), f"{path.name} menyebut raw/silver"
