# Thesius Workbench

A reusable, problem-agnostic proof-search automation scaffold for mathematical research.

It generalizes the Erdős divisor-sum proof-search workflow into a configurable system that can be used for arbitrary math problems:

- theorem/frontier tracking in SQLite;
- strategy portfolio execution with falsification-first discipline;
- symbolic/CAS hooks;
- optional Lean/Aristotle formalization hooks;
- optional Datasette read-only theorem codex;
- optional Streamlit control dashboard;
- LangGraph orchestration for stateful, iterative proof search.

## Core idea

Every run maintains a state containing:

- current theorem/frontier;
- known definitions and constraints;
- ranked strategies;
- proof ledger;
- falsifications/counterexamples;
- computation artifacts;
- formalization jobs;
- sharpest remaining theorem.

Each iteration follows:

```text
load problem spec
  -> select strategies
  -> falsify first
  -> attempt proof or reduction
  -> run symbolic/computational checks
  -> generate optional formalization tasks
  -> synthesize status
  -> discover or demote strategies
  -> persist to SQLite
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Configure your model and local API key:

```bash
cp config/settings.example.yaml config/local_settings.yaml
python scripts/configure_settings.py --model gpt-4.1
```

This writes `config/local_settings.yaml`, which is ignored by git by default. You can also edit it manually:

```yaml
llm:
  provider: openai
  model: gpt-4.1
  api_key: "sk-..."
  base_url: ""
  temperature: 0.2
```

Run with the default settings file:

```bash
python scripts/run_agent.py \
  --problem examples/generic_number_theory_problem.yaml \
  --strategies examples/generic_strategy_portfolio.yaml \
  --iterations 3 \
  --parallel-strategies 3 \
  --out runs/example_run \
  --db proof_codex.sqlite
```

Or choose a settings file explicitly:

```bash
python scripts/run_agent.py \
  --settings config/local_settings.yaml \
  --problem examples/generic_number_theory_problem.yaml \
  --strategies examples/generic_strategy_portfolio.yaml
```

Environment variables are still supported as a fallback for deployments:

```bash
export OPENAI_API_KEY="YOUR_KEY"
export MODEL_NAME="gpt-4.1"
```

Optional tool settings can also be stored in `config/local_settings.yaml`:

```yaml
formalization:
  lean_cmd: "lake env lean"
  aristotle_cli: "aristotle"
  aristotle_api_key: ""

tools:
  sage_cmd: "sage"
  magma_cmd: "magma"
```

For production or shared machines, environment variables or a secret manager are safer than storing plaintext keys in a local file. OpenAI's API reference says API keys should be securely loaded from an environment variable or key-management service on the server.

## Run a generic example

```bash
python scripts/run_agent.py \
  --problem examples/generic_number_theory_problem.yaml \
  --strategies examples/generic_strategy_portfolio.yaml \
  --iterations 3 \
  --parallel-strategies 3 \
  --out runs/example_run \
  --db proof_codex.sqlite
```

## Initialize codex only

```bash
python scripts/init_codex.py --db proof_codex.sqlite
python scripts/seed_problem.py --db proof_codex.sqlite --problem examples/generic_number_theory_problem.yaml
```

## Run Streamlit dashboard

```bash
streamlit run apps/streamlit_app.py -- --db proof_codex.sqlite
```

## Run Datasette browser

```bash
datasette serve proof_codex.sqlite --metadata datasette/metadata.json
```

## Problem spec format

See `examples/generic_number_theory_problem.yaml`.

A problem spec contains:

```yaml
title: "..."
domain: "number_theory"
background: "..."
definitions:
  - name: "..."
    statement: "..."
targets:
  - id: "main"
    statement: "..."
known_results:
  - status: "PROVED"
    statement: "..."
current_frontier: "..."
falsification_tests:
  - "search for small counterexamples"
formalization_targets:
  - "prove algebraic identity in Lean"
```

## Status labels

The system expects claims to use only:

- `PROVED`
- `CONDITIONAL`
- `COMPUTATIONAL`
- `HEURISTIC`
- `FAILED/OPEN`

This keeps the theorem ledger honest.

## Strategy design

Strategies are configured in YAML. A strategy contains:

- `id`
- `name`
- `rank`
- `description`
- `allowed_tools`
- `falsification_prompts`
- `proof_prompts`
- `success_criteria`
- `failure_modes`

The workbench ships with generic strategies:

1. exact algebraic reduction;
2. counterexample search;
3. proof by known theorem audit;
4. symbolic/CAS simplification;
5. computational experiment;
6. formalization in Lean;
7. strategy discovery;
8. dependency graph tightening;
9. asymptotic/scaling falsification;
10. alternate formulation search.

## Front ends

Use both:

- SQLite as the canonical ledger;
- Datasette for read-only browsing/search/query;
- Streamlit for active strategy control and dashboards.

## Important caveat

This is a proof-search workbench, not a theorem prover. It helps organize, falsify, compute, and formalize. Mathematical correctness still depends on explicit proofs or verified formalizations.
