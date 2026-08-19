"""Ingest AI-Scientist symbolic_math experiment results into the theorem codex.

The source directory is either a template directory (containing only ``run_0``,
the baseline) or an idea results directory
(``results/symbolic_math/<timestamp>_<idea_name>/`` with ``run_0..run_N`` and a
``notes.txt``). Each ``run_*`` subdirectory holds ``final_info.json`` and
usually ``all_results.npy``.

Mapping into the codex:
    - theorem: one per benchmark (hidden-law recovery target),
    - strategy: one per ingested source directory,
    - attempt: one per (run x benchmark),
    - artifact: one per run's ``final_info.json``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .db import add_artifact, add_attempt, connect, init_db, upsert_strategy, upsert_theorem

BASELINE_STRATEGY_SLUG = "symbolic-math-random-search-baseline"
BASELINE_STRATEGY_NAME = "Random search baseline (symbolic_math)"
RUN_DIR_RE = re.compile(r"^run_(\d+)$")
IDEA_TIMESTAMP_RE = re.compile(r"^\d{8}_\d{6}_")

# Evidence strength for the no-downgrade rule. Statuses outside this map
# (CONDITIONAL, FALSIFIED) are never overwritten by ingest evidence.
_STATUS_RANK = {"FAILED/OPEN": 0, "HEURISTIC": 1, "COMPUTATIONAL": 2, "PROVED": 3}


@dataclass
class SeedResult:
    seed: int
    solved: int
    verified: int
    best_nrmse: Optional[float]
    evals_to_solve: Optional[float]
    best_complexity: Optional[float]
    best_expr: Optional[str]


@dataclass
class BenchmarkRun:
    """Results for one benchmark within one run_* directory."""

    benchmark: str
    means: dict[str, Any]
    seeds: list[SeedResult]


@dataclass
class RunRecord:
    run_name: str
    final_info_path: Path
    benchmarks: list[BenchmarkRun]


@dataclass
class SourceRecords:
    source_dir: Path
    strategy_slug: str
    strategy_name: str
    strategy_description_md: str
    runs: list[RunRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class IngestSummary:
    theorems: int = 0
    strategies: int = 0
    attempts: int = 0
    attempts_skipped: int = 0
    artifacts: int = 0
    artifacts_skipped: int = 0


def theorem_slug(benchmark: str) -> str:
    return f"symbolic-math-{benchmark.replace('_', '-')}"


def humanize(name: str) -> str:
    return name.replace("_", " ").strip().title()


def status_from_seeds(seeds: list[SeedResult]) -> str:
    """COMPUTATIONAL if any seed verified (sympy CAS, up to constants), else HEURISTIC if any solved, else FAILED/OPEN."""
    if any(s.verified for s in seeds):
        return "COMPUTATIONAL"
    if any(s.solved for s in seeds):
        return "HEURISTIC"
    return "FAILED/OPEN"


def stronger_status(existing: str, computed: str) -> str:
    """Never downgrade an existing theorem status (PROVED > COMPUTATIONAL > HEURISTIC > FAILED/OPEN)."""
    if existing not in _STATUS_RANK:
        return existing
    return existing if _STATUS_RANK[existing] >= _STATUS_RANK[computed] else computed


def derive_strategy(source_dir: Path) -> tuple[str, str, str]:
    """Return (slug, name, description_md) for the strategy represented by source_dir."""
    dir_name = source_dir.name
    notes_path = source_dir / "notes.txt"
    is_idea_dir = bool(IDEA_TIMESTAMP_RE.match(dir_name)) or notes_path.exists()
    if not is_idea_dir:
        description = (
            "Random search over expression trees from the AI-Scientist `symbolic_math` template "
            "(baseline `run_0` results): sample candidate expressions, score by NRMSE against noisy "
            "observations of a hidden physical law, verify symbolically with sympy."
        )
        return BASELINE_STRATEGY_SLUG, BASELINE_STRATEGY_NAME, description
    idea_name = IDEA_TIMESTAMP_RE.sub("", dir_name)
    slug = f"symbolic-math-{idea_name.replace('_', '-')}"
    name = f"{humanize(idea_name)} (symbolic_math)"
    description = (
        f"AI-Scientist idea `{idea_name}` run on the `symbolic_math` template "
        "(hidden-law recovery via symbolic regression)."
    )
    if notes_path.exists():
        notes_head = "\n".join(notes_path.read_text(encoding="utf-8").splitlines()[:10]).strip()
        if notes_head:
            description = notes_head
    return slug, name, description


def _load_all_results(path: Path, run_name: str, warnings: list[str]) -> dict[str, Any] | None:
    """Load all_results.npy; on any failure warn and return None (final_info.json-only ingest)."""
    if not path.exists():
        warnings.append(f"{run_name}: all_results.npy missing; best expressions unavailable.")
        return None
    try:
        import numpy as np
    except ImportError:
        warnings.append(f"{run_name}: numpy unavailable; skipping all_results.npy (best expressions unavailable).")
        return None
    try:
        data = np.load(path, allow_pickle=True).item()
    except Exception as exc:  # noqa: BLE001 - degrade gracefully on any corrupt npy
        warnings.append(f"{run_name}: failed to load all_results.npy ({exc}); best expressions unavailable.")
        return None
    return data if isinstance(data, dict) else None


def _seed_value(final_info_dict: dict[str, Any], key: str, index: int) -> Any:
    values = final_info_dict.get(key)
    if isinstance(values, list) and index < len(values):
        return values[index]
    return None


def parse_source_dir(source_dir: str | Path) -> SourceRecords:
    """Parse an AI-Scientist symbolic_math results directory into pure-data records."""
    src = Path(source_dir).resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"Not a directory: {src}")
    slug, name, description = derive_strategy(src)
    records = SourceRecords(source_dir=src, strategy_slug=slug, strategy_name=name, strategy_description_md=description)
    run_dirs = sorted(
        (p for p in src.iterdir() if p.is_dir() and RUN_DIR_RE.match(p.name)),
        key=lambda p: int(RUN_DIR_RE.match(p.name).group(1)),  # type: ignore[union-attr]
    )
    for run_dir in run_dirs:
        final_info_path = run_dir / "final_info.json"
        if not final_info_path.exists():
            records.warnings.append(f"{run_dir.name}: no final_info.json; run skipped.")
            continue
        try:
            final_info = json.loads(final_info_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            records.warnings.append(f"{run_dir.name}: invalid final_info.json ({exc}); run skipped.")
            continue
        all_results = _load_all_results(run_dir / "all_results.npy", run_dir.name, records.warnings)
        benchmarks: list[BenchmarkRun] = []
        for benchmark, payload in final_info.items():
            if benchmark == "aggregate" or not isinstance(payload, dict):
                continue
            final_info_dict = payload.get("final_info_dict") or {}
            solved = final_info_dict.get("solved") or []
            seeds: list[SeedResult] = []
            for i in range(len(solved)):
                best_expr: Optional[str] = None
                if all_results is not None:
                    expr = all_results.get(f"{benchmark}_{i}_best_expr")
                    best_expr = None if expr is None else str(expr)
                seeds.append(
                    SeedResult(
                        seed=i,
                        solved=int(solved[i]),
                        verified=int(_seed_value(final_info_dict, "verified", i) or 0),
                        best_nrmse=_seed_value(final_info_dict, "best_nrmse", i),
                        evals_to_solve=_seed_value(final_info_dict, "evals_to_solve", i),
                        best_complexity=_seed_value(final_info_dict, "best_complexity", i),
                        best_expr=best_expr,
                    )
                )
            benchmarks.append(BenchmarkRun(benchmark=benchmark, means=payload.get("means") or {}, seeds=seeds))
        records.runs.append(RunRecord(run_name=run_dir.name, final_info_path=final_info_path, benchmarks=benchmarks))
    return records


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _statement_md(benchmark: str) -> str:
    return (
        f"Recover the hidden physical law `{benchmark}` from noisy observational data "
        "(hidden-law recovery target from the AI-Scientist `symbolic_math` template). "
        "COMPUTATIONAL status means the discovered expression matched the hidden law under "
        "sympy CAS verification (up to constants), not a formal proof."
    )


def _result_md(run_name: str, bench: BenchmarkRun) -> str:
    lines = [
        f"### {run_name}: {bench.benchmark}",
        "",
        "| seed | best_expr | solved | verified | best_nrmse | evals_to_solve | best_complexity |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for s in bench.seeds:
        expr = f"`{s.best_expr}`" if s.best_expr is not None else "unavailable"
        lines.append(
            f"| {s.seed} | {expr} | {s.solved} | {s.verified} | {_fmt(s.best_nrmse)} "
            f"| {_fmt(s.evals_to_solve)} | {_fmt(s.best_complexity)} |"
        )
    if bench.means:
        lines += ["", "Means: " + ", ".join(f"{k}={_fmt(v)}" for k, v in bench.means.items())]
    return "\n".join(lines)


def write_records(con: sqlite3.Connection, records: SourceRecords) -> IngestSummary:
    """Write parsed records into the codex. Idempotent: upserts theorems/strategies, skips duplicate attempts/artifacts."""
    summary = IngestSummary()
    upsert_strategy(
        con,
        slug=records.strategy_slug,
        name=records.strategy_name,
        description_md=records.strategy_description_md,
    )
    summary.strategies += 1

    all_seeds: dict[str, list[SeedResult]] = defaultdict(list)
    for run in records.runs:
        for bench in run.benchmarks:
            all_seeds[bench.benchmark].extend(bench.seeds)
    for benchmark, seeds in all_seeds.items():
        slug = theorem_slug(benchmark)
        computed = status_from_seeds(seeds)
        existing = con.execute("SELECT status FROM theorem WHERE slug=?", (slug,)).fetchone()
        status = computed if existing is None else stronger_status(str(existing[0]), computed)
        upsert_theorem(
            con,
            slug=slug,
            title=humanize(benchmark),
            statement_md=_statement_md(benchmark),
            status=status,
            kind="THEOREM",
        )
        summary.theorems += 1

    invocation = f"thesius ingest ai-scientist {records.source_dir}"
    for run in records.runs:
        run_id = f"{records.source_dir.name}/{run.run_name}"
        prompt_md = f"Ingested from `{run.final_info_path}` via `{invocation}`."
        first_attempt_id: Optional[int] = None
        for bench in run.benchmarks:
            title = f"{run.run_name}: {bench.benchmark}"
            existing_attempt = con.execute(
                "SELECT id FROM attempt WHERE run_id=? AND title=?", (run_id, title)
            ).fetchone()
            if existing_attempt is not None:
                summary.attempts_skipped += 1
                if first_attempt_id is None:
                    first_attempt_id = int(existing_attempt[0])
                continue
            aid = add_attempt(
                con,
                theorem_slug=theorem_slug(bench.benchmark),
                strategy_slug=records.strategy_slug,
                run_id=run_id,
                title=title,
                prompt_md=prompt_md,
                result_md=_result_md(run.run_name, bench),
                status=status_from_seeds(bench.seeds),
            )
            summary.attempts += 1
            if first_attempt_id is None:
                first_attempt_id = aid
        artifact_path = str(run.final_info_path)
        existing_artifact = con.execute(
            "SELECT id FROM artifact WHERE path=? AND kind=?", (artifact_path, "final_info")
        ).fetchone()
        if existing_artifact is None:
            add_artifact(
                con,
                path=artifact_path,
                kind="final_info",
                attempt_id=first_attempt_id,
                description_md=f"AI-Scientist final_info.json for {run.run_name} ({len(run.benchmarks)} benchmarks).",
            )
            summary.artifacts += 1
        else:
            summary.artifacts_skipped += 1
    return summary


def ingest_ai_scientist(source_dir: str | Path, db_path: str | Path) -> tuple[SourceRecords, IngestSummary]:
    """Full pipeline: initialize the database, parse source_dir, and write the records."""
    init_db(db_path)
    records = parse_source_dir(source_dir)
    con = connect(db_path)
    try:
        summary = write_records(con, records)
    finally:
        con.close()
    return records, summary
