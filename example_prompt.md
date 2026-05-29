You are continuing the Erdős divisor-sum project.

Core setup:

    K(n)=3n+12-2σ(n),
    s(n)=σ(n)-n,

and

    A(n)=#{ d | K(n):
            d<K(n)/d,
            d+K(n)/d<=s(n)-11 }.

The primitive semiprime-side count satisfies

    S(n)<=A(n).

All broad reductions have already been performed. Do not restart from earlier branches unless needed for a consistency check.

Every claim must be labeled as one of:

    PROVED
    CONDITIONAL
    COMPUTATIONAL
    HEURISTIC
    FAILED/OPEN

Do not overclaim.

============================================================
CURRENT EXACT FRONTIER
============================================================

The surviving obstruction is the very-short shifted-product branch arising from the off-identity product energy of the trace-zero Möbius involution family.

For the dominant branch m=uv, the final congruence is

    Auv+B(u+v)+C ≡ 0 mod ell,

where

    A=2(q+1)-p(q-2),
    B=2(q+1)(p+1),
    C=B-12.

Solving for u gives the Möbius transformation

    u = (-Bv-C)/(Av+B) mod ell.

The associated matrix is

    M_{p,q} =
        [ -B   12-B ]
        [  A     B  ].

Known facts:

    PROVED: tr(M_{p,q})=0.
    PROVED: M_{p,q}^2=(B^2-AC)I.
    PROVED: nondegenerate T_{p,q} are projective involutions.
    PROVED: projective equality T_{p,q}=T_{p',q'} implies {p,q}={p',q'} mod ell, assuming ell∤6.
    PROVED: no point-stabilizer concentration.
    PROVED: no repeated fixed-point-pair concentration.
    COMPUTATIONAL: map multiplicity, product energy, and inverse-hit statistics are random-like.

The short-box energy target is

    E(T_{P,Q})
    << ( |T_{P,Q}|^2 + |T_{P,Q}|^4/ell^3 ) (log X)^C.

The off-identity product-fiber reduction gives rational functions F evaluated at

    z = 2(p+1)(q+1).

The current sharp analytic theorem is:

    sum_{p~P,q~Q}
        χ(F(2(p+1)(q+1)))
    << PQ (log X)^(-A)

for all relevant nondegenerate rational functions F in the very-short range

    PQ <= ell polylog(X).

============================================================
PRIMARY TASK: VERY-SHORT SHIFTED-PRODUCT CHARACTER SUMS
============================================================

Focus on this theorem first. Do not switch to other strategies until this theorem is either:

    - proved,
    - disproved by a concrete obstruction,
    - or reduced to a strictly sharper theorem.

Tasks:

1. Re-derive the off-identity product-fiber formula.

   Verify

       M1 M2 =
       [ A2(12-B1)+B1B2       12(B2-B1)       ]
       [ B1A2-A1B2             A1(12-B2)+B1B2 ]

2. For a fixed nonidentity projective product

       R = [ r s ]
           [ t u ],

   handle separately:

       s≠0,
       s=0,
       α=r-s+t-u≠0,
       α=0.

3. In the s≠0 and α≠0 branch, verify the shifted-product hyperbola:

       (αB1-12(t-u))(αB2-12(r+t))
       =
       144((t-u)(r+t)-αt) mod ell.

4. Parameterize the product fiber by

       z=B1=2(p1+1)(q1+1),

   and derive rational functions F1(z), F2(z) whose quadratic-character conditions determine whether the corresponding (A_i,B_i) recover valid p_i,q_i.

5. Classify algebraic degeneracies.

   Search for:

       F_i(z)=c z^k G(z)^2,
       constant-character cases,
       pole collapses,
       α=0 special families,
       s=0 special families,
       Q(R)=0 discriminant collapse,
       denominator-zero families.

   If a degeneration produces infinite families, state them explicitly.

6. If F is nondegenerate, prove the available bilinear estimate:

       |sum_{p~P,q~Q} χ(F(2(p+1)(q+1)))|
       << sqrt(ell π(P)π(Q)).

   Use:

       multiplicative Fourier inversion,
       Cauchy-Schwarz,
       character orthogonality,
       Weil bound for complete multiplicative character twists.

7. State exactly what this proves.

   It should prove the branch

       PQ >> ell (log X)^B.

8. Attack the remaining very-short branch

       PQ <= ell polylog(X).

   Try, in order:

       A. Burgess-type bounds in p or q.
       B. Bilinear character sums over shifted prime products.
       C. Trilinear / quadrilinear finite-field character-sum technology.
       D. Bourgain-Garaev-Konyagin-Shparlinski shifted-product congruence methods.
       E. Sum-product/additive-combinatorics input.
       F. Prime-specific cancellation from p+1, q+1.

9. If very-short cancellation cannot be proved, isolate the exact missing theorem.

   It should have the form:

       Very-Short Shifted-Product Character-Sum Theorem:
       For all nondegenerate rational functions F from off-identity product fibers,

           sum_{p~P,q~Q}
               χ(F(2(p+1)(q+1)))
           << PQ(log X)^(-A)

       in the final-core range PQ <= ell polylog(X), with necessary lower-size hypotheses.

10. Convert any proven result back into:

       shifted-product character sums
       -> off-identity Möbius energy
       -> Möbius incidence
       -> final-core occupancy
       -> rank-two branch
       -> sum_{n<=X} A(n) << X(log X)^C.

============================================================
SECONDARY TASKS IF TARGET 1 STALLS
============================================================

If Target 1 stalls, do not restart the whole project. Continue only through strategies directly connected to the same obstruction.

A. Short-box Möbius energy

    Try to prove

        E(T_{P,Q})
        << ( |T|^2 + |T|^4/ell^3 )(log X)^C.

    Focus on off-identity product fibers.

B. Rational exponential sums

    Try to prove cancellation in

        sum_{u~U,v~V,q~Q}
            e_ell(h J/H)

    for h≠0, especially in large-volume branches.

C. Near-injectivity

    Try to prove

        sum_N r(N)^2 << MPQ(log X)^C.

    Use the already observed near-injectivity as a guide, but do not treat computation as proof.

D. Geometric divisor-window rigidity

    Use

        a | H_0p-J_0,
        a > max(p,q)logX/g,
        ga^2 < H_0p-J_0 < aH/logX.

    Retain all geometric constraints. Do not use coefficient-free Hooley-Delta.

E. Low-Ω cleanup

    Use

        σ(m)/m < 3q/(2(q+1)) < 3/2

    only as branch cleanup, not as the main route.

============================================================
FALSIFICATION RULES
============================================================

Before accepting any theorem, try to falsify it by:

    - explicit counterexamples,
    - scaling contradictions,
    - hidden degeneracies,
    - square rational functions,
    - fiber multiplicity explosions,
    - constant-character cases,
    - subgroup concentration,
    - failure in tiny boxes,
    - random-model mismatch.

If falsified, state the counterexample or obstruction and revise the theorem.

============================================================
OUTPUT FORMAT
============================================================

Return:

1. PROVED statements.
2. CONDITIONAL statements.
3. COMPUTATIONAL findings.
4. HEURISTIC interpretations.
5. FAILED/OPEN statements.
6. Falsified strategies.
7. Sharpest remaining theorem.
8. Whether the full project is resolved.
9. If unresolved, the exact next theorem and why it is the true obstruction.

Do not overclaim.
