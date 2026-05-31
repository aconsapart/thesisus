from __future__ import annotations
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from theorem_codex.db import *  # noqa


def seed(db: str, prompt_path: str | None = None):
    init_db(db)
    con = connect(db)
    prompt = Path(prompt_path).read_text(encoding='utf-8') if prompt_path and Path(prompt_path).exists() else ''

    main = upsert_theorem(con, 'final_average_bound', 'Final average bound for A(n)', '''Prove

```math
\\sum_{n\\le X} A(n) \\ll X(\\log X)^C
```

where `K(n)=3n+12-2σ(n)`, `s(n)=σ(n)-n`, and `S(n)<=A(n)` for the primitive semiprime-side count.''', 'FAILED/OPEN', kind='THEOREM', frontier_rank=99, is_frontier=True, importance=5)

    occ = upsert_theorem(con, 'final_core_occupancy', 'Final-core occupancy theorem', '''In the final rank-two core, `K(mpq)=Hp-J`. If `K(mpq)=de`, `g=(H,d)`, `H=gH_0`, `d=ga`, `J=gJ_0`, then

```math
a\\mid H_0p-J_0.
```

Control this occupancy to close the rank-two branch.''', 'FAILED/OPEN', kind='FRONTIER', frontier_rank=50, is_frontier=True, parent_slug='final_average_bound', importance=5)

    energy = upsert_theorem(con, 'short_box_mobius_random_energy', 'Short-box random energy for trace-zero Möbius involutions', '''For `T_{P,Q}={T_{p,q}:p~P,q~Q}`, prove

```math
E(T_{P,Q}) \\ll (|T|^2+|T|^4/\\ell^3)(\\log X)^C.
```

The transformations are represented by `M_{p,q}=[[-B,12-B],[A,B]]`, with `A=2(q+1)-p(q-2)`, `B=2(p+1)(q+1)`.''', 'FAILED/OPEN', kind='FRONTIER', frontier_rank=20, is_frontier=True, parent_slug='final_core_occupancy', importance=5)

    avg = upsert_theorem(con, 'averaged_product_fiber_large_sieve', 'Averaged product-fiber character large sieve', '''Prove

```math
\\sum_R |\\sum_z w(z)\\chi(F_R(z))|^2 \\ll \\text{random-size energy bound}.
```

This replaces the too-strong individual very-short character-sum target and should imply off-identity Möbius energy.''', 'FAILED/OPEN', kind='FRONTIER', frontier_rank=0, is_frontier=True, parent_slug='short_box_mobius_random_energy', importance=5)

    twodisc = upsert_theorem(con, 'two_discriminant_product_fiber_large_sieve', 'Two-discriminant product-fiber character large sieve', '''Handle both square-discriminant conditions `F_1` and `F_2` arising from the off-identity product-fiber parameterization. Known: `F_1` pairwise large-sieve estimate is proved in the main chart. Open: `F_2` and mixed `F_1F_2`.''', 'FAILED/OPEN', kind='FRONTIER', frontier_rank=1, is_frontier=True, parent_slug='averaged_product_fiber_large_sieve', importance=5)

    shifted = upsert_theorem(con, 'very_short_shifted_product_character_sum', 'Very-short shifted-product character-sum theorem', '''For non-square rational quadratic functions `F` from off-identity product fibers, prove an averaged or lower-size-qualified estimate of

```math
\\sum_{p\\sim P,q\\sim Q} \\chi(F(2(p+1)(q+1))) \\ll PQ(\\log X)^{-A}
```

in the very-short range `PQ<=ell polylog(X)`, after removing explicit degeneracies.''', 'FAILED/OPEN', kind='FRONTIER', frontier_rank=2, is_frontier=True, parent_slug='averaged_product_fiber_large_sieve', importance=5)

    prod = upsert_theorem(con, 'product_formula_M1M2', 'Product formula for M1M2', '''For `M_i=[[-B_i,12-B_i],[A_i,B_i]]`,

```math
M_1M_2=\\begin{pmatrix}A_2(12-B_1)+B_1B_2&12(B_2-B_1)\\\\B_1A_2-A_1B_2&A_1(12-B_2)+B_1B_2\\end{pmatrix}.
```''', 'PROVED', kind='LEMMA', importance=4)
    disc = upsert_theorem(con, 'discriminant_recovery_identity', 'Discriminant identity for recovering p,q from A,B', '''Given `A=-pq+2p+2q+2` and `B=2(p+1)(q+1)`, the cleared discriminant is

```math
36\\Delta=4A^2+4AB+24A+B^2-60B+36.
```''', 'PROVED', kind='LEMMA', importance=4)
    f1 = upsert_theorem(con, 'F1_pairwise_large_sieve', 'Pairwise large-sieve estimate for first discriminant F1', '''In the affine chart `s=1`, `F_1(r,t,u;z)` depends only on `L_z=zr+(z-12)t-zu`. For `z!=z'`, the pairwise character correlation over `R` is `O(ell^2)` after excluding explicit exceptional loci.''', 'PROVED', kind='LEMMA', parent_slug='averaged_product_fiber_large_sieve', importance=5)

    add_dependency(con, 'final_average_bound', 'final_core_occupancy', 'DEPENDS_ON')
    add_dependency(con, 'final_core_occupancy', 'short_box_mobius_random_energy', 'DEPENDS_ON')
    add_dependency(con, 'short_box_mobius_random_energy', 'averaged_product_fiber_large_sieve', 'DEPENDS_ON')
    add_dependency(con, 'averaged_product_fiber_large_sieve', 'two_discriminant_product_fiber_large_sieve', 'DEPENDS_ON')
    add_dependency(con, 'averaged_product_fiber_large_sieve', 'F1_pairwise_large_sieve', 'SUPPORTED_BY')
    add_dependency(con, 'two_discriminant_product_fiber_large_sieve', 'product_formula_M1M2', 'DEPENDS_ON')
    add_dependency(con, 'two_discriminant_product_fiber_large_sieve', 'discriminant_recovery_identity', 'DEPENDS_ON')

    strategies = [
        ('avg_product_fiber','Averaged product-fiber large sieve','Attack the second moment over product fibers rather than individual tiny-box sums.',1,'ACTIVE',10),
        ('two_discriminant','Two-discriminant correlation','Handle F2 and mixed F1F2 correlations after F1 is controlled.',2,'ACTIVE',9),
        ('shifted_product_chars','Very-short shifted-product character sums','Character sums over F(2(p+1)(q+1)); works when PQ >> ell polylog.',3,'ACTIVE',8),
        ('mobius_energy','Short-box Möbius energy','Prove random energy for trace-zero involution family.',4,'ACTIVE',7),
        ('near_injectivity','Near-injectivity / collision energy','Bypass inverse-distribution by proving K(mpq) almost injective.',5,'ACTIVE',6),
        ('integer_lifting','Integer lifting','Falsified: modular congruence usually does not lift to integer equality.',98,'FALSIFIED',-10),
        ('interlacing','Prime interlacing rules','Falsified by counterexamples.',99,'FALSIFIED',-9),
    ]
    for row in strategies:
        upsert_strategy(con, slug=row[0], name=row[1], description_md=row[2], rank=row[3], status=row[4], score=row[5])

    add_claim(con, 'short_box_mobius_random_energy', 'PROVED', 'The matrices `M_{p,q}` have trace zero and are projective involutions.', 'Use Cayley-Hamilton for a trace-zero `2x2` matrix.')
    add_claim(con, 'short_box_mobius_random_energy', 'PROVED', 'Projective equality `T_{p,q}=T_{p\',q\'}` implies `{p,q}={p\',q\'}` modulo `ell`, assuming `ell∤6`.', 'The identity `C=B-12` forces the projective scalar to be 1.')
    add_claim(con, 'very_short_shifted_product_character_sum', 'FAILED/OPEN', 'Uniform individual very-short estimates are too strong without lower-size or averaging hypotheses.', 'Tiny boxes can contain O(1) prime pairs and no cancellation.')
    add_claim(con, 'F1_pairwise_large_sieve', 'PROVED', 'The first discriminant has a rank-one collapse and pairwise large-sieve estimate.', '`F_1` depends only on one linear form `L_z`, so off-diagonal correlations factor into one-variable quadratic-character sums.')
    add_claim(con, 'two_discriminant_product_fiber_large_sieve', 'FAILED/OPEN', 'The second discriminant `F_2` and mixed `F_1F_2` correlations remain open.', 'These are the next algebraic bottleneck for the averaged product-fiber theorem.')

    add_falsification(con, theorem_slug='very_short_shifted_product_character_sum', strategy_slug='shifted_product_chars', obstruction_md='The individual theorem is false in arbitrary tiny boxes.', counterexample_md='A box with a single prime pair may have character sum of magnitude 1.', severity='HIGH')
    add_falsification(con, theorem_slug='final_core_occupancy', strategy_slug='integer_lifting', obstruction_md='Integer lifting was falsified.', counterexample_md='The congruence value is typically many multiples of ell, not zero as an integer.', severity='HIGH')

    add_computation(con, theorem_slug='two_discriminant_product_fiber_large_sieve', run_id='seed', name='Current symbolic status', status='COMPUTATIONAL', summary={'F1_pairwise':'proved', 'F2_pairwise':'open', 'mixed_F1F2':'open'})

    for tag in ['frontier','character-sum','mobius','energy','formalizable','falsified']:
        add_tag(con, tag)
    for slug, tags in {
        'averaged_product_fiber_large_sieve':['frontier','character-sum','energy'],
        'two_discriminant_product_fiber_large_sieve':['frontier','character-sum'],
        'short_box_mobius_random_energy':['frontier','mobius','energy'],
        'product_formula_M1M2':['formalizable'],
        'discriminant_recovery_identity':['formalizable'],
        'very_short_shifted_product_character_sum':['frontier','character-sum'],
    }.items():
        for tag in tags: link_tag(con, slug, tag)

    if prompt:
        aid = add_attempt(con, theorem_slug='two_discriminant_product_fiber_large_sieve', strategy_slug='avg_product_fiber', run_id='seed', title='Uploaded current frontier prompt', prompt_md=prompt[:8000], result_md='Seeded prompt into theorem codex.', status='COMPUTATIONAL')
        add_artifact(con, path=prompt_path, kind='prompt', theorem_slug='two_discriminant_product_fiber_large_sieve', attempt_id=aid, description_md='Uploaded current frontier prompt.')

    con.close()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='proof_codex.sqlite')
    parser.add_argument('--prompt', default='data/current_frontier_prompt.md')
    args = parser.parse_args()
    seed(args.db, args.prompt)
    print(f'Seeded {args.db}')
