# Meta Strategy Discovery Prompt

You are not proving the theorem directly. You are looking for new strategies that are materially different from the current portfolio.

Current frontier:

```text
Exact short-box product-fiber curve incidence for the trace-zero Möbius involution family.
```

Existing broad families:

- hybrid integer/finite-field attack;
- exact `(A,B)` incidence;
- CAS pairwise degeneracy;
- averaged product-fiber large sieve;
- two-discriminant theorem;
- short-box Möbius energy;
- shifted-product character sums;
- rational exponential sums;
- inverse discrepancy;
- near-injectivity;
- divisor-window rigidity;
- low-Ω cleanup.

Return JSON list only.

Each item must include:

```json
{
  "id": "short_unique_id",
  "title": "Strategy title",
  "description": "Precise strategy and the theorem it attacks",
  "priority": 9,
  "first_falsification_test": "A concrete test that would kill or sharply revise this strategy"
}
```

Do not propose generic strategies.
