# Theorem Codex

A local-first theorem codex for proof-search workflows using **SQLite**, **Datasette**, and **Streamlit**.

This package is tuned for the Erdős divisor-sum project, but the schema is generic enough for other theorem-ledger workflows.

## What it gives you

- SQLite database as the canonical theorem ledger.
- Datasette for read-only browsing, filtering, SQL queries, and JSON API exploration.
- Streamlit dashboard for active review, theorem/strategy CRUD, diagnostics, and notes.
- Seed data for the current Erdős project frontier.
- Falsification ledger, attempt ledger, computation ledger, formalization queue, artifacts, tags, and theorem dependencies.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Initialize database

```bash
python scripts/seed.py --db proof_codex.sqlite --prompt data/current_frontier_prompt.md
```

or:

```bash
make init
```

## Run Streamlit dashboard

```bash
streamlit run apps/streamlit_app.py -- --db proof_codex.sqlite
```

or:

```bash
make streamlit
```

## Run Datasette browser

```bash
datasette serve proof_codex.sqlite --metadata datasette/metadata.json
```

or:

```bash
make datasette
```

## Suggested workflow

1. Use Streamlit to add/update theorem frontiers, strategies, claims, attempts, falsifications, computations, and dependencies.
2. Use Datasette for read-only audit, browsing, filtering, and SQL exploration.
3. Let proof-search agents write attempts and computations into SQLite.
4. Store large CSV/Parquet outputs externally and link them in the `artifact` table.
5. Keep every claim labeled using the project status discipline.

## Status labels

Use these for theorem, claim, attempt, and computation states:

- `PROVED`
- `CONDITIONAL`
- `COMPUTATIONAL`
- `HEURISTIC`
- `FAILED/OPEN`
- `FALSIFIED`

Strategies can also use:

- `ACTIVE`
- `DEMOTED`
- `PAUSED`
- `RESOLVED`

## Core tables

- `theorem`: theorem/lemma/frontier statements.
- `claim`: individual claims attached to a theorem.
- `strategy`: proof-search strategies and scores.
- `attempt`: prompt/result records.
- `falsification`: counterexamples, obstructions, killed routes.
- `computation`: code/data/report pointers and summary JSON.
- `formalization_job`: Lean/Aristotle/local formalization queue.
- `artifact`: files and reports linked to the proof ledger.
- `theorem_relation`: dependency graph.
- `tag`, `theorem_tag`: labels.

## Seeded current frontier

The initial seed includes the current exact frontier:

- Averaged product-fiber large sieve.
- Two-discriminant product-fiber character large sieve.
- Very-short shifted-product character sums.
- Short-box Möbius random energy.
- Final-core occupancy theorem.
- Final average bound.

It also seeds proved algebraic lemmas such as:

- product formula for `M1M2`,
- discriminant recovery identity,
- trace-zero involution facts,
- `F1` pairwise large-sieve progress.

## Why SQLite + Datasette + Streamlit

- SQLite is the canonical ledger.
- Datasette is the audit/read-only query interface.
- Streamlit is the active control dashboard.

This keeps the system simple, local-first, and easy to archive.
