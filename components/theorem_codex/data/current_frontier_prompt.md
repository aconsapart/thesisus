You are continuing the Erdős divisor-sum project.

The goal is to prove, if possible,

    sum_{n<=X} A(n) << X(log X)^C,

where

    K(n)=3n+12-2σ(n),
    s(n)=σ(n)-n,

and

    A(n)=#{ d | K(n):
            d<K(n)/d,
            d+K(n)/d<=s(n)-11 }.

The primitive semiprime-side solution count satisfies

    S(n)<=A(n).

Do not overclaim. Every claim must be labeled as one of:

    PROVED
    CONDITIONAL
    COMPUTATIONAL
    HEURISTIC
    FAILED/OPEN

Your task is to continue through the ranked proof targets below until either:

    1. the full theorem sum A(n)<<X(log X)^C is proved;
    2. or the proof is reduced to a strictly sharper, explicitly stated theorem than the current frontier.

Falsification is mandatory. Before pursuing any theorem deeply, first try to disprove it by:

    - explicit counterexamples,
    - scaling contradictions,
    - hidden degeneracies,
    - concentration examples,
    - fiber-multiplicity explosions,
    - random-model failure,
    - incompatible known lower bounds.

If a strategy fails, do not stop. Record why it fails, sharpen the theorem, and move to the next ranked target.

============================================================
CURRENT FINAL FRONTIER
============================================================

The remaining obstruction is in the final rank-two core.

Write

    n=mpq,

where p,q are unitary primes.

For fixed m,q define

    H=(q-2)m-2(q+1)s(m),
    J=2(q+1)σ(m)-12.

Then

    K(mpq)=Hp-J.

If

    K(mpq)=de,

and

    g=(H,d),
    H=gH_0,
    d=ga,
    J=gJ_0,

then

    H_0 p - a e = J_0,

so

    a | H_0 p - J_0.

The final-core inequalities give

    a > max(p,q) log X / g,

and

    g a^2 < H_0 p - J_0 < aH/log X.

The rough-a branch is dominant. Often a has a large prime factor ell>P, frequently a=ell prime. Then

    p ≡ J_0 H_0^{-1} mod ell.

The final obstruction is equivalent to showing that these structured inverse residues rarely hit p~P.

============================================================
DOMINANT LOW-Ω BRANCH
============================================================

Computation shows the final core is dominated by

    m=uv     squarefree semiprime,
    m=r^2   prime square.

For m=uv:

    s(m)=u+v+1,

and the inverse-hit condition becomes

    J(u,v,q) ≡ p H(u,v,q) mod ell.

Equivalently,

    Auv+B(u+v)+C ≡ 0 mod ell,

where

    A=2(q+1)-p(q-2),
    B=2(q+1)(p+1),
    C=B-12.

Solving for u gives a Möbius transformation:

    u = (-Bv-C)/(Av+B) mod ell.

The corresponding matrix is

    M_{p,q} =
        [ -B   12-B ]
        [  A     B  ].

Known facts:

    PROVED: tr(M_{p,q})=0.
    PROVED: M_{p,q}^2=(B^2-AC)I.
    PROVED: nondegenerate transformations are projective involutions.
    PROVED: projective equality T_{p,q}=T_{p',q'} implies {p,q}={p',q'} mod ell, assuming ell∤6.
    PROVED: no point-stabilizer concentration in the tested algebraic sense.
    PROVED: no repeated fixed-point-pair concentration.
    COMPUTATIONAL: actual data shows low map multiplicity, low energy, no catastrophic degeneracy.

For m=r^2, the inverse-hit condition becomes a quadratic congruence in r.

============================================================
RANKED TARGETS
============================================================

Work through these in order. If a target proves enough, combine the proof chain and finish the project. If it fails, record the failure and proceed.

------------------------------------------------------------
TARGET 1 — SHIFTED-PRODUCT CHARACTER SUMS
------------------------------------------------------------

This is currently the most concrete short-box analytic theorem.

The off-identity Möbius product-energy problem reduces to square-discriminant conditions over

    B=2(p+1)(q+1).

A key target is:

    sum_{p~P, q~Q} χ(F(2(p+1)(q+1)))
        << PQ (log X)^(-A)

for all relevant nondegenerate rational functions F, where χ is the quadratic character modulo ell.

Tasks:

1. Derive explicitly the rational functions F arising from fixed off-identity product fibers

       M_{p1,q1} M_{p2,q2} ~ R.

2. Verify the product formula:

       M1 M2 =
       [ A2(12-B1)+B1B2       12(B2-B1)          ]
       [ B1A2-A1B2             A1(12-B2)+B1B2    ].

3. For s≠0 and α=r-s+t-u≠0, confirm the shifted-product hyperbola:

       (αB1-12(t-u))(αB2-12(r+t))
       =
       144((t-u)(r+t)-αt)     mod ell.

4. Reduce validity of each (A_i,B_i) to the square discriminant condition for recovering p_i,q_i.

5. Falsify the target by searching whether some F is square-degenerate:

       F(z)=c z^k G(z)^2

   or produces χ(F(z)) constant.

6. If nondegenerate, prove the bilinear character estimate by multiplicative Fourier:

       Let A={2(p+1)}, B={q+1}, z=ab.
       Prove

       |sum_{a in A, b in B} χ(F(ab))|
           << sqrt(ell |A||B|)

   assuming the complete character sums

       sum_z ψ(z)χ(F(z)) <<_F sqrt(ell)

   for all multiplicative characters ψ.

7. Determine the range this proves:

       PQ >> ell (log X)^B.

8. If the theorem only proves a large-product branch, isolate the remaining very-short branch

       PQ <= ell polylog(X).

9. Try to improve using bilinear/trilinear/quadrilinear character-sum technology.

10. If still incomplete, state the exact shifted-product character-sum theorem needed.

------------------------------------------------------------
TARGET 2 — RATIONAL EXPONENTIAL SUMS / TRACE FUNCTIONS
------------------------------------------------------------

For the large-volume branch, attack the rational-map equidistribution directly.

For m=uv define

    H=(q-2)uv-2(q+1)(u+v+1),
    J=2(q+1)(uv+u+v+1)-12.

The desired cancellation is in sums of the form

    sum_{u~U, v~V, q~Q}
        e_ell( h J(u,v,q) / H(u,v,q) )

for h≠0 mod ell.

Tasks:

1. Check algebraic nondegeneracy:
       - H not identically zero.
       - J/H not reducible to an additive character of a low-degree trivial form.
       - no large fiber degeneracy J=λH.

2. Prove complete-sum cancellation using Weil/Deligne-type bounds if possible.

3. Use completion to intervals and determine the exact volume threshold.

4. Compare against current diagnostics:
       semiprime large-volume branch around PUVQ >> ell^(5/2);
       prime-square branch around PRQ >> ell^2.

5. If complete-sum completion is insufficient, formulate a Type-II rational exponential-sum theorem.

6. Try to use averaging over p,q,ell,h to beat completion losses.

7. If impossible, isolate the exact trace-function theorem needed.

------------------------------------------------------------
TARGET 3 — SHORT-BOX MÖBIUS RANDOM ENERGY
------------------------------------------------------------

Let

    T_{P,Q}={T_{p,q}: p~P, q~Q} subset PGL_2(F_ell).

The energy is

    E(T)=#{T1 T2^{-1}=T3 T4^{-1}}.

Since each T is an involution, this is

    E(T)=#{T1 T2 = T3 T4}.

The correct random scale is

    E(T) << ( |T|^2 + |T|^4/ell^3 ) (log X)^C.

Tasks:

1. Reprove:
       - trace-zero involution,
       - projective injectivity,
       - full-field energy E(T_full)<<ell^5.

2. Decompose

       E(T)=|T|^2 + E_off(T),

   where |T|^2 is the forced identity diagonal from T^2=id.

3. Derive the off-identity product-fiber formula.

4. Prove or falsify random-size off-identity product fibers.

5. Use the shifted-product character-sum target from TARGET 1 to prove E_off if possible.

6. If character sums do not suffice, attempt product-growth/approximate-subgroup logic:

       High energy -> approximate subgroup-like subset.
       Show such concentration forces:
           point stabilizer concentration,
           fixed-point-pair concentration,
           torus-normalizer concentration,
           exceptional subgroup concentration.

7. Use already proved nonconcentration facts:
       - no map collapse,
       - no point-stabilizer concentration,
       - no fixed-point-pair concentration.

8. Prove missing subgroup nonconcentration if possible.

9. If product-growth gives only power savings, state the exact gap to random energy.

10. If energy is proved, combine with Warren–Wheeler Möbius incidence to bound incidences.

------------------------------------------------------------
TARGET 4 — MODULAR INVERSE DISCREPANCY
------------------------------------------------------------

In the prime-a rough branch:

    a=ell prime,
    ell>P,
    ell>Q usually,

and

    p ≡ J_0 H_0^{-1} mod ell.

Target:

    sum_{m,q,g,ell}
      ( 1_{J_0 H_0^{-1} in [P,2P]}
        - (# primes in [P,2P])/ell )
      << Q(log X)^C.

Tasks:

1. Express H,J,H_0,J_0 explicitly for m=uv and m=r^2.

2. Compare this with known modular inverse discrepancy theorems.

3. Attempt a Kloosterman/dispersion setup:
       use additive characters for the interval condition,
       reduce to sums over e_ell(h JH^{-1}).

4. Falsify by checking whether residues cluster for fixed ell, q, m-type.

5. If no clustering, state a structured modular-inverse discrepancy theorem.

6. Determine whether this theorem is weaker, stronger, or equivalent to TARGET 2.

------------------------------------------------------------
TARGET 5 — NEAR-INJECTIVITY / COLLISION ENERGY
------------------------------------------------------------

Try to bypass inverse-distribution.

Define

    r(N)=#{(m,p,q): K(mpq)=N}.

Target:

    sum_N r(N)^2 << MPQ(log X)^C.

Tasks:

1. Split collisions:
       m=m',
       m≠m',
       same H,J,
       same K-value via affine line intersections.

2. Use the already observed near-injectivity:
       computationally 511 triples, 508 distinct K-values.

3. For m=uv and m'=u'v', write collision equations explicitly.

4. Use the determinant form:

       K(mpq)=Hp-J.

5. Try to prove that

       Hp-J = H'p'-J'

   forces equality or rare algebraic coincidences.

6. Search for and classify collision families.

7. If a collision family exists, isolate it and prove it contributes polylog.

8. If near-injectivity is proved, combine with global Hooley-Delta moments by Cauchy-Schwarz.

------------------------------------------------------------
TARGET 6 — GEOMETRIC DIVISOR-WINDOW RIGIDITY
------------------------------------------------------------

Use the final-core divisor window:

    a | H_0 p - J_0,

with

    a > max(p,q) log X / g,

and

    g a^2 < H_0 p - J_0 < aH/log X.

Tasks:

1. Determine whether admissible a must be near sqrt(H_0 p/g).

2. Bound the width of the allowed divisor interval.

3. Try to prove that a number H_0p-J_0 cannot have many divisors in this moving interval on average.

4. Split by:
       rough a,
       smooth a,
       prime a,
       large g,
       small g.

5. Use Hooley-Delta estimates only after retaining the full geometric constraints.

6. If generic divisor estimates are too weak, isolate the exact geometric divisor-window theorem.

------------------------------------------------------------
TARGET 7 — DEFICIENCY / LOW-OMEGA SIEVE
------------------------------------------------------------

The final core forces

    σ(m)/m < 3q/(2(q+1)) < 3/2.

Tasks:

1. Try to prove high-Ω(m) negligibility:

       Ω(m)>=3 contributes << Q(log X)^C.

2. Use forbidden divisor machinery:
       if r|m and σ(r)/r >= 3/2, exclude or bound.

3. Reduce as much as possible to:
       m=uv,
       m=r^2.

4. If high-Ω is not negligible, classify surviving patterns:
       r^3,
       r^2s,
       other.

5. Combine with low-Ω Diophantine equations:
       m=r:
           r=(de+B-12)/D.
       m=r^2:
           B^2+4D(B+de-12)=z^2.
       m=uv:
           (Du-B)(Dv-B)=D(de+B-12)+B^2.

6. If this cannot prove occupancy alone, keep it as branch cleanup.

============================================================
COMPUTATIONAL TASKS
============================================================

At every stage, run diagnostics to falsify strategies.

Use stored final-core data if available.

Compute:

1. Degeneracy of F in shifted-product character sums.
2. Complete-sum nondegeneracy checks.
3. Energy E(T) and E_off(T) by ell.
4. Product-fiber multiplicity for M1M2.
5. Map multiplicity of T_{p,q}.
6. Subgroup concentration:
       point stabilizer,
       fixed-point pair,
       torus-like clustering,
       exceptional repeated fibers.
7. Inverse-hit actual vs expected:
       actual hits / sum prime_count(P)/ell.
8. Large-volume coverage.
9. Short-box remaining branch.
10. Collision-energy r(N)^2.
11. Divisor-window Δ for H_0p-J_0.
12. Low-Ω distribution of m.

If a proposed theorem fails, output counterexamples and revise the theorem.

============================================================
COMBINATION RULES
============================================================

A full proof can be assembled by any successful route:

Route A:
    shifted-product character sums
    -> short-box energy
    -> Möbius incidence
    -> final-core occupancy
    -> rank-two branch
    -> sum A(n)<<X(log X)^C.

Route B:
    rational exponential sums
    -> large-volume branch
    plus short-box energy/near-injectivity
    -> final-core occupancy.

Route C:
    near-injectivity
    -> structured Hooley-Delta via Cauchy-Schwarz
    -> rank-two branch.

Route D:
    geometric divisor-window rigidity
    -> final-core occupancy directly.

Route E:
    low-Ω sieve
    plus explicit Diophantine occupancy
    -> final-core occupancy.

Always combine partial theorems into the strongest current conditional theorem.

============================================================
FINAL OUTPUT
============================================================

Return:

1. What was PROVED.
2. What was DISPROVED/FALSIFIED.
3. What is CONDITIONAL.
4. What computations found.
5. Which target currently appears strongest.
6. The sharpest remaining theorem.
7. Whether the full project is resolved.
8. If not resolved, give the next theorem in the chain and why it is the true obstruction.

Do not overclaim. If the final theorem is not proved, state exactly what remains.