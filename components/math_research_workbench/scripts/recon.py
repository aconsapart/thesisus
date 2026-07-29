#!/usr/bin/env python3
"""Hostile prior-art recon: has someone already published this?

    # emit one hostile-search prompt per angle
    python scripts/recon.py --problem examples/counterexample_demo_problem.yaml --emit-prompts

    # grade the responses that came back
    python scripts/recon.py --problem examples/counterexample_demo_problem.yaml \\
        --ingest pass1.md pass2.md --claims-out CLAIMS.md

Exit codes:
    0  every claim CLEAR
    1  at least one claim KILLED or WOUNDED (the search did its job)
    2  at least one claim UNDER_SEARCHED -- search again with different phrasing
"""
from math_workbench.recon import main

if __name__ == "__main__":
    main()
