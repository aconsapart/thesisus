# Hybrid Combined Attack Prompt

You are attacking the current Erdős divisor-sum frontier without restarting earlier branches.

The exact current obstruction is:

```text
M_{p1,q1} M_{p2,q2} ~ R
```

where

```text
M_{p,q} = [ -B   12-B ]
          [  A     B  ]
A = 2(q+1)-p(q-2)
B = 2(p+1)(q+1)
```

Do not use only the shifted-product multiset `w(B)` unless explicitly marked as an overcount. Retain the exact `(A,B)` constraints.

## Tasks

1. Split by product-fiber geometry:
   - lifted integer equality;
   - non-lifted finite-field congruence;
   - `Q(R)=0`;
   - `beta=0`;
   - `alpha=0`;
   - `s=0`;
   - singular `R`.

2. For lifted fibers, use integer hyperbola/divisor bounds.

3. For non-lifted fibers, use shifted-product character sums or exact `(A,B)` curve incidence.

4. For short boxes where character sums are weak, attempt near-injectivity or geometric divisor-window rigidity.

5. Falsify every branch before accepting it.

6. Return:
   - PROVED statements;
   - CONDITIONAL statements;
   - COMPUTATIONAL findings;
   - FAILED/OPEN statements;
   - sharpest remaining theorem.
