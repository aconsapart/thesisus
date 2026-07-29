#!/usr/bin/env python3
"""Search a problem's conjectures for counterexamples. No model, no API key.

    python scripts/sweep.py --problem examples/counterexample_demo_problem.yaml

Exit codes:
    0  nothing falsified
    1  at least one conjecture falsified (a successful run -- it found something)
    2  evaluator disagreement detected; investigate before trusting the run
"""
from math_workbench.sweep import main

if __name__ == "__main__":
    main()
