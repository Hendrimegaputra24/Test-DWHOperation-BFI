"""Tes struktur Airflow tanpa perlu memasang Airflow: DAG dibaca sebagai teks (AST), serta
pemeriksaan opsi --step pada pipeline dan pengaturan docker-compose."""
import ast
from pathlib import Path

import pytest
import yaml

import pipeline

ROOT = Path(__file__).resolve().parent.parent
DAG_FILE = ROOT / "airflow" / "dags" / "price_pipeline_daily.py"
TREE = ast.parse(DAG_FILE.read_text(encoding="utf-8"))


def _calls(name):
    return [n for n in ast.walk(TREE) if isinstance(n, ast.Call)
            and getattr(n.func, "id", getattr(n.func, "attr", None)) == name]


def _kw(call, key):
    for k in call.keywords:
        if k.arg == key:
            return ast.literal_eval(k.value) if isinstance(k.value, ast.Constant) else k.value
    raise KeyError(key)


def test_dag_has_expected_id_schedule_and_safety_settings():
    dag = _calls("DAG")[0]
    assert _kw(dag, "dag_id") == "price_pipeline_daily"
    assert _kw(dag, "schedule") == "0 1 * * *"       # tiap hari pukul 01.00
    assert _kw(dag, "catchup") is False
    assert _kw(dag, "max_active_runs") == 1          # dua run tidak boleh menulis bersamaan


def test_dag_has_three_tasks_chained_in_order():
    ids = [_kw(c, "task_id") for c in _calls("BashOperator")]
    assert ids == ["run_crawler", "run_dbt_build", "run_pricing_model"]
    chain = next(n for n in ast.walk(TREE) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.RShift)
                 and isinstance(n.left, ast.BinOp))                       # a >> b >> c
    assert (chain.left.left.id, chain.left.right.id, chain.right.id) == (
        "run_crawler", "run_dbt_build", "run_pricing_model")


def test_each_task_runs_the_matching_pipeline_step():
    steps = {}
    for c in _calls("BashOperator"):
        arg = _kw(c, "bash_command")                                        # pipeline_step("...")
        steps[_kw(c, "task_id")] = ast.literal_eval(arg.args[0])
    assert steps == {"run_crawler": "ingest", "run_dbt_build": "transform", "run_pricing_model": "recommend"}
    assert set(steps.values()) <= set(pipeline.STEP_CHOICES)


def test_pipeline_step_option_rejects_unknown_step():
    assert pipeline.STEP_CHOICES == ("all", "ingest", "transform", "recommend")
    with pytest.raises(SystemExit):                  # argparse menolak sebelum menyentuh database
        pipeline.main(["--step", "tidak-ada"])


def test_airflow_is_optional_profile_and_core_services_unchanged():
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    assert services["airflow"]["profiles"] == ["airflow"]
    assert services["airflow"]["depends_on"]["pipeline"]["condition"] == "service_completed_successfully"
    for name in ("db", "pipeline", "api", "metabase"):
        assert "profiles" not in services[name]       # tetap menyala dengan `docker compose up`
