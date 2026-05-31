# Pairwise degeneracy CAS node

The new CAS node targets the algebraic bottleneck

```text
F_R(z) F_R(z') ∈ F_ell(R)^2 ?
```

for the averaged product-fiber second moment.

## What is currently automated

In the main affine chart `s=1`, the first discriminant has rank-one form

```text
F1(z)=4L_z^2+4(z+6)L_z+z^2-60z+36,
L_z=z r+(z-12)t-z w.
```

The node verifies with SymPy:

```text
disc_r F1(z) = 1152 z^3,
resultant_r(F1(z), F1(y)) = 20736 (y-z)^2 E(t,y,z).
```

This proves/computationally confirms that the `F1` pairwise degeneracy is diagonal plus an explicit exceptional factor.

## Optional Sage/Magma

The node writes:

```text
pairwise_degeneracy.sage
pairwise_degeneracy.magma
```

and runs them if `SAGE_CMD` or `MAGMA_CMD` is configured. Otherwise, it records the scripts for external execution.

## Remaining algebraic bottleneck

The current unresolved CAS target is the full two-discriminant theorem:

```text
F2_R(z)F2_R(z') and F1_R(z)F2_R(z') are non-square outside diagonal and explicit exceptional loci.
```
