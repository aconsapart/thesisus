# Thesius Workbench

A reusable, problem-agnostic automation scaffold for mathematical research that
works two tracks at once: **proving statements and refuting them**.

It generalizes the Erdős divisor-sum workflow into a configurable system that can be used for arbitrary math problems:

- theorem/frontier tracking in SQLite;
- **executable conjectures and an automated counterexample search**;
- **independent double-checking of every witness before it is believed**;
- strategy portfolio execution with separate proof and refutation lanes;
- symbolic/CAS hooks;
- optional Lean/Aristotle formalization hooks;
- optional Datasette read-only theorem codex;
- optional Streamlit control dashboard;
- LangGraph orchestration for stateful, iterative search.

## Core idea

A counterexample is a result, not a setback. It settles a question, and it is
usually far cheaper to find than a proof. So the workbench treats refutation as
a peer of proof rather than as advice in a prompt: conjectures are first-class
objects with their own ledger, their own lanes, and their own budget.

Every run maintains a state containing:

- current theorem/frontier;
- known definitions and constraints;
- ranked strategies, in `PROVE` and `REFUTE` modes;
- proof ledger;
- **conjectures, their search verdicts, and every witness with its verification status**;
- computation artifacts;
- formalization jobs;
- sharpest remaining theorem.

Each iteration follows:

```text
load problem spec
  -> select strategies (refutation lanes reserved first)
  -> sweep every conjecture for counterexamples   [deterministic, no model]
  -> run refutation lanes and check each proposed witness
  -> assess
       falsified? -> repair: the strongest statement the witness does not kill
       survived?  -> attempt proof or reduction
                     -> run symbolic/computational checks
                     -> generate optional formalization tasks
  -> synthesize status
  -> discover or demote strategies
  -> persist to SQLite
```

Refutation runs *before* the proof lanes and can divert the iteration. Spending
a proof budget on a statement that has a verified counterexample is the most
expensive mistake available, so when the frontier dies the run repairs it and
the next iteration attacks the repaired statement.

## Try the refutation track in ten seconds

No model, no API key, no LangGraph:

```bash
python -m math_workbench.sweep --problem examples/counterexample_demo_problem.yaml
```

Six conjectures whose status is already settled mathematics. Three are refuted
with explicit witnesses (Euler's `n^2+n+41` at `n = 40`, Fermat's `F_5`,
Mersenne's `2^11-1`), one is refuted and then repaired by adding a coprimality
hypothesis, and two hold throughout their declared space.

Exit code 1 means something was falsified — a *successful* run of that tool.
Exit code 2 means the two evaluators disagreed somewhere and the run should not
be trusted until that is fixed.

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

## Sweep for counterexamples only

Deterministic, reproducible, and free. Worth running before committing to a
proof campaign, and usable as a CI check on a problem spec.

```bash
python -m math_workbench.sweep \
  --problem examples/counterexample_demo_problem.yaml \
  --db proof_codex.sqlite \
  --out runs/sweep/report.md
```

## Initialize codex only

```bash
python scripts/init_codex.py --db proof_codex.sqlite
python scripts/seed_problem.py --db proof_codex.sqlite --problem examples/generic_number_theory_problem.yaml
```

## Tests

```bash
pip install pytest
python -m pytest tests/
```

The refutation track is tested without langchain, langgraph, or an API key —
only sympy and pyyaml. The graph tests are skipped automatically if the
`agents` extra is not installed. Among other things the suite pins the demo
problem's verdicts against known mathematics, so if Euler's polynomial stops
being reported as falsified at `n = 40`, the build fails.

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
conjectures:
  - id: "claim-to-break"
    statement: "..."
    predicate: "is_prime(n*n + n + 41)"
    assumptions: ["n > 0"]
    variables:
      n: {kind: integers, low: 0, high: 100}
known_results:
  - status: "PROVED"
    statement: "..."
current_frontier: "..."
falsification_tests:
  - "search for small counterexamples"
formalization_targets:
  - "prove algebraic identity in Lean"
refutation:
  max_evaluations: 4000
  time_limit_s: 20.0
```

Unknown top-level keys are rejected at load time. A silently ignored
`conjecture:` typo would disable the entire refutation track, which is exactly
the kind of failure that is invisible until it matters.

## Status labels

The system expects claims to use only:

- `PROVED`
- `CONDITIONAL`
- `COMPUTATIONAL`
- `HEURISTIC`
- `FAILED/OPEN`
- `FALSIFIED`

`FALSIFIED` and `FAILED/OPEN` are not the same thing, and the distinction is the
point: `FALSIFIED` means the question is settled negatively and here is the
witness; `FAILED/OPEN` means nothing was settled. Keeping them apart is what
keeps the theorem ledger honest.

Running against a database created before this was added? `init_db` migrates it
in place — SQLite cannot alter a CHECK constraint, so the affected tables are
rebuilt and the report tells you what changed.

## Conjectures

`targets` are what you try to prove. `conjectures` are what you try to break:

```yaml
conjectures:
  - id: divisor-count-multiplicative
    statement: "d(mn) = d(m) d(n) for all positive integers m and n."
    predicate: "divisor_count(m*n) == divisor_count(m)*divisor_count(n)"
    variables:
      m: {kind: integers, low: 1, high: 40}
      n: {kind: integers, low: 1, high: 40}
```

The sweep finds `m = n = 2` in a dozen evaluations. See
[docs/ADDING_A_NEW_PROBLEM.md](docs/ADDING_A_NEW_PROBLEM.md) for the domain
kinds, the predicate vocabulary, and how to choose a search space.

Predicates are parsed with a whitelist grammar rather than `eval`: no attribute
access, no comprehensions, no imports, and a fixed table of mathematical
functions. A bad predicate fails at load time, not three iterations into a run.

## How a counterexample earns belief

Every witness — found by the sweep or proposed by a model — is evaluated twice,
by independent implementations: SymPy's exact arithmetic, and a pure-Python
`Fraction` path with hand-written Euclid, Miller-Rabin, and trial-division
factorisation.

| Verdict           | Meaning                                                        |
| ----------------- | -------------------------------------------------------------- |
| `VERIFIED_EXACT`  | both evaluators agree the predicate fails here                  |
| `VERIFIED_SINGLE` | only one evaluator could decide; weaker, and labelled so        |
| `CONTESTED`       | the evaluators disagree — a bug in one of them, never evidence  |
| `REJECTED`        | not a counterexample (predicate holds, or assumptions fail)     |
| `UNCHECKED`       | could not be evaluated at all                                   |

Witnesses a model claims are routinely wrong, so they are re-checked before
being recorded, and the ones that fail are kept on record as discarded — a lane
that keeps proposing dead assignments is a lane worth demoting.

A search that exhausts its whole space without a witness reports
`VERIFIED_EXHAUSTIVE`: a proof over *that space only*, stated that way every
time it appears. If any point failed to evaluate, exhaustive verification is
withheld — covering the space is not enough, the coverage has to have worked.

## Strategy design

Strategies are configured in YAML. A strategy contains:

- `id`
- `name`
- `rank`
- `mode` — `PROVE`, `REFUTE`, or `BOTH`
- `description`
- `allowed_tools`
- `falsification_prompts`
- `counterexample_prompts` — used by `REFUTE` lanes
- `proof_prompts`
- `target_conjectures` — optional, restricts a lane to specific conjectures
- `success_criteria`
- `failure_modes`

Refutation lanes are filled from their own budget (`--parallel-refutations`)
before proof lanes are selected, so ranking cannot quietly starve the
refutation track — which is exactly how the previous version of this pipeline
ended up never falsifying anything.

The workbench ships with generic strategies:

1. exact algebraic reduction (`PROVE`);
2. boundary and degenerate case hunt (`REFUTE`);
3. algebraic coincidence search (`REFUTE`) — for witnesses too large for the sweep;
4. symbolic/CAS degeneracy classification (`BOTH`);
5. averaged second moment (`PROVE`);
6. asymptotic/scaling falsification (`REFUTE`);
7. formalization in Lean (`PROVE`);
8. strategy discovery (`BOTH`).

## Front ends

Use both:

- SQLite as the canonical ledger;
- Datasette for read-only browsing/search/query;
- Streamlit for active strategy control and dashboards.

## Important caveat

This is a research workbench, not a theorem prover. It helps organize, falsify,
compute, and formalize. Mathematical correctness still depends on explicit
proofs or verified formalizations.

Two limits worth stating plainly:

- **A verified counterexample is a real refutation; an exhausted search is not a
  proof.** `VERIFIED_EXHAUSTIVE` means no witness exists in the *declared
  space*. Fermat's conjecture survives an exhaustive sweep of `k in [0, 4]`. The
  declared space is the claim you are actually testing, and choosing it badly is
  the easiest way to get a confident, worthless answer.
- **The refutation track only sees what you make executable.** A statement not
  expressible as a predicate over declared domains cannot be swept, and falls
  back to model-proposed witnesses — which are checked, but only found by
  guessing.
