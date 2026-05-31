# Architecture

This workbench is problem-agnostic.

## Core abstractions

- `ProblemSpec`: definitions, targets, known results, current frontier.
- `StrategySpec`: a ranked lane with falsification prompts and proof prompts.
- `Theorem ledger`: SQLite tables for theorem states, claims, attempts, computations, and formalization jobs.
- `LangGraph workflow`: iterative stateful proof search.

## Graph

```text
select_strategies
  -> run_strategies
  -> symbolic_checks
  -> cas_degeneracy
  -> formalization
  -> synthesize
  -> discover
  -> repeat
```

## Why this generalizes

To use a new math problem, provide:

1. a problem YAML file;
2. a strategy portfolio YAML file;
3. optional domain-specific CAS scripts or computation nodes.

No Erdős-specific theorem is hardcoded, except in the provided example spec.
