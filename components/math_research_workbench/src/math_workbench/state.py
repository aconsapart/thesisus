from __future__ import annotations

from typing import Any, Literal, TypedDict

Status = Literal["PROVED", "CONDITIONAL", "COMPUTATIONAL", "HEURISTIC", "FAILED/OPEN"]


class Finding(TypedDict):
    status: Status
    title: str
    content: str


class WorkbenchState(TypedDict):
    run_id: str
    out_dir: str
    db_path: str
    iteration: int
    max_iterations: int
    parallel_strategies: int
    problem: dict[str, Any]
    strategies: list[dict[str, Any]]
    active_strategies: list[dict[str, Any]]
    proof_ledger: list[Finding]
    failed_strategies: list[str]
    computations: list[Finding]
    formalizations: list[Finding]
    current_frontier: str
    sharpest_remaining_theorem: str
    selected_report: str
    strategy_reports: list[dict[str, str]]
    symbolic_report: str
    cas_report: str
    formalization_report: str
    synthesis: str
    discovery_report: str
    resolved: bool
