"""Standalone counterexample sweep: no model, no API key, no LangGraph.

Deliberately importable without `langchain` or `langgraph` installed. The sweep
is the cheapest useful thing the workbench does and the only part that is fully
deterministic, so it should be runnable on its own -- before committing to a
proof campaign, in CI, or as a pre-commit check on a problem spec.

    python -m math_workbench.sweep --problem examples/counterexample_demo_problem.yaml

Exit code 1 means at least one conjecture was falsified. That is a *successful*
run of this tool: it found something.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .config import ProblemSpec, load_app_config
from .conjecture import load_conjectures
from .tools.refutation import (
    STATUS_CONTESTED,
    STATUS_FALSIFIED,
    STATUS_VERIFIED_EXHAUSTIVE,
    SearchBudget,
    render_report,
    search_conjectures,
)

__all__ = ["sweep", "main"]


def sweep(
    problem_path: str,
    db: str | None = None,
    out: str | None = None,
    budget: SearchBudget | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Search every declared conjecture and optionally persist the result.

    Returns a summary dict rather than printing only, so callers (tests, CI,
    the agent) can act on the outcome.
    """
    problem = ProblemSpec.from_yaml(problem_path)
    conjectures = load_conjectures(problem.conjectures)
    if budget is None:
        budget = load_app_config().search_budget(problem.refutation)

    outcomes = search_conjectures(conjectures, budget)
    report = render_report(outcomes)

    if not quiet:
        print(report)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(report, encoding="utf-8")
    if db:
        # Imported here so a sweep that does not persist never needs the codex.
        from .tools.codex import connect, init_db, record_search_outcome, upsert_problem

        init_db(db)
        con = connect(db)
        problem_id = upsert_problem(con, problem.__dict__)
        for conjecture, outcome in zip(conjectures, outcomes):
            record_search_outcome(con, problem_id, conjecture, outcome, run_id="sweep", iteration=0)
        con.close()

    return {
        "problem": problem.slug,
        "outcomes": [o.as_dict() for o in outcomes],
        "falsified": [o.conjecture_id for o in outcomes if o.status == STATUS_FALSIFIED],
        "verified_exhaustive": [
            o.conjecture_id for o in outcomes if o.status == STATUS_VERIFIED_EXHAUSTIVE
        ],
        "contested": [o.conjecture_id for o in outcomes if o.status == STATUS_CONTESTED],
        "report": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem", required=True)
    parser.add_argument("--db", default=None, help="Persist results to this codex database")
    parser.add_argument("--out", default=None, help="Write the markdown report here")
    parser.add_argument("--max-evaluations", type=int, default=None)
    parser.add_argument("--random-samples", type=int, default=None)
    parser.add_argument("--time-limit", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--settings", default="config/local_settings.yaml", help="Local settings YAML (for search defaults)"
    )
    args = parser.parse_args()

    import os

    os.environ["MATH_WORKBENCH_CONFIG"] = args.settings
    overrides = {
        k: v
        for k, v in {
            "max_evaluations": args.max_evaluations,
            "random_samples": args.random_samples,
            "time_limit_s": args.time_limit,
            "seed": args.seed,
        }.items()
        if v is not None
    }
    problem = ProblemSpec.from_yaml(args.problem)
    budget = load_app_config().search_budget({**(problem.refutation or {}), **overrides})

    result = sweep(args.problem, db=args.db, out=args.out, budget=budget)
    if result["contested"]:
        print(
            f"\nCONTESTED: {len(result['contested'])} conjecture(s) had evaluator disagreements. "
            "That is a bug in an evaluator, not a mathematical result. Investigate before trusting this run."
        )
        raise SystemExit(2)
    raise SystemExit(1 if result["falsified"] else 0)


if __name__ == "__main__":
    main()
