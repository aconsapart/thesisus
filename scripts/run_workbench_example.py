from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
from thesius.app import _db_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--parallel-strategies", type=int, default=3)
    parser.add_argument("--out", default="runs/workbench_example")
    parser.add_argument("--db", default=None, help="SQLite database path. Overrides saved Thesius setting.")
    args = parser.parse_args()
    db = _db_path(args.db)
    script = Path("components/math_research_workbench/scripts/run_agent.py")
    cmd = [
        sys.executable, str(script),
        "--settings", "components/math_research_workbench/config/local_settings.yaml",
        "--problem", "components/math_research_workbench/examples/generic_number_theory_problem.yaml",
        "--strategies", "components/math_research_workbench/examples/generic_strategy_portfolio.yaml",
        "--iterations", str(args.iterations),
        "--parallel-strategies", str(args.parallel_strategies),
        "--out", args.out,
        "--db", db,
    ]
    subprocess.run(cmd, check=False)

if __name__ == "__main__":
    main()
