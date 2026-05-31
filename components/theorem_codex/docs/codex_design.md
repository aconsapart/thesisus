# Theorem Codex Design

## Goal

This is a theorem-focused codex, not only a dashboard. The central object is a theorem/lemma/frontier statement with:

- formal or informal statement,
- proof status,
- claims,
- dependencies,
- proof attempts,
- falsifications,
- computations,
- formalization jobs,
- artifacts and reports.

## Canonical storage

SQLite is the canonical ledger. All frontends should read from and write to SQLite.

Datasette is a read-only exploration and audit surface. It is ideal for SQL queries, filters, JSON API access, and publishing the ledger.

Streamlit is the active control panel. It is ideal for adding theorems, attempts, falsifications, strategy status changes, and browsing graphs and diagnostics.

## Important design principle

The system should preserve failed paths as first-class records. In a proof-search project, falsified strategies are as valuable as proved lemmas because they prevent repeated dead ends.

## Status discipline

Every claim must be one of:

- PROVED
- CONDITIONAL
- COMPUTATIONAL
- HEURISTIC
- FAILED/OPEN
- FALSIFIED

## Theorem dependency graph

Use `theorem_relation` to record chains such as:

```text
averaged_product_fiber_large_sieve
  depends_on two_discriminant_product_fiber_large_sieve
  supported_by F1_pairwise_large_sieve
```

The dependency graph is how the codex remembers what theorem would finish which branch.
