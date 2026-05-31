# CAS degeneracy report

## SymPy fallback

```text
# SymPy pairwise degeneracy fallback
F1z = 4*r**2*z**2 + 8*r*t*z**2 - 96*r*t*z - 8*r*w*z**2 + 4*r*z**2 + 24*r*z + 4*t**2*z**2 - 96*t**2*z + 576*t**2 - 8*t*w*z**2 + 96*t*w*z + 4*t*z**2 - 24*t*z - 288*t + 4*w**2*z**2 - 4*w*z**2 - 24*w*z + z**2 - 60*z + 36
disc_r(F1z) = 1152*z**3
resultant_r(F1z,F1y) = 20736*(y - z)**2*(256*t**4*y**2 - 512*t**4*y*z + 256*t**4*z**2 - 256*t**3*y**2 + 512*t**3*y*z - 256*t**3*z**2 - 64*t**2*y**2*z + 96*t**2*y**2 - 64*t**2*y*z**2 - 192*t**2*y*z + 96*t**2*z**2 + 32*t*y**2*z - 16*t*y**2 + 32*t*y*z**2 + 32*t*y*z - 16*t*z**2 + 4*y**2*z**2 - 4*y**2*z + y**2 - 4*y*z**2 - 2*y*z + z**2)
Expected: diagonal factor (y-z)^2 and an exceptional polynomial after removal.
F2 numerator total degree: 6
F2 denominator: (r*z + t*z - 12*t - w*z + 12*w - z)**2
STATUS: F1 verified; F2 constructed for Sage/Magma factorization.
```

## Sage

```json
{
  "ok": false,
  "backend": "sage",
  "error": "No SAGE_CMD and `sage` not found"
}
```

## Magma

```json
{
  "ok": false,
  "backend": "magma",
  "error": "No MAGMA_CMD and `magma` not found"
}
```
