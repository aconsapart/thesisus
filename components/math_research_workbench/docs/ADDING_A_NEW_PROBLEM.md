# Adding a new problem

1. Copy `examples/generic_number_theory_problem.yaml`.
2. Fill in title, background, definitions, targets, known results, and current frontier.
3. Add a `conjectures:` block — the claims you want *attacked*, not proved.
4. Copy `examples/generic_strategy_portfolio.yaml` and edit strategies, keeping
   at least one lane in `REFUTE` mode.
5. Sweep first, before spending anything on a model:

```bash
python -m math_workbench.sweep --problem your_problem.yaml
```

6. Then run the full pipeline:

```bash
python scripts/run_agent.py \
  --problem your_problem.yaml \
  --strategies your_strategies.yaml \
  --iterations 3 \
  --parallel-strategies 3 \
  --parallel-refutations 1 \
  --out runs/your_run \
  --db proof_codex.sqlite
```

## Good frontier statements

A good frontier is precise:

- states variables and hypotheses;
- says what is already proved;
- names the exact missing theorem;
- includes known falsifications;
- gives computation/formalization targets.

Avoid vague frontiers like "solve the problem." Use "prove or disprove theorem X under hypotheses Y."

## Writing conjectures

`targets` are what you try to prove. `conjectures` are what you try to break. A
conjecture is a universally quantified claim with a predicate the searcher can
evaluate directly:

```yaml
conjectures:
  - id: divisor-count-multiplicative
    statement: "d(mn) = d(m) d(n) for all positive integers m and n."
    predicate: "divisor_count(m*n) == divisor_count(m)*divisor_count(n)"
    assumptions:
      - "gcd(m, n) == 1"        # points failing this are skipped, not counted as witnesses
    variables:
      m: {kind: integers, low: 1, high: 40}
      n: {kind: integers, low: 1, high: 40}
    notes: "Free-text; a good place to record why you suspect it is false."
```

### Domain kinds

| Kind        | Fields                          | Example                                        |
| ----------- | ------------------------------- | ---------------------------------------------- |
| `integers`  | `low`, `high`, `step`           | `{kind: integers, low: 1, high: 100}`          |
| `primes`    | `low`, `high`                   | `{kind: primes, low: 2, high: 500}`            |
| `values`    | `values` (or a bare YAML list)  | `[1, 2, "3/4"]`                                |
| `rationals` | `low`, `high`, `max_denominator`| `{kind: rationals, low: 0, high: 1, max_denominator: 8}` |

### Predicate vocabulary

Arithmetic (`+ - * / // % **`), comparison, `and`/`or`/`not`, `in`, and
conditional expressions, plus:

`abs`, `min`, `max`, `gcd`, `lcm`, `floor`, `ceiling`, `sqrt`, `factorial`,
`binomial`, `is_prime`, `divisor_count`, `divisor_sigma`, `totient`, `mobius`,
`prime`, `primepi`, `log`, `exp`.

Anything else is rejected at load time. Predicates are parsed with a whitelist
grammar, not `eval`, so attribute access, comprehensions, lambdas and imports
are refused outright — a bad predicate is a startup error rather than a
surprise three iterations into a run.

### Choosing the search space

The declared space **is** the claim you are testing. A sweep of `k in [0, 4]`
will report Fermat's conjecture `VERIFIED_EXHAUSTIVE` — correctly, and
uselessly, because the counterexample is at `k = 5`. Two habits help:

- Set bounds by what you can afford to evaluate, then say so in `notes`.
- Give the `REFUTE` lanes something to do outside the box. Their whole purpose
  is proposing witnesses the smallest-first sweep will never reach.

Enumeration is diagonal, so multi-variable spaces get explored in every variable
at once. You do not need to keep the ranges small to reach the second variable.

### Budget

Machine-side limits come from `search:` in `config/local_settings.yaml`; a
problem's `refutation:` block overrides them:

```yaml
refutation:
  max_evaluations: 4000
  random_samples: 200      # sampled only after exhaustive enumeration is exhausted
  time_limit_s: 20.0
  max_witnesses: 3
  seed: 20240729           # sampling is seeded, so runs are reproducible
```

## Reading the results

| Status                 | What it means                                                        |
| ---------------------- | -------------------------------------------------------------------- |
| `FALSIFIED`            | a witness was found and independently checked                        |
| `VERIFIED_EXHAUSTIVE`  | no witness exists in the declared space — a proof over that space only |
| `OPEN`                 | the budget ran out; nothing was settled                              |
| `CONTESTED`            | the two evaluators disagreed; a bug to fix before trusting the run    |

A `CONTESTED` result is not a mathematical finding. It means the rational
evaluator and the symbolic evaluator reached different conclusions about the
same assignment, so one of them is wrong. Fix that before reading anything else
from the run.

## A worked example

`examples/counterexample_demo_problem.yaml` declares six conjectures whose true
status is already settled mathematics: three are false (Euler's prime
polynomial, Fermat primes, Mersenne exponents), one is false and then repaired
by adding a coprimality hypothesis, and two hold throughout their space. It is
the fastest way to confirm the machinery reports what it should before you
point it at a claim whose answer you do not already know.
