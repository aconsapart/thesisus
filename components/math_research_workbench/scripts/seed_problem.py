#!/usr/bin/env python3
import argparse
from math_workbench.config import ProblemSpec, StrategyPortfolio
from math_workbench.tools.codex import connect, init_db, upsert_problem, upsert_strategy, insert_theorem

parser = argparse.ArgumentParser()
parser.add_argument("--db", required=True)
parser.add_argument("--problem", required=True)
parser.add_argument("--strategies")
args = parser.parse_args()

init_db(args.db)
con = connect(args.db)
problem = ProblemSpec.from_yaml(args.problem)
pid = upsert_problem(con, problem.__dict__)
for i, t in enumerate(problem.targets):
    insert_theorem(con, pid, t.get("id", f"target_{i}"), t.get("title", t.get("id", f"target_{i}")), t.get("statement", ""), t.get("status", "FAILED/OPEN"), i + 1)
if args.strategies:
    portfolio = StrategyPortfolio.from_yaml(args.strategies)
    for s in portfolio.strategies:
        upsert_strategy(con, s.__dict__)
con.close()
print(f"Seeded {args.db} with {problem.title}")
