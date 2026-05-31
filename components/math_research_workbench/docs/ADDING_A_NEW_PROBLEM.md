# Adding a new problem

1. Copy `examples/generic_number_theory_problem.yaml`.
2. Fill in title, background, definitions, targets, known results, and current frontier.
3. Copy `examples/generic_strategy_portfolio.yaml` and edit strategies.
4. Run:

```bash
python scripts/run_agent.py --problem your_problem.yaml --strategies your_strategies.yaml --iterations 3 --parallel-strategies 3 --out runs/your_run --db proof_codex.sqlite
```

## Good frontier statements

A good frontier is precise:

- states variables and hypotheses;
- says what is already proved;
- names the exact missing theorem;
- includes known falsifications;
- gives computation/formalization targets.

Avoid vague frontiers like "solve the problem." Use "prove or disprove theorem X under hypotheses Y."
