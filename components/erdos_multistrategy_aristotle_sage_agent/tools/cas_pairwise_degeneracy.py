#!/usr/bin/env python3
"""Standalone CAS helper for the current pairwise degeneracy frontier.

It generates SageMath and Magma scripts for checking the off-identity product-fiber
rational functions, and always runs a lightweight SymPy fallback for the F1 pairwise
resultant/discriminant facts.

Usage:
    python tools/cas_pairwise_degeneracy.py --out runs/cas_check

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


class CASDegeneracyClient:
    def __init__(self, out_dir: str, timeout: int = 600):
        self.out_dir = Path(out_dir)
        self.timeout = timeout

    def _cmd(self, env_name: str, default_binary: str) -> str:
        explicit = os.environ.get(env_name, "")
        if explicit:
            return explicit
        return shutil.which(default_binary) or ""

    def write_sage_script(self, task_id: str) -> Path:
        task_dir = self.out_dir / "cas" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        script = task_dir / "pairwise_degeneracy.sage"
        script.write_text("""
print("Sage pairwise degeneracy analysis")
P.<r,t,u,z,y> = PolynomialRing(QQ, 5, order='degrevlex')
K = FractionField(P)
rK,tK,uK,zK,yK = map(K, [r,t,u,z,y])
alpha = rK - 1 + tK - uK

def Delta(A,B):
    return 4*A^2 + 4*A*B + 24*A + B^2 - 60*B + 36

A1z = zK*(rK+tK-uK) - 12*tK
B1z = zK
F1z = Delta(A1z, B1z)
A1y = yK*(rK+tK-uK) - 12*tK
B1y = yK
F1y = Delta(A1y, B1y)
print("F1z factor:", factor(P(F1z)))
print("disc_r(F1z):", factor(P(F1z).discriminant(r)))
print("resultant_r(F1z,F1y):", factor(P(F1z).resultant(P(F1y), r)))

denz = zK*alpha - 12*(tK-uK)
B2z = 12*(zK*(rK+tK)-12*tK)/denz
A2z = 12*(zK*(rK*(rK+tK-uK)+tK)-12*rK*tK)/denz
F2z = Delta(A2z, B2z)
print("F2z numerator factor:", factor(F2z.numerator()))
print("F2z denominator factor:", factor(F2z.denominator()))
print("deg numerator F2z:", P(F2z.numerator()).total_degree())
try:
    print("disc_r numerator F2z:", factor(P(F2z.numerator()).discriminant(r)))
except Exception as e:
    print("disc_r numerator F2z failed:", repr(e))
""".strip()+"\n", encoding="utf-8")
        return script

    def write_magma_script(self, task_id: str) -> Path:
        task_dir = self.out_dir / "cas" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        script = task_dir / "pairwise_degeneracy.magma"
        script.write_text("""
Q := Rationals();
P<r,t,u,z,y> := PolynomialRing(Q, 5);
K := FieldOfFractions(P);
rK := K!r; tK := K!t; uK := K!u; zK := K!z; yK := K!y;
alpha := rK - 1 + tK - uK;
Delta := function(A,B)
    return 4*A^2 + 4*A*B + 24*A + B^2 - 60*B + 36;
end function;
A1z := zK*(rK+tK-uK) - 12*tK;
B1z := zK;
F1z := Delta(A1z,B1z);
A1y := yK*(rK+tK-uK) - 12*tK;
B1y := yK;
F1y := Delta(A1y,B1y);
"F1z factor"; Factorization(P!F1z);
"disc_r(F1z)"; Factorization(Discriminant(P!F1z, r));
"resultant_r(F1z,F1y)"; Factorization(Resultant(P!F1z, P!F1y, r));
denz := zK*alpha - 12*(tK-uK);
B2z := 12*(zK*(rK+tK)-12*tK)/denz;
A2z := 12*(zK*(rK*(rK+tK-uK)+tK)-12*rK*tK)/denz;
F2z := Delta(A2z,B2z);
"F2z numerator factor"; Factorization(Numerator(F2z));
"F2z denominator factor"; Factorization(Denominator(F2z));
""".strip()+"\n", encoding="utf-8")
        return script

    def sympy_fallback(self) -> str:
        r,t,u,z,y = sp.symbols("r t u z y")
        Lz = z*r + (z-12)*t - z*u
        Ly = y*r + (y-12)*t - y*u
        F1z = sp.expand(4*Lz**2 + 4*(z+6)*Lz + z**2 - 60*z + 36)
        F1y = sp.expand(4*Ly**2 + 4*(y+6)*Ly + y**2 - 60*y + 36)
        disc_r = sp.factor(sp.discriminant(F1z, r))
        res_r = sp.factor(sp.resultant(F1z, F1y, r))
        return "\n".join([
            "# SymPy fallback pairwise degeneracy facts",
            f"F1z total degree: {sp.Poly(F1z, r,t,u,z).total_degree()}",
            f"disc_r(F1z) = {disc_r}",
            f"resultant_r(F1z,F1y) = {res_r}",
            "Interpretation: resultant contains the diagonal factor (y-z)^2; remaining factors describe exceptional loci.",
        ])

    def run(self, task_id: str = "pairwise") -> dict[str, Any]:
        result: dict[str, Any] = {"task_id": task_id}
        sage_script = self.write_sage_script(task_id)
        magma_script = self.write_magma_script(task_id)
        result["sage_script"] = str(sage_script)
        result["magma_script"] = str(magma_script)

        sage = self._cmd("SAGE_CMD", "sage")
        if sage:
            proc = subprocess.run([sage, str(sage_script)], capture_output=True, text=True, timeout=self.timeout)
            result["sage"] = {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
        else:
            result["sage"] = {"ok": False, "error": "SageMath not found. Set SAGE_CMD or install sage."}

        magma = self._cmd("MAGMA_CMD", "magma")
        if magma:
            proc = subprocess.run([magma, str(magma_script)], capture_output=True, text=True, timeout=self.timeout)
            result["magma"] = {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
        else:
            result["magma"] = {"ok": False, "error": "Magma not found. Set MAGMA_CMD if available."}

        result["sympy_fallback"] = self.sympy_fallback()
        return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/cas_pairwise")
    ap.add_argument("--task-id", default="pairwise")
    args = ap.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    result = CASDegeneracyClient(args.out).run(args.task_id)
    out = Path(args.out) / "cas_result.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(result["sympy_fallback"])
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
