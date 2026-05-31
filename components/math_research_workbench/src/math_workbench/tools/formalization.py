from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from math_workbench.config import load_app_config

LEAN_STARTER = r'''
import Mathlib

namespace MathWorkbench

theorem product_formula_entry11
    (A1 A2 B1 B2 : ℤ) :
    (-B1) * (-B2) + (12 - B1) * A2 = A2 * (12 - B1) + B1 * B2 := by
  ring

theorem product_formula_entry12
    (A1 A2 B1 B2 : ℤ) :
    (-B1) * (12 - B2) + (12 - B1) * B2 = 12 * (B2 - B1) := by
  ring

theorem product_formula_entry21
    (A1 A2 B1 B2 : ℤ) :
    A1 * (-B2) + B1 * A2 = B1 * A2 - A1 * B2 := by
  ring

theorem product_formula_entry22
    (A1 A2 B1 B2 : ℤ) :
    A1 * (12 - B2) + B1 * B2 = A1 * (12 - B2) + B1 * B2 := by
  ring

theorem shifted_product_hyperbola_identity
    (alpha B1 B2 r t u : ℤ) :
    (alpha*B1 - 12*(t-u))*(alpha*B2 - 12*(r+t))
      - 144*((t-u)*(r+t)-alpha*t)
    = alpha*(alpha*B1*B2 - 12*B1*(r+t) - 12*B2*(t-u) + 144*t) := by
  ring

end MathWorkbench
'''


def run_local_lean(out_dir: str, lean_code: str = LEAN_STARTER) -> dict[str, Any]:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    lean_path = p / "MathWorkbench.lean"
    lean_path.write_text(lean_code, encoding="utf-8")
    cfg = load_app_config()
    lean_cmd = cfg.lean_cmd() or shutil.which("lean")
    if not lean_cmd:
        return {"ok": False, "backend": "LEAN_LOCAL", "error": "Lean not configured", "lean_path": str(lean_path)}
    cmd = lean_cmd.split() + [str(lean_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return {"ok": proc.returncode == 0, "backend": "LEAN_LOCAL", "cmd": cmd, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "lean_path": str(lean_path)}


def run_aristotle_cli(out_dir: str, lean_code: str = LEAN_STARTER, prompt: str = "Fill all sorries and verify this Lean project.") -> dict[str, Any]:
    cfg = load_app_config()
    cli = cfg.aristotle_cli() or shutil.which("aristotle")
    api_key = cfg.aristotle_api_key()
    p = Path(out_dir) / "aristotle_project"
    p.mkdir(parents=True, exist_ok=True)
    (p / "lakefile.toml").write_text('''name = "math_workbench_formal"\nversion = "0.1.0"\ndefaultTargets = ["MathWorkbench"]\n\n[[lean_lib]]\nname = "MathWorkbench"\n\n[[require]]\nname = "mathlib"\nscope = "leanprover-community"\n''', encoding="utf-8")
    (p / "lean-toolchain").write_text("leanprover/lean4:stable\n", encoding="utf-8")
    (p / "MathWorkbench.lean").write_text(lean_code, encoding="utf-8")
    if not cli:
        return {"ok": False, "backend": "ARISTOTLE_CLI", "error": "aristotle CLI not found", "project_dir": str(p)}
    if not api_key:
        return {"ok": False, "backend": "ARISTOTLE_CLI", "error": "ARISTOTLE_API_KEY not set", "project_dir": str(p)}
    cmd = [cli, "submit", prompt, "--project-dir", str(p), "--wait"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    return {"ok": proc.returncode == 0, "backend": "ARISTOTLE_CLI", "cmd": cmd, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "project_dir": str(p)}
