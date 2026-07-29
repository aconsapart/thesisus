from __future__ import annotations

from typing import Any, Literal, TypedDict

# FALSIFIED is a terminal outcome, not a failure to progress. FAILED/OPEN means
# "we could not settle this"; FALSIFIED means "we settled it, negatively, and
# here is the witness".
Status = Literal["PROVED", "CONDITIONAL", "COMPUTATIONAL", "HEURISTIC", "FAILED/OPEN", "FALSIFIED"]

# How an iteration ended. `OPEN` is the only one that justifies another pass.
Resolution = Literal["OPEN", "PROVED", "FALSIFIED"]


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
    parallel_refutations: int
    parallel_searches: int
    problem: dict[str, Any]
    strategies: list[dict[str, Any]]
    active_strategies: list[dict[str, Any]]
    active_refuters: list[dict[str, Any]]
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

    # --- refutation track ---------------------------------------------
    # `conjectures` are the executable claims declared in the problem spec.
    # `search_outcomes` is what the automated search established about each.
    # `verified_counterexamples` holds only witnesses that survived independent
    # checking; `contested_witnesses` holds disagreements between the two
    # evaluators, which are bugs to investigate and never evidence.
    conjectures: list[dict[str, Any]]
    search_outcomes: list[dict[str, Any]]
    claimed_witnesses: list[dict[str, Any]]
    verified_counterexamples: list[dict[str, Any]]
    contested_witnesses: list[dict[str, Any]]
    discarded_witnesses: list[dict[str, Any]]
    falsified_conjectures: list[str]
    exhaustively_verified: list[str]
    refutation_reports: list[dict[str, str]]
    refutation_report: str
    repair_report: str
    frontier_falsified: bool
    resolution: Resolution

    # --- prior-art track ----------------------------------------------
    # Day-zero recon. `claims` are the separately attackable contributions;
    # `prior_art_assessments` records, per claim, whether the literature already
    # has it and whether the search was thorough enough for silence to count.
    # `claims_file` is the maximally-defensible claim set, meant to be
    # superseded in version control rather than quietly edited.
    claims: list[dict[str, Any]]
    prior_art_passes: list[dict[str, Any]]
    prior_art_assessments: list[dict[str, Any]]
    prior_art_report: str
    claims_file: str
    claim_surgery_report: str
    claims_blocked: list[str]
    prior_art_done: bool
