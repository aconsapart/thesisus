# Thesius Suite

A local-first theorem/proof research workbench with:

- **Python command-line TUI** (`thesius`) instead of shell scripts
- SQLite theorem codex
- Datasette read-only browser
- Streamlit dashboard
- LangGraph/LangChain research agents
- CAS/formalization hooks
- pytest test suite

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[test,agents]"
```

## Configure the default SQLite database

Thesius stores the SQLite database path in `config/local_cli_settings.json`. Set it once:

```bash
thesius config set-db proof_codex.sqlite
```

Check the configured database:

```bash
thesius config get-db
thesius config show
```

Every command now uses this configured database by default. You can still override it per command with `--db`:

```bash
thesius status --db another_codex.sqlite
```

You can also initialize and save a database path in one step:

```bash
thesius init --db proof_codex.sqlite --save-db
```

The local settings file is ignored by git. See `config/local_cli_settings.example.json` for a template.

## Initialize the codex

```bash
thesius init
```

or with Python only:

```bash
python -m scripts.init_codex
```

## Use the command-line TUI

```bash
thesius tui
```

Commands inside the TUI:

```text
status
frontier
strategies
show <theorem_slug>
add-attempt <theorem_slug> <strategy_slug> <STATUS> <text...>
add-falsification <theorem_slug> <strategy_slug> <SEVERITY> <text...>
quit
```

## Direct commands

```bash
thesius status
thesius frontier
thesius strategies
thesius theorem exact-short-box-product-fiber-curve-intersection
```

## Launch UIs without shell scripts

```bash
thesius serve streamlit
thesius serve datasette
```

## Run the generic workbench agent

```bash
thesius run workbench \
  --iterations 3 \
  --parallel-strategies 3 \
  --out runs/workbench_example
```

## Run tests

```bash
pytest -q
```

## Notes

This package intentionally avoids bash scripts. The `scripts/` directory contains Python modules only.

The CLI uses Typer and Rich. Typer is a Python CLI framework based on type hints, and Rich provides terminal formatting and tables.
