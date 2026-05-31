# Current Frontier

You are continuing the Erdős divisor-sum project.

Core setup:

    K(n)=3n+12-2σ(n),
    s(n)=σ(n)-n,

and

    A(n)=#{ d | K(n):
            d<K(n)/d,
            d+K(n)/d<=s(n)-11 }.

The primitive semiprime-side count satisfies:

    S(n)<=A(n).

All broad reductions have already been performed. Do not restart earlier branches unless needed for a consistency check.

Every claim must be labeled as one of:

    PROVED
    CONDITIONAL
    COMPUTATIONAL
    HEURISTIC
    FAILED/OPEN

Current exact frontier:

The obstruction is the very-short shifted-product branch from off-identity product energy of the trace-zero Möbius involution family

    M_{p,q} = [ -B   12-B ]
              [  A     B  ],

where

    A=2(q+1)-p(q-2),
    B=2(p+1)(q+1).

The strongest current target is an averaged product-fiber large-sieve / second-moment theorem, not a uniform tiny-box theorem for each individual F.
