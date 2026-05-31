# Hybrid Attack and Strategy Discovery Lanes

This version adds two automation lanes to the existing multi-strategy proof-search scaffold.

## 1. Hybrid combined attack

Strategy id:

```text
hybrid_combined_attack
```

Purpose:

Combine the currently strongest partial routes instead of treating them as competitors:

- integer hyperbola / divisor bounds for lifted or small-`Q(R)` fibers;
- finite-field shifted-product and character-sum methods for large non-lifted fibers;
- exact `(A,B)`-curve incidence to avoid overcounting by `w(B)` alone;
- near-injectivity / collision-energy fallback;
- geometric divisor-window rigidity for final-core divisors.

The lane is intended to attack the current exact obstruction:

```text
M_{p1,q1} M_{p2,q2} ~ R
```

while keeping both exact constraints:

```text
A_i = 2(q_i+1)-p_i(q_i-2)
B_i = 2(p_i+1)(q_i+1)
```

rather than only the shifted product `B_i`.

## 2. Meta-strategy discovery

Strategy id:

```text
meta_strategy_discovery
```

Purpose:

Look for materially new strategies and falsification tests. This lane is deliberately conservative:

- it must propose a first falsification test;
- it must avoid generic “try everything” strategies;
- it only appends new strategies whose IDs are not already in the portfolio.

The graph node `node_discover_strategies` runs after each synthesis step and can append up to three newly discovered strategies to later iterations.

## New graph flow

```text
select_strategies
  -> run_strategies
  -> symbolic_checks
  -> cas_degeneracy
  -> generate_formal_tasks
  -> run_formalization
  -> synthesize
  -> discover_strategies
  -> increment or end
```

## Output artifacts

Each iteration may now include:

```text
strategy_hybrid_combined_attack.md
strategy_meta_strategy_discovery.md
strategy_discovery_raw.json
strategy_discovery_report.md
```

## Practical advice

Run with at least 4 parallel strategies to include the hybrid lane, meta-discovery lane, exact `(A,B)` curve lane, and CAS degeneracy lane together:

```bash
python src/erdos_agent.py --iterations 4 --parallel-strategies 4 --out runs/hybrid_run_001
```
