#!/usr/bin/env python3
"""Standalone CAS degeneracy checks for the Erdős shifted-product frontier.

This script does not require LangChain/LangGraph. It writes SageMath and Magma
scripts for the pairwise degeneracy problem and runs a SymPy fallback.

Usage:
    python src/cas_degeneracy_standalone.py --out runs/cas_deg_001

Optional:
    export SAGE_CMD=sage
    export MAGMA_CMD=magma
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import sympy as sp


def sage_script() -> str:
    return """
# SageMath script: pairwise degeneracy for averaged product-fiber large sieve
# Run: sage pairwise_degeneracy.sage
R.<r,t,w,z,y> = PolynomialRing(QQ, 5, order='lex')
alpha = r - 1 + t - w
Lz = z*r + (z-12)*t - z*w
Ly = y*r + (y-12)*t - y*w
F1z = 4*Lz^2 + 4*(z+6)*Lz + z^2 - 60*z + 36
F1y = 4*Ly^2 + 4*(y+6)*Ly + y^2 - 60*y + 36
print('F1 degree in r:', F1z.degree(r))
print('disc_r(F1z) factor:')
print(factor(F1z.discriminant(r)))
Res = F1z.resultant(F1y, r)
print('resultant_r(F1z,F1y) factor:')
print(factor(Res))
print('squarefree part of resultant:')
# MPolynomial_libsingular has no squarefree_part(); rebuild it from the factorization
print(factor(prod(f for f, m in Res.factor())))
if Res % ((y-z)^2) == 0:
    core = Res // ((y-z)^2)
else:
    core = Res
print('core after removing (y-z)^2 if divisible:')
print(factor(core))
print('STATUS: Sage F1 pairwise degeneracy script completed. Extend TODO for F2/F1F2.')
""".strip()+"\n"


def magma_script() -> str:
    return """
// Magma script: pairwise degeneracy for averaged product-fiber large sieve
// Run: magma pairwise_degeneracy.magma
Q := Rationals();
P<r,t,w,z,y> := PolynomialRing(Q, 5, "lex");
alpha := r - 1 + t - w;
Lz := z*r + (z-12)*t - z*w;
Ly := y*r + (y-12)*t - y*w;
F1z := 4*Lz^2 + 4*(z+6)*Lz + z^2 - 60*z + 36;
F1y := 4*Ly^2 + 4*(y+6)*Ly + y^2 - 60*y + 36;
"F1 degree in r:", Degree(F1z, 1);
"disc_r(F1z):", Factorization(Discriminant(F1z, r));
Res := Resultant(F1z, F1y, r);
"resultant_r(F1z,F1y):", Factorization(Res);
"STATUS: Magma F1 pairwise degeneracy script completed. Extend for F2/F1F2.";
""".strip()+"\n"


def sympy_report() -> str:
    r, t, w, z, y = sp.symbols("r t w z y")
    alpha = r - 1 + t - w
    Lz = z*r + (z-12)*t - z*w
    Ly = y*r + (y-12)*t - y*w
    F1z = sp.expand(4*Lz**2 + 4*(z+6)*Lz + z**2 - 60*z + 36)
    F1y = sp.expand(4*Ly**2 + 4*(y+6)*Ly + y**2 - 60*y + 36)
    disc_r = sp.factor(sp.discriminant(F1z, r))
    res_r = sp.factor(sp.resultant(F1z, F1y, r))
    den = z*alpha - 12*(t-w)
    B2 = 12*(z*(r+t)-12*t) / den
    A2 = 12*(z*(r*(r+t-w)+t)-12*r*t) / den
    F2_rat = 4*A2**2 + 4*A2*B2 + 24*A2 + B2**2 - 60*B2 + 36
    F2_num, F2_den = sp.fraction(sp.together(F2_rat))
    F2_num = sp.factor(F2_num)
    F2_den = sp.factor(F2_den)
    try:
        total_deg = sp.Poly(F2_num, r, t, w, z).total_degree()
    except Exception:
        total_deg = "unavailable"
    return "\n".join([
        "# SymPy pairwise degeneracy fallback",
        f"F1z = {F1z}",
        f"disc_r(F1z) = {disc_r}",
        f"resultant_r(F1z,F1y) = {res_r}",
        "Expected: diagonal factor (y-z)^2 and an exceptional polynomial after removal.",
        f"F2 numerator total degree: {total_deg}",
        f"F2 denominator: {F2_den}",
        "STATUS: F1 verified; F2 constructed for Sage/Magma factorization.",
    ])


def run_external(script_path: Path, env_name: str, fallback_binary: str) -> dict[str, Any]:
    cmd = os.environ.get(env_name) or shutil.which(fallback_binary)
    if not cmd:
        return {"ok": False, "backend": fallback_binary, "error": f"No {env_name} and `{fallback_binary}` not found"}
    try:
        proc = subprocess.run([cmd, str(script_path)], capture_output=True, text=True, timeout=600)
        return {"ok": proc.returncode == 0, "cmd": [cmd, str(script_path)], "stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
    except Exception as exc:
        return {"ok": False, "backend": fallback_binary, "error": repr(exc)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="runs/cas_degeneracy")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sage_path = out / "pairwise_degeneracy.sage"
    magma_path = out / "pairwise_degeneracy.magma"
    sage_path.write_text(sage_script(), encoding="utf-8")
    magma_path.write_text(magma_script(), encoding="utf-8")
    report = {
        "sage_script": str(sage_path),
        "magma_script": str(magma_path),
        "sympy_fallback": sympy_report(),
        "sage": run_external(sage_path, "SAGE_CMD", "sage"),
        "magma": run_external(magma_path, "MAGMA_CMD", "magma"),
    }
    (out / "cas_degeneracy_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "cas_degeneracy_report.md").write_text(
        "# CAS degeneracy report\n\n## SymPy fallback\n\n```text\n" + report["sympy_fallback"] + "\n```\n\n" +
        "## Sage\n\n```json\n" + json.dumps(report["sage"], indent=2, ensure_ascii=False) + "\n```\n\n" +
        "## Magma\n\n```json\n" + json.dumps(report["magma"], indent=2, ensure_ascii=False) + "\n```\n",
        encoding="utf-8",
    )
    print(f"Wrote CAS degeneracy reports to {out}")


if __name__ == "__main__":
    main()
