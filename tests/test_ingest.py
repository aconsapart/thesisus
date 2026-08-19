from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from thesius.app import app
from thesius.db import connect, init_db, rows, table_count, upsert_theorem
from thesius.ingest import ingest_ai_scientist, parse_source_dir, stronger_status

runner = CliRunner()

# Three benchmarks covering all three status mappings, plus the aggregate key.
BENCHMARKS = {
    "kepler_third_law": {"solved": [1, 1], "verified": [0, 1]},
    "ideal_gas_pressure": {"solved": [1, 0], "verified": [0, 0]},
    "snell_refraction": {"solved": [0, 0], "verified": [0, 0]},
}


def make_source_dir(tmp_path: Path, *, with_npy: bool = True, name: str = "symbolic_math") -> Path:
    src = tmp_path / name
    run_dir = src / "run_0"
    run_dir.mkdir(parents=True)
    final_info: dict = {}
    all_results: dict = {}
    for benchmark, flags in BENCHMARKS.items():
        final_info[benchmark] = {
            "means": {"solved_mean": sum(flags["solved"]) / 2, "verified_mean": sum(flags["verified"]) / 2},
            "stderrs": {"solved_stderr": 0.0},
            "final_info_dict": {
                "solved": flags["solved"],
                "verified": flags["verified"],
                "best_nrmse": [0.1, 0.2],
                "evals_to_solve": [100, 3000],
                "best_complexity": [5, 7],
            },
        }
        for seed in range(2):
            all_results[f"{benchmark}_{seed}_best_expr"] = f"x0**{seed + 1}"
            all_results[f"{benchmark}_{seed}_final_info"] = {"solved": flags["solved"][seed]}
            all_results[f"{benchmark}_{seed}_history"] = []
    final_info["aggregate"] = {
        "means": {"solve_rate_mean": 0.5},
        "stderrs": {"solve_rate_stderr": 0.0},
        "final_info_dict": {"solve_rate": [0.5, 0.5]},
    }
    (run_dir / "final_info.json").write_text(json.dumps(final_info), encoding="utf-8")
    if with_npy:
        np.save(run_dir / "all_results.npy", all_results)  # type: ignore[arg-type]
    return src


def test_ingest_status_mapping(tmp_path: Path):
    src = make_source_dir(tmp_path)
    db = tmp_path / "codex.sqlite"
    result = runner.invoke(app, ["ingest", "ai-scientist", str(src), "--db", str(db)])
    assert result.exit_code == 0, result.output
    con = connect(db)
    try:
        statuses = {r["slug"]: r["status"] for r in rows(con, "SELECT slug, status FROM theorem")}
        assert statuses["symbolic-math-kepler-third-law"] == "COMPUTATIONAL"
        assert statuses["symbolic-math-ideal-gas-pressure"] == "HEURISTIC"
        assert statuses["symbolic-math-snell-refraction"] == "FAILED/OPEN"
        attempts = rows(con, "SELECT title, status, result_md FROM attempt ORDER BY title")
        assert len(attempts) == 3
        by_title = {a["title"]: a for a in attempts}
        assert by_title["run_0: kepler_third_law"]["status"] == "COMPUTATIONAL"
        assert by_title["run_0: ideal_gas_pressure"]["status"] == "HEURISTIC"
        assert by_title["run_0: snell_refraction"]["status"] == "FAILED/OPEN"
        assert "`x0**1`" in by_title["run_0: kepler_third_law"]["result_md"]
        assert table_count(con, "strategy") == 1
        assert table_count(con, "artifact") == 1
    finally:
        con.close()


def test_ingest_is_idempotent(tmp_path: Path):
    src = make_source_dir(tmp_path)
    db = tmp_path / "codex.sqlite"
    for _ in range(2):
        result = runner.invoke(app, ["ingest", "ai-scientist", str(src), "--db", str(db)])
        assert result.exit_code == 0, result.output
    con = connect(db)
    try:
        assert table_count(con, "theorem") == 3
        assert table_count(con, "strategy") == 1
        assert table_count(con, "attempt") == 3
        assert table_count(con, "artifact") == 1
    finally:
        con.close()


def test_missing_npy_degrades_to_final_info_only(tmp_path: Path):
    src = make_source_dir(tmp_path, with_npy=False)
    db = tmp_path / "codex.sqlite"
    result = runner.invoke(app, ["ingest", "ai-scientist", str(src), "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert "all_results.npy" in result.output
    con = connect(db)
    try:
        assert table_count(con, "theorem") == 3
        assert table_count(con, "attempt") == 3
        result_md = rows(con, "SELECT result_md FROM attempt")[0]["result_md"]
        assert "unavailable" in result_md
    finally:
        con.close()


def test_aggregate_key_is_skipped(tmp_path: Path):
    src = make_source_dir(tmp_path)
    records = parse_source_dir(src)
    benchmarks = {b.benchmark for run in records.runs for b in run.benchmarks}
    assert "aggregate" not in benchmarks
    assert benchmarks == set(BENCHMARKS)
    db = tmp_path / "codex.sqlite"
    ingest_ai_scientist(src, db)
    con = connect(db)
    try:
        assert rows(con, "SELECT id FROM theorem WHERE slug=?", ("symbolic-math-aggregate",)) == []
    finally:
        con.close()


def test_no_downgrade_of_existing_status(tmp_path: Path):
    src = make_source_dir(tmp_path)
    db = tmp_path / "codex.sqlite"
    init_db(db)
    con = connect(db)
    try:
        upsert_theorem(
            con,
            slug="symbolic-math-snell-refraction",
            title="Snell Refraction",
            statement_md="Previously proved in Lean.",
            status="PROVED",
        )
    finally:
        con.close()
    result = runner.invoke(app, ["ingest", "ai-scientist", str(src), "--db", str(db)])
    assert result.exit_code == 0, result.output
    con = connect(db)
    try:
        status = rows(con, "SELECT status FROM theorem WHERE slug=?", ("symbolic-math-snell-refraction",))[0]["status"]
        assert status == "PROVED"
    finally:
        con.close()


def test_stronger_status_ordering():
    assert stronger_status("PROVED", "COMPUTATIONAL") == "PROVED"
    assert stronger_status("HEURISTIC", "COMPUTATIONAL") == "COMPUTATIONAL"
    assert stronger_status("FAILED/OPEN", "HEURISTIC") == "HEURISTIC"
    assert stronger_status("COMPUTATIONAL", "FAILED/OPEN") == "COMPUTATIONAL"
    # Statuses outside the ingest ladder are never overwritten.
    assert stronger_status("FALSIFIED", "COMPUTATIONAL") == "FALSIFIED"


def test_idea_dir_strategy_from_notes(tmp_path: Path):
    src = make_source_dir(tmp_path, name="20260819_123456_adaptive_temperature")
    (src / "notes.txt").write_text("Adaptive temperature schedule.\nLine two.\n", encoding="utf-8")
    records = parse_source_dir(src)
    assert records.strategy_slug == "symbolic-math-adaptive-temperature"
    assert records.strategy_name == "Adaptive Temperature (symbolic_math)"
    assert records.strategy_description_md.startswith("Adaptive temperature schedule.")
