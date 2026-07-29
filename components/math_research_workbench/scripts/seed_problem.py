#!/usr/bin/env python3
"""Seed a codex with a problem: its targets to prove and its conjectures to break."""
import argparse

from math_workbench.config import ProblemSpec, StrategyPortfolio
from math_workbench.conjecture import load_conjectures
from math_workbench.tools.codex import (
    connect,
    init_db,
    insert_theorem,
    upsert_conjecture,
    upsert_problem,
    upsert_strategy,
)

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
parser.add_argument("--problem", required=True)
parser.add_argument("--strategies")
args = parser.parse_args()

report = init_db(args.db)
if not report.already_current:
    print(f"[codex] {report.summary()}")

con = connect(args.db)
problem = ProblemSpec.from_yaml(args.problem)
pid = upsert_problem(con, problem.__dict__)
for i, t in enumerate(problem.targets):
    insert_theorem(con, pid, t.get("id", f"target_{i}"), t.get("title", t.get("id", f"target_{i}")), t.get("statement", ""), t.get("status", "FAILED/OPEN"), i + 1)

# Parsed rather than copied: a bad predicate should fail here, at seed time,
# rather than during a run that has already spent a model budget.
conjectures = load_conjectures(problem.conjectures)
for c in conjectures:
    upsert_conjecture(con, pid, c)

if args.strategies:
    portfolio = StrategyPortfolio.from_yaml(args.strategies)
    for s in portfolio.strategies:
        upsert_strategy(con, s.__dict__)
con.close()

print(f"Seeded {args.db} with {problem.title}")
print(f"  targets to prove:     {len(problem.targets)}")
print(f"  conjectures to break: {len(conjectures)}")
if conjectures:
    total = sum(c.space_size() for c in conjectures)
    print(f"  total search space:   {total} points")
    print(f"\nSweep them now with:\n  python -m math_workbench.sweep --problem {args.problem}")
