# Architecture

This workbench is problem-agnostic, and it works two tracks at once: proving
statements and refuting them.

## Core abstractions

- `ProblemSpec`: definitions, **targets** (what to prove), **conjectures**
  (what to break), known results, current frontier.
- `Conjecture`: a universally quantified claim with a machine-checkable
  predicate over declared variable domains. This is the refutable counterpart
  of a theorem -- a counterexample search can act on it with no model involved.
- `StrategySpec`: a ranked lane with a `mode` of `PROVE`, `REFUTE`, or `BOTH`.
  Refutation lanes are scheduled from their own budget so proof lanes cannot
  crowd them out.
- `Witness`: a concrete assignment offered as a counterexample, carrying the
  record of how it was checked.
- `Theorem ledger`: SQLite tables for theorem states, conjectures,
  counterexamples, claims, attempts, computations, and formalization jobs.
- `LangGraph workflow`: iterative stateful search over both tracks.

## Graph

```text
select_strategies
  -> search_counterexamples      deterministic sweep, no model
  -> refute_lanes                model-proposed witnesses, each re-checked
  -> assess_refutation
       |-- frontier falsified --> repair ---------------> synthesize
       `-- survived ------------> run_strategies
                                  -> symbolic_checks
                                  -> cas_degeneracy
                                  -> formalization -----> synthesize
  -> discover
  -> repeat
```

Refutation runs **before** the proof lanes and can divert the iteration. Proving
a statement that has a verified counterexample is the most expensive mistake the
pipeline can make, so when the frontier dies the iteration goes straight to
repair, and the next iteration's proof lanes get the repaired statement instead.

## The verification discipline

Every witness -- whether the deterministic sweep found it or a model proposed it
-- is evaluated twice by independent implementations:

1. a **SymPy path**: exact symbolic arithmetic and SymPy's number theory;
2. a **rational path**: `int`/`Fraction` with hand-written number theory
   (Euclid's algorithm, Miller-Rabin, trial-division factorisation).

The verdicts, strongest first:

| Verdict           | Meaning                                                        |
| ----------------- | -------------------------------------------------------------- |
| `VERIFIED_EXACT`  | both evaluators agree the predicate fails here                  |
| `VERIFIED_SINGLE` | only one evaluator could decide; weaker evidence, labelled so   |
| `CONTESTED`       | the evaluators disagree -- a bug in one of them, never evidence |
| `REJECTED`        | not a counterexample (predicate holds, or assumptions fail)     |
| `UNCHECKED`       | could not be evaluated at all                                   |

`CONTESTED` outranks `FALSIFIED` at the conjecture level, deliberately. If an
evaluator is demonstrably wrong somewhere in a search, its verdicts elsewhere in
that same search are not trustworthy either, so witnesses found alongside a
disagreement are withheld rather than promoted. Reporting the refutation and
quietly dropping the disagreement is how a wrong result ships.

The rational path refuses to approximate. Asked for `sqrt(2)` it abstains rather
than comparing floats, which downgrades the witness to `VERIFIED_SINGLE` instead
of manufacturing false agreement.

## What a search can conclude

A search over a finite declared space has three honest outcomes:

- `FALSIFIED` -- a witness was found and checked.
- `VERIFIED_EXHAUSTIVE` -- every point was evaluated, without error, and none
  refuted the claim. This proves the statement **over that space and nowhere
  else**, and the reports say so every time.
- `OPEN` -- the budget ran out, or some points failed to evaluate. Nothing was
  settled. Exhaustive verification is withheld when any point errored: covering
  the space is not enough, the coverage has to have worked.

## Enumeration order

Search enumerates *diagonally*, by increasing sum of variable indices, rather
than lexicographically. Over `m, n in [1, 10^4]`, `itertools.product` would
spend an entire 5000-point budget on `n = 1`; the diagonal order finds
`d(mn) = d(m)d(n)`'s counterexample at `m = n = 2` within a dozen evaluations.
The first witness found is therefore minimal in search order, and is flagged.

## Predicates are untrusted input

Predicates come from YAML written by a collaborator, or from a model proposing a
repair. They are parsed with a whitelist grammar over an AST -- no attribute
access, no comprehensions, no lambdas, no calls to anything outside a fixed
function table -- and never handed to `eval` on an open namespace. Unbounded
operations (`**`, `factorial`, factorisation) are capped and fail loudly rather
than hanging.

## Why this generalizes

To use a new math problem, provide:

1. a problem YAML file, with `targets` to prove and `conjectures` to break;
2. a strategy portfolio YAML file with lanes in both modes;
3. optional domain-specific CAS scripts or computation nodes.

No Erdős-specific theorem is hardcoded, except in the provided example spec.

## Running the refutation track alone

The sweep is deterministic and needs no model, no API key, and no LangGraph:

```bash
python -m math_workbench.sweep --problem examples/counterexample_demo_problem.yaml
```

Exit code 1 means something was falsified -- which is a *successful* run of that
tool. Exit code 2 means an evaluator disagreement was found and must be
investigated before the run is trusted. This makes the sweep usable as a CI check
on a problem spec.
