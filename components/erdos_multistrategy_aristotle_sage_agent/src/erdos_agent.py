#!/usr/bin/env python3
"""
Multi-strategy LangGraph/LangChain proof-search scaffold for the Erdős divisor-sum project,
with optional Aristotle/Lean formalization support.

Run:
    export OPENAI_API_KEY="..."
    export MODEL_NAME="gpt-4.1"
    python src/erdos_agent.py --iterations 4 --parallel-strategies 3 --out runs/run_001

Optional formalization environment:
    export LEAN_CMD="lake env lean"          # or "lean"
    export ARISTOTLE_API_URL="..."           # if available
    export ARISTOTLE_API_KEY="..."           # if available
    export ARISTOTLE_CLI="..."               # command accepting JSON on stdin

Optional CAS environment:
    export SAGE_CMD="sage"                    # default auto-detected if installed
    export MAGMA_CMD="magma"                  # default auto-detected if installed

Design goals:
- multiple strategies in parallel;
- falsification-first;
- symbolic checks;
- formalization lane for small candidate lemmas;
- conservative status labels.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import shutil
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict

import requests
import sympy as sp
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

Status = Literal["PROVED", "CONDITIONAL", "COMPUTATIONAL", "HEURISTIC", "FAILED/OPEN"]


class Finding(TypedDict):
    status: Status
    strategy_id: str
    title: str
    content: str


class StrategyState(TypedDict):
    id: str
    title: str
    description: str
    priority: int
    score: float
    status: str
    last_result: str
    falsifications: list[str]
    proved: list[str]
    open: list[str]


class FormalTask(TypedDict):
    id: str
    source_strategy: str
    informal_statement: str
    informal_proof: str
    lean_statement: str
    lean_code: str
    backend: str
    status: str
    output: str


class ResearchState(TypedDict):
    run_id: str
    out_dir: str
    iteration: int
    max_iterations: int
    parallel_strategies: int
    project_setup: str
    current_frontier: str
    strategies: list[StrategyState]
    active_strategy_ids: list[str]
    proof_ledger: list[Finding]
    computational_findings: list[Finding]
    formal_tasks: list[FormalTask]
    failed_strategies: list[str]
    sharpest_remaining_theorem: str
    last_strategy_batch_result: str
    last_symbolic_result: str
    last_cas_result: str
    last_formalization_result: str
    last_synthesis: str
    resolved: bool


SYSTEM_PROMPT = """You are a mathematical proof-search assistant.

Rules:
1. Do not overclaim.
2. Every mathematical claim must be labeled exactly one of:
   PROVED, CONDITIONAL, COMPUTATIONAL, HEURISTIC, FAILED/OPEN.
3. Falsify before proving.
4. If a theorem fails, sharpen it and state the sharper theorem.
5. Do not restart old branches unless needed for a consistency check.
6. Prefer exact algebraic reductions, symbolic verification, and explicit counterexamples.
7. When proposing formalization, focus on small algebraic lemmas first.
8. If unresolved, end with the exact remaining theorem.
"""

PROJECT_SETUP = r"""
We are continuing the Erdős divisor-sum project.

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
"""

CURRENT_FRONTIER = r"""
Current frontier:

The obstruction is the very-short shifted-product branch from the off-identity product energy
of the trace-zero Möbius involution family

    M_{p,q} = [ -B   12-B ]
              [  A     B  ],

where

    A=2(q+1)-p(q-2),
    B=2(p+1)(q+1).

The previous individual target

    sum_{p~P,q~Q} χ(F(2(p+1)(q+1))) << PQ(log X)^(-A)

is too strong in arbitrary tiny boxes.

The better target is the averaged product-fiber large-sieve / second-moment estimate:

    sum_R | sum_z w(z) χ(F_R(z)) |^2 << random-size energy bound.

Known useful facts:

    PROVED: tr(M_{p,q})=0.
    PROVED: M_{p,q}^2=(B^2-AC)I.
    PROVED: nondegenerate transformations are projective involutions.
    PROVED: projective equality T_{p,q}=T_{p',q'} implies {p,q}={p',q'} mod ell, assuming ell∤6.
    PROVED: product formula for M1M2.
    PROVED: in the main s!=0, alpha!=0 branch, product fibers reduce to shifted-product hyperbola.
    PROVED: the first discriminant F1 has a rank-one collapse.
    OPEN: the full two-discriminant averaged product-fiber large-sieve theorem.
"""


def default_strategies() -> list[StrategyState]:
    raw = [
        (
            "cas_pairwise_degeneracy",
            "CAS pairwise degeneracy classification",
            "Use SageMath/Magma/SymPy to classify when F_R(z)F_R(z') is square and isolate exceptional loci.",
            -1,
        ),
        (
            "avg_product_fiber",
            "Averaged product-fiber large sieve",
            "Prove the second-moment estimate over R for F_R(z), replacing the overstrong individual tiny-box theorem.",
            0,
        ),
        (
            "two_discriminant",
            "Two-discriminant product-fiber theorem",
            "Handle F1, F2, and mixed F1F2 pairwise correlations; classify pairwise square degeneracies.",
            1,
        ),
        (
            "short_box_energy",
            "Short-box Möbius random energy",
            "Prove random-size off-identity product energy for trace-zero involutions T_{p,q}.",
            2,
        ),
        (
            "shifted_product_chars",
            "Very-short shifted-product character sums",
            "Attack sums chi(F(2(p+1)(q+1))) in PQ <= ell polylog with lower-size or averaged hypotheses.",
            3,
        ),
        (
            "rational_exp_sums",
            "Rational exponential sums / trace functions",
            "Use sums e_ell(h J/H) for large-volume or Type-II ranges.",
            4,
        ),
        (
            "inverse_discrepancy",
            "Structured modular inverse discrepancy",
            "Attack p ≡ J0 H0^{-1} mod ell directly through discrepancy/Kloosterman/dispersion.",
            5,
        ),
        (
            "near_injectivity",
            "Near-injectivity / collision energy",
            "Prove sum_N r(N)^2 << MPQ polylog to bypass inverse distribution.",
            6,
        ),
        (
            "divisor_window",
            "Geometric divisor-window rigidity",
            "Use a | H0 p - J0 and ga^2 < H0p-J0 < aH/logX with all final-core constraints.",
            7,
        ),
        (
            "low_omega",
            "Deficiency / low-Ω cleanup",
            "Use σ(m)/m < 3q/(2(q+1)) to reduce high-Ω residuals.",
            8,
        ),
    ]
    return [
        StrategyState(
            id=sid,
            title=title,
            description=desc,
            priority=priority,
            score=100.0 - 7.0 * priority,
            status="active",
            last_result="",
            falsifications=[],
            proved=[],
            open=[],
        )
        for sid, title, desc, priority in raw
    ]


def build_llm() -> ChatOpenAI:
    model = os.environ.get("MODEL_NAME", "gpt-4.1")
    return ChatOpenAI(model=model, temperature=0.15)


def write_artifact(state: ResearchState, name: str, content: str) -> None:
    out = Path(state["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def call_llm(user_prompt: str) -> str:
    llm = build_llm()
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
    response = llm.invoke(messages)
    return str(response.content)


# -----------------------------------------------------------------------------
# Formalization backends
# -----------------------------------------------------------------------------

@dataclasses.dataclass
class AristotleClient:
    """Pluggable Aristotle integration.

    Public Aristotle/Lean interfaces may change. This client supports:
      1. ARISTOTLE_CLI: command accepting JSON on stdin and returning JSON/text.
      2. ARISTOTLE_API_URL + optional ARISTOTLE_API_KEY: HTTP POST JSON.

    Adapt `payload` and result parsing to the endpoint you actually have.
    """

    api_url: str = os.environ.get("ARISTOTLE_API_URL", "")
    api_key: str = os.environ.get("ARISTOTLE_API_KEY", "")
    cli: str = os.environ.get("ARISTOTLE_CLI", "")
    timeout: int = 120

    def available(self) -> bool:
        return bool(self.api_url or self.cli)

    def prove(self, lean_code: str, informal_context: str = "") -> dict[str, Any]:
        payload = {
            "task": "prove_lean",
            "lean_code": lean_code,
            "informal_context": informal_context,
            "requirements": {
                "no_sorry": True,
                "no_unsound_axioms": True,
                "return_completed_lean": True,
            },
        }
        if self.cli:
            try:
                proc = subprocess.run(
                    self.cli,
                    input=json.dumps(payload),
                    text=True,
                    shell=True,
                    capture_output=True,
                    timeout=self.timeout,
                )
                return {
                    "backend": "aristotle_cli",
                    "ok": proc.returncode == 0,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "returncode": proc.returncode,
                }
            except Exception as exc:  # noqa: BLE001
                return {"backend": "aristotle_cli", "ok": False, "error": repr(exc)}

        if self.api_url:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            try:
                resp = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)
                text = resp.text
                try:
                    body: Any = resp.json()
                except Exception:  # noqa: BLE001
                    body = text
                return {
                    "backend": "aristotle_http",
                    "ok": resp.ok,
                    "status_code": resp.status_code,
                    "body": body,
                }
            except Exception as exc:  # noqa: BLE001
                return {"backend": "aristotle_http", "ok": False, "error": repr(exc)}

        return {"backend": "none", "ok": False, "error": "No Aristotle backend configured"}


@dataclasses.dataclass
class CASDegeneracyClient:
    """Optional SageMath/Magma integration for pairwise degeneracy analysis.

    Environment variables:
      SAGE_CMD="sage" or path to Sage executable
      MAGMA_CMD="magma" or path to Magma executable

    The generated scripts target the current algebraic bottleneck:
        F_R(z) F_R(z') square? in the off-identity product-fiber family.
    """

    out_dir: str
    timeout: int = 600

    def _cmd(self, env_name: str, default_binary: str) -> str:
        explicit = os.environ.get(env_name, "")
        if explicit:
            return explicit
        found = shutil.which(default_binary)
        return found or ""

    def sage_cmd(self) -> str:
        return self._cmd("SAGE_CMD", "sage")

    def magma_cmd(self) -> str:
        return self._cmd("MAGMA_CMD", "magma")

    def write_sage_script(self, task_id: str) -> Path:
        task_dir = Path(self.out_dir) / "cas" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        script = task_dir / "pairwise_degeneracy.sage"
        script.write_text("""
# SageMath script for the pairwise degeneracy bottleneck.
# It works in the affine chart s=1 and main branch alpha=r-1+t-u != 0.
# Goal: inspect F1_R(z), F2_R(z), pairwise products, discriminants and resultants.

print("Sage pairwise degeneracy analysis")
P.<r,t,u,z,y> = PolynomialRing(QQ, 5, order='degrevlex')
K = FractionField(P)
rK,tK,uK,zK,yK = map(K, [r,t,u,z,y])

alpha = rK - 1 + tK - uK

def Delta(A,B):
    return 4*A^2 + 4*A*B + 24*A + B^2 - 60*B + 36

# First product pair parameterized by B1=z.
A1z = zK*(rK+tK-uK) - 12*tK
B1z = zK
F1z = Delta(A1z, B1z)

A1y = yK*(rK+tK-uK) - 12*tK
B1y = yK
F1y = Delta(A1y, B1y)

print("F1z factor:", factor(P(F1z)))
print("disc_r(F1z):", factor(P(F1z).discriminant(r)))
print("resultant_r(F1z,F1y):", factor(P(F1z).resultant(P(F1y), r)))

# Second product pair: formulas from M1M2 ~ R in s=1 branch.
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
        task_dir = Path(self.out_dir) / "cas" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        script = task_dir / "pairwise_degeneracy.magma"
        script.write_text("""
// Magma script for pairwise degeneracy analysis in affine chart s=1.
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

    def run(self, task_id: str) -> dict[str, Any]:
        result: dict[str, Any] = {"backend": "cas_degeneracy", "task_id": task_id}
        sage_script = self.write_sage_script(task_id)
        magma_script = self.write_magma_script(task_id)
        result["sage_script"] = str(sage_script)
        result["magma_script"] = str(magma_script)

        sage = self.sage_cmd()
        if sage:
            try:
                proc = subprocess.run([sage, str(sage_script)], capture_output=True, text=True, timeout=self.timeout)
                result["sage"] = {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
            except Exception as exc:  # noqa: BLE001
                result["sage"] = {"ok": False, "error": repr(exc)}
        else:
            result["sage"] = {"ok": False, "error": "SageMath not found. Set SAGE_CMD or install sage."}

        magma = self.magma_cmd()
        if magma:
            try:
                proc = subprocess.run([magma, str(magma_script)], capture_output=True, text=True, timeout=self.timeout)
                result["magma"] = {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
            except Exception as exc:  # noqa: BLE001
                result["magma"] = {"ok": False, "error": repr(exc)}
        else:
            result["magma"] = {"ok": False, "error": "Magma not found. Set MAGMA_CMD if available."}

        try:
            result["sympy_fallback"] = self.sympy_fallback()
        except Exception as exc:  # noqa: BLE001
            result["sympy_fallback"] = f"SymPy fallback failed: {exc!r}"

        return result


def run_local_lean(lean_code: str, out_dir: str, task_id: str) -> dict[str, Any]:
    lean_cmd = os.environ.get("LEAN_CMD", "")
    if not lean_cmd:
        return {"backend": "local_lean", "ok": False, "error": "LEAN_CMD not configured"}

    path = Path(out_dir) / "formal" / f"{task_id}.lean"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(lean_code, encoding="utf-8")

    try:
        proc = subprocess.run(
            f"{lean_cmd} {path}",
            shell=True,
            text=True,
            capture_output=True,
            timeout=120,
        )
        return {
            "backend": "local_lean",
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
            "path": str(path),
        }
    except Exception as exc:  # noqa: BLE001
        return {"backend": "local_lean", "ok": False, "error": repr(exc), "path": str(path)}


# -----------------------------------------------------------------------------
# Graph nodes
# -----------------------------------------------------------------------------


def select_top_strategies(state: ResearchState) -> list[StrategyState]:
    active = [s for s in state["strategies"] if s["status"] not in {"falsified", "closed"}]
    active.sort(key=lambda s: (-float(s["score"]), int(s["priority"])))
    return active[: state["parallel_strategies"]]


def node_select_strategies(state: ResearchState) -> dict[str, Any]:
    selected = select_top_strategies(state)
    text = "# Selected strategies\n\n" + "\n".join(
        f"- {s['id']}: {s['title']} (score={s['score']:.2f})" for s in selected
    )
    write_artifact(state, f"iteration_{state['iteration']:02d}/selected_strategies.md", text)
    return {"active_strategy_ids": [s["id"] for s in selected]}


def strategy_prompt(state: ResearchState, strategy: StrategyState) -> str:
    return f"""
{state['project_setup']}

{state['current_frontier']}

Active strategy:
ID: {strategy['id']}
Title: {strategy['title']}
Description: {strategy['description']}

Previous result for this strategy:
{strategy['last_result'] or '(none)'}

Task:
1. FALSIFY FIRST: try counterexamples, scaling contradictions, degeneracies, concentration, tiny-box failure.
2. If not falsified, attempt a proof or a sharper reduction.
3. Include exact algebra and formulas where applicable.
4. Propose formalization candidates: small lemmas suitable for Lean/Aristotle.
5. Return sections exactly:
   - PROVED
   - CONDITIONAL
   - COMPUTATIONAL
   - HEURISTIC
   - FAILED/OPEN
   - FORMALIZATION_CANDIDATES
   - SHARPEST_REMAINING_THEOREM

Do not overclaim.
"""


def node_run_strategies(state: ResearchState) -> dict[str, Any]:
    by_id = {s["id"]: s for s in state["strategies"]}
    updated: list[StrategyState] = []
    batch_report_parts: list[str] = []
    ledger = list(state["proof_ledger"])
    failed = list(state["failed_strategies"])

    for sid in state["active_strategy_ids"]:
        strat = by_id[sid]
        result = call_llm(strategy_prompt(state, strat))
        write_artifact(state, f"iteration_{state['iteration']:02d}/strategy_{sid}.md", result)

        new_strat = dict(strat)
        new_strat["last_result"] = result

        # Conservative scoring heuristic.
        lower = result.lower()
        if "falsified" in lower or "counterexample" in lower or "too strong" in lower:
            new_strat["score"] = max(0.0, float(new_strat["score"]) - 20.0)
            new_strat["falsifications"].append(f"iteration {state['iteration']}: see artifact")
            failed.append(f"{sid}: possible falsification or overstrong formulation at iteration {state['iteration']}")
        if "proved" in lower:
            new_strat["score"] = float(new_strat["score"]) + 8.0
            new_strat["proved"].append(f"iteration {state['iteration']}: see artifact")
        if "sharpest_remaining_theorem" in lower or "remaining theorem" in lower:
            new_strat["score"] = float(new_strat["score"]) + 2.0
            new_strat["open"].append(f"iteration {state['iteration']}: see artifact")

        updated.append(new_strat)  # type: ignore[arg-type]
        batch_report_parts.append(f"# Strategy {sid}\n\n{result}\n")
        ledger.append(
            Finding(
                status="HEURISTIC",
                strategy_id=sid,
                title=f"Iteration {state['iteration']} strategy result: {sid}",
                content=result,
            )
        )

    # Preserve untouched strategies.
    updated_ids = {s["id"] for s in updated}
    all_strats = [s for s in state["strategies"] if s["id"] not in updated_ids] + updated
    all_strats.sort(key=lambda s: int(s["priority"]))

    batch = "\n\n---\n\n".join(batch_report_parts)
    write_artifact(state, f"iteration_{state['iteration']:02d}/strategy_batch_report.md", batch)

    return {
        "strategies": all_strats,
        "last_strategy_batch_result": batch,
        "proof_ledger": ledger,
        "failed_strategies": failed,
    }


def symbolic_checks() -> str:
    A1, A2, B1, B2 = sp.symbols("A1 A2 B1 B2")
    M1 = sp.Matrix([[-B1, 12 - B1], [A1, B1]])
    M2 = sp.Matrix([[-B2, 12 - B2], [A2, B2]])
    prod = sp.expand(M1 * M2)
    expected = sp.Matrix(
        [
            [A2 * (12 - B1) + B1 * B2, 12 * (B2 - B1)],
            [B1 * A2 - A1 * B2, A1 * (12 - B2) + B1 * B2],
        ]
    )
    product_ok = sp.simplify(prod - expected) == sp.zeros(2, 2)

    A, B = sp.symbols("A B")
    s0 = (A + B / 2 - 3) / 3
    t0 = B / 2 - s0 - 1
    Delta = sp.expand(s0**2 - 4 * t0)
    cleared = sp.expand(36 * Delta)
    expected_delta = sp.expand(4 * A**2 + 4 * A * B + 24 * A + B**2 - 60 * B + 36)
    delta_ok = sp.simplify(cleared - expected_delta) == 0

    # Main shifted-product hyperbola check.
    r, s, t, u, alpha = sp.symbols("r s t u alpha")
    alpha_expr = r - s + t - u
    lhs = (alpha * B1 - 12 * (t - u)) * (alpha * B2 - 12 * (r + t))
    rhs = 144 * ((t - u) * (r + t) - alpha * t)
    bilinear = alpha * B1 * B2 - 12 * B1 * (r + t) - 12 * B2 * (t - u) + 144 * t
    hyperbola_diff = sp.expand(lhs - rhs - alpha * bilinear)
    hyperbola_ok = sp.simplify(hyperbola_diff.subs(alpha, alpha_expr)) == 0

    return "\n".join(
        [
            "# Symbolic checks",
            f"Product formula OK: {product_ok}",
            f"Discriminant formula OK: {delta_ok}",
            f"Shifted-product hyperbola identity OK: {hyperbola_ok}",
            "",
            "M1*M2 computed:",
            str(prod),
            "",
            "36Δ computed:",
            str(cleared),
        ]
    )


def node_symbolic_checks(state: ResearchState) -> dict[str, Any]:
    result = symbolic_checks()
    write_artifact(state, f"iteration_{state['iteration']:02d}/symbolic_checks.md", result)
    findings = list(state["computational_findings"])
    findings.append(
        Finding(
            status="COMPUTATIONAL",
            strategy_id="symbolic",
            title=f"Iteration {state['iteration']} symbolic checks",
            content=result,
        )
    )
    return {"last_symbolic_result": result, "computational_findings": findings}


FORMALIZATION_PROMPT_TEMPLATE = """
You are preparing small Lean 4 formalization tasks for the Erdős divisor-sum project.

Current frontier:
{frontier}

Recent strategy results:
{strategy_results}

Task:
Extract 1-3 small algebraic lemmas that are suitable for formalization.
Prefer lemmas involving polynomial identities, matrix multiplication, discriminant identities, or trace-zero involution.

For each lemma, return JSON with:
- id
- informal_statement
- informal_proof
- lean_statement
- lean_code

Lean code can include `by ring` for polynomial identities where appropriate.
Do not include sorry unless the purpose is only a statement skeleton. Prefer complete small examples.
Return only JSON list.
"""


def parse_json_list(text: str) -> list[dict[str, Any]]:
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    except Exception:
        pass

    # Try extracting fenced JSON.
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    if match:
        try:
            obj = json.loads(match.group(1))
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
        except Exception:
            return []
    return []



def node_cas_degeneracy(state: ResearchState) -> dict[str, Any]:
    """Run optional CAS-backed pairwise degeneracy analysis."""
    client = CASDegeneracyClient(state["out_dir"])
    result_obj = client.run(f"it{state['iteration']:02d}_pairwise")
    text = json.dumps(result_obj, indent=2, ensure_ascii=False)
    write_artifact(state, f"iteration_{state['iteration']:02d}/cas_pairwise_degeneracy.json", text)

    readable = ["# CAS pairwise degeneracy analysis", ""]
    readable.append(f"Sage script: {result_obj.get('sage_script')}")
    readable.append(f"Magma script: {result_obj.get('magma_script')}")
    readable.append("")
    if isinstance(result_obj.get("sage"), dict):
        readable.append("## Sage result")
        readable.append("```json")
        readable.append(json.dumps(result_obj["sage"], indent=2, ensure_ascii=False)[:12000])
        readable.append("```")
    if isinstance(result_obj.get("magma"), dict):
        readable.append("## Magma result")
        readable.append("```json")
        readable.append(json.dumps(result_obj["magma"], indent=2, ensure_ascii=False)[:12000])
        readable.append("```")
    readable.append("## SymPy fallback")
    readable.append("```text")
    readable.append(str(result_obj.get("sympy_fallback", ""))[:12000])
    readable.append("```")
    md = "\n".join(readable)
    write_artifact(state, f"iteration_{state['iteration']:02d}/cas_pairwise_degeneracy.md", md)

    findings = list(state["computational_findings"])
    findings.append(Finding(status="COMPUTATIONAL", strategy_id="cas_pairwise_degeneracy", title=f"Iteration {state['iteration']} CAS pairwise degeneracy", content=md))
    return {"last_cas_result": md, "computational_findings": findings}

def node_generate_formal_tasks(state: ResearchState) -> dict[str, Any]:
    prompt = FORMALIZATION_PROMPT_TEMPLATE.format(
        frontier=state["current_frontier"],
        strategy_results=state["last_strategy_batch_result"][:12000],
    )
    raw = call_llm(prompt)
    write_artifact(state, f"iteration_{state['iteration']:02d}/formal_task_generation_raw.md", raw)

    tasks_raw = parse_json_list(raw)
    tasks: list[FormalTask] = list(state["formal_tasks"])
    for i, item in enumerate(tasks_raw):
        task_id = f"it{state['iteration']:02d}_formal_{i:02d}"
        tasks.append(
            FormalTask(
                id=task_id,
                source_strategy="formalization",
                informal_statement=str(item.get("informal_statement", "")),
                informal_proof=str(item.get("informal_proof", "")),
                lean_statement=str(item.get("lean_statement", "")),
                lean_code=str(item.get("lean_code", "")),
                backend="pending",
                status="pending",
                output="",
            )
        )
    return {"formal_tasks": tasks}


def node_run_formalization(state: ResearchState) -> dict[str, Any]:
    tasks: list[FormalTask] = []
    aristotle = AristotleClient()
    report_parts: list[str] = []

    for task in state["formal_tasks"]:
        if task["status"] != "pending":
            tasks.append(task)
            continue

        lean_code = task["lean_code"].strip()
        if not lean_code:
            task["status"] = "skipped"
            task["backend"] = "none"
            task["output"] = "No Lean code provided."
            tasks.append(task)
            continue

        local = run_local_lean(lean_code, state["out_dir"], task["id"])
        if local.get("ok"):
            task["status"] = "verified"
            task["backend"] = "local_lean"
            task["output"] = json.dumps(local, indent=2)
            tasks.append(task)
            report_parts.append(f"## {task['id']} VERIFIED by local Lean\n\n{task['informal_statement']}\n")
            continue

        if aristotle.available():
            art = aristotle.prove(lean_code, task["informal_proof"])
            task["status"] = "aristotle_attempted_verified" if art.get("ok") else "aristotle_failed"
            task["backend"] = str(art.get("backend", "aristotle"))
            task["output"] = json.dumps(art, indent=2, ensure_ascii=False)
            report_parts.append(f"## {task['id']} Aristotle result\n\n```json\n{task['output']}\n```\n")
        else:
            task["status"] = "unverified_no_backend"
            task["backend"] = "none"
            task["output"] = json.dumps(local, indent=2)
            report_parts.append(
                f"## {task['id']} not verified\n\nNo successful local Lean check and no Aristotle backend configured.\n\n```json\n{task['output']}\n```\n"
            )
        tasks.append(task)

    report = "\n\n".join(report_parts) if report_parts else "No new formalization tasks run."
    write_artifact(state, f"iteration_{state['iteration']:02d}/formalization_report.md", report)
    return {"formal_tasks": tasks, "last_formalization_result": report}


def node_synthesize(state: ResearchState) -> dict[str, Any]:
    strategies_json = json.dumps(state["strategies"], indent=2)
    prompt = f"""
Synthesize this iteration of the multi-strategy proof search.

Current frontier:
{state['current_frontier']}

Active strategy results:
{state['last_strategy_batch_result'][:16000]}

Symbolic checks:
{state['last_symbolic_result']}

CAS pairwise degeneracy results:
{state.get('last_cas_result', '')[:12000]}

Formalization results:
{state['last_formalization_result'][:8000]}

Current strategy table:
{strategies_json[:12000]}

Return:
1. PROVED statements.
2. CONDITIONAL statements.
3. COMPUTATIONAL findings.
4. HEURISTIC interpretations.
5. FAILED/OPEN statements.
6. Strategies falsified or demoted this iteration.
7. Strategy score updates, conceptually.
8. Sharpest remaining theorem.
9. Whether the full project is resolved.
10. Exact next theorem if unresolved.
"""
    result = call_llm(prompt)
    write_artifact(state, f"iteration_{state['iteration']:02d}/synthesis.md", result)

    resolved = False
    lower = result.lower()
    if "full project is resolved" in lower and "failed/open" not in lower and "not resolved" not in lower:
        resolved = True

    remaining = extract_remaining_theorem(result)
    return {"last_synthesis": result, "sharpest_remaining_theorem": remaining, "resolved": resolved}


def extract_remaining_theorem(text: str) -> str:
    keys = [
        "Sharpest remaining theorem",
        "Exact next theorem",
        "next theorem",
        "true obstruction",
        "FAILED/OPEN",
    ]
    lower = text.lower()
    for key in keys:
        idx = lower.find(key.lower())
        if idx >= 0:
            return text[idx : idx + 2500]
    return text[-2500:]


def node_increment(state: ResearchState) -> dict[str, Any]:
    return {"iteration": state["iteration"] + 1}


def should_continue(state: ResearchState) -> Literal["continue", "end"]:
    if state["resolved"]:
        return "end"
    if state["iteration"] + 1 >= state["max_iterations"]:
        return "end"
    return "continue"


def build_graph():
    graph = StateGraph(ResearchState)
    graph.add_node("select_strategies", node_select_strategies)
    graph.add_node("run_strategies", node_run_strategies)
    graph.add_node("symbolic_checks", node_symbolic_checks)
    graph.add_node("cas_degeneracy", node_cas_degeneracy)
    graph.add_node("generate_formal_tasks", node_generate_formal_tasks)
    graph.add_node("run_formalization", node_run_formalization)
    graph.add_node("synthesize", node_synthesize)
    graph.add_node("increment", node_increment)

    graph.add_edge(START, "select_strategies")
    graph.add_edge("select_strategies", "run_strategies")
    graph.add_edge("run_strategies", "symbolic_checks")
    graph.add_edge("symbolic_checks", "cas_degeneracy")
    graph.add_edge("cas_degeneracy", "generate_formal_tasks")
    graph.add_edge("generate_formal_tasks", "run_formalization")
    graph.add_edge("run_formalization", "synthesize")
    graph.add_conditional_edges("synthesize", should_continue, {"continue": "increment", "end": END})
    graph.add_edge("increment", "select_strategies")

    return graph.compile(checkpointer=InMemorySaver())


def initial_state(out_dir: str, iterations: int, parallel_strategies: int) -> ResearchState:
    return ResearchState(
        run_id=datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"),
        out_dir=out_dir,
        iteration=0,
        max_iterations=iterations,
        parallel_strategies=parallel_strategies,
        project_setup=PROJECT_SETUP,
        current_frontier=CURRENT_FRONTIER,
        strategies=default_strategies(),
        active_strategy_ids=[],
        proof_ledger=[],
        computational_findings=[],
        formal_tasks=[],
        failed_strategies=[],
        sharpest_remaining_theorem="",
        last_strategy_batch_result="",
        last_symbolic_result="",
        last_cas_result="",
        last_formalization_result="",
        last_synthesis="",
        resolved=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--parallel-strategies", type=int, default=3)
    parser.add_argument("--out", type=str, default="runs/erdos_multistrategy_run")
    parser.add_argument("--thread-id", type=str, default="erdos-multistrategy-formal")
    args = parser.parse_args()

    Path(args.out).mkdir(parents=True, exist_ok=True)
    state = initial_state(args.out, args.iterations, args.parallel_strategies)
    app = build_graph()
    config = {"configurable": {"thread_id": args.thread_id}}
    final_state = app.invoke(state, config=config)

    final_path = Path(args.out) / "final_state.json"
    final_path.write_text(json.dumps(final_state, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote run artifacts to {args.out}")
    print(f"Wrote final state to {final_path}")
    print("\n=== Last synthesis ===\n")
    print(final_state.get("last_synthesis", ""))


if __name__ == "__main__":
    main()
