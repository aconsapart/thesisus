from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import sympy as sp

from math_workbench.config import load_app_config


def symbolic_core_checks() -> str:
    A1, A2, B1, B2 = sp.symbols("A1 A2 B1 B2")
    M1 = sp.Matrix([[-B1, 12 - B1], [A1, B1]])
    M2 = sp.Matrix([[-B2, 12 - B2], [A2, B2]])
    prod = sp.expand(M1 * M2)
    expected = sp.Matrix([
        [A2 * (12 - B1) + B1 * B2, 12 * (B2 - B1)],
        [B1 * A2 - A1 * B2, A1 * (12 - B2) + B1 * B2],
    ])
    product_ok = sp.simplify(prod - expected) == sp.zeros(2, 2)

    A, B = sp.symbols("A B")
    s0 = (A + B / 2 - 3) / 3
    t0 = B / 2 - s0 - 1
    Delta = sp.expand(s0**2 - 4 * t0)
    cleared = sp.expand(36 * Delta)
    expected_delta = sp.expand(4 * A**2 + 4 * A * B + 24 * A + B**2 - 60 * B + 36)
    delta_ok = sp.simplify(cleared - expected_delta) == 0

    # Hyperbola completion check
    alpha, r, s, t, u = sp.symbols("alpha r s t u")
    expr = sp.expand((alpha * B1 - 12 * (t - u)) * (alpha * B2 - 12 * (r + t)) - 144 * ((t - u) * (r + t) - alpha * t))
    expected_expr = sp.expand(alpha * (alpha * B1 * B2 - 12 * B1 * (r + t) - 12 * B2 * (t - u) + 144 * t))
    hyperbola_ok = sp.simplify(expr - expected_expr) == 0

    return "\n".join([
        "# Symbolic core checks",
        f"Product formula OK: {product_ok}",
        f"Discriminant formula OK: {delta_ok}",
        f"Hyperbola completion OK: {hyperbola_ok}",
        "",
        "M1*M2 computed:", str(prod),
        "",
        "36Δ computed:", str(cleared),
    ])


def generate_sage_pairwise_script(out_dir: str) -> str:
    path = Path(out_dir) / "pairwise_degeneracy.sage"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(r'''
# SageMath pairwise degeneracy scaffold
# Goal: classify whether F_R(z)*F_R(y) is a square in the rational function field.

R.<r,t,u,z,y> = PolynomialRing(QQ, 5)
# Affine chart s=1. These are placeholders for the first-discriminant numerator N_z.
# The agent should replace/extend this with F2 and mixed products as formulas stabilize.
Lz = z*r + (z-12)*t - z*u
Nz = 4*Lz^2 + 4*(z+6)*Lz + z^2 - 60*z + 36
Ly = y*r + (y-12)*t - y*u
Ny = 4*Ly^2 + 4*(y+6)*Ly + y^2 - 60*y + 36
print("disc_r Nz =", Nz.discriminant(r).factor())
print("resultant_r Nz Ny =", Nz.resultant(Ny, r).factor())
print("squarefree-ish factors Nz*Ny =")
print((Nz*Ny).factor())
'''.strip() + "\n", encoding="utf-8")
    return str(path)


def generate_magma_pairwise_script(out_dir: str) -> str:
    path = Path(out_dir) / "pairwise_degeneracy.magma"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(r'''
Q := Rationals();
P<r,t,u,z,y> := PolynomialRing(Q, 5);
Lz := z*r + (z-12)*t - z*u;
Nz := 4*Lz^2 + 4*(z+6)*Lz + z^2 - 60*z + 36;
Ly := y*r + (y-12)*t - y*u;
Ny := 4*Ly^2 + 4*(y+6)*Ly + y^2 - 60*y + 36;
"disc_r Nz"; Factorization(Discriminant(Nz, r));
"resultant_r Nz Ny"; Factorization(Resultant(Nz, Ny, r));
'''.strip() + "\n", encoding="utf-8")
    return str(path)


def run_optional_command(cmd: list[str], timeout: int = 300) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"ok": proc.returncode == 0, "cmd": cmd, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as e:
        return {"ok": False, "cmd": cmd, "error": repr(e)}


def cas_pairwise_degeneracy(out_dir: str) -> dict[str, Any]:
    report: dict[str, Any] = {"sympy_core": symbolic_core_checks()}
    sage_script = generate_sage_pairwise_script(out_dir)
    magma_script = generate_magma_pairwise_script(out_dir)
    report["sage_script"] = sage_script
    report["magma_script"] = magma_script

    cfg = load_app_config()
    sage = cfg.tools.sage_cmd or os.environ.get("SAGE_CMD") or shutil.which("sage")
    magma = cfg.tools.magma_cmd or os.environ.get("MAGMA_CMD") or shutil.which("magma")
    if sage:
        report["sage_result"] = run_optional_command([sage, sage_script])
    else:
        report["sage_result"] = {"ok": False, "error": "Sage not configured"}
    if magma:
        report["magma_result"] = run_optional_command([magma, magma_script])
    else:
        report["magma_result"] = {"ok": False, "error": "Magma not configured"}

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "cas_pairwise_degeneracy.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = ["# CAS pairwise degeneracy report", "", "## SymPy core", "", "```", report["sympy_core"], "```"]
    for key in ("sage_result", "magma_result"):
        md += ["", f"## {key}", "", "```json", json.dumps(report[key], indent=2)[:8000], "```"]
    (Path(out_dir) / "cas_pairwise_degeneracy.md").write_text("\n".join(md), encoding="utf-8")
    return report
