# Integration guide

## Recommended workflow

1. Use `theorem_codex` as the durable proof ledger.
2. Use `math_research_workbench` for generic or new mathematical problems.
3. Use `math_frontier_langchain_template` when building new prompt nodes.
4. Use `erdos_hybrid_strategy_agent` when working specifically on the Erdős divisor-sum frontier.
5. Use the Streamlit app for active control/review and Datasette for read-only browsing and SQL/API access.

## Data flow

```text
LangGraph agent runs
  -> writes theorem/attempt/computation/formalization metadata to SQLite
  -> writes large artifacts to runs/ or component output directories
  -> theorem_codex Streamlit/Datasette reads SQLite
```

## Local model/API key config

The `math_research_workbench` component supports `config/local_settings.yaml`. This file is ignored by git in that component. Use:

```bash
cd components/math_research_workbench
cp config/settings.example.yaml config/local_settings.yaml
python scripts/configure_settings.py --model gpt-4.1
```

You may also keep using environment variables such as `OPENAI_API_KEY` and `MODEL_NAME`.

## Formalization and CAS

Optional environment variables:

```bash
export SAGE_CMD=sage
export MAGMA_CMD=magma
export LEAN_CMD="lake env lean"
export ARISTOTLE_CLI=aristotle
export ARISTOTLE_API_KEY=...
```

The scaffold treats formalization as supportive unless a Lean/Aristotle proof verifies with no gaps.
