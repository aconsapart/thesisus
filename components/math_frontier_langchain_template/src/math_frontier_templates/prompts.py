"""LangChain prompt templates for mathematical frontier proof search.

These templates use Mustache format so mathematical braces in LaTeX do not
need to be escaped. LangChain ChatPromptTemplate supports reusable chat
prompts with variables supplied at runtime.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = PACKAGE_ROOT / "templates"


def _load(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def frontier_master_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", "You are a rigorous mathematical proof-search assistant. Do not overclaim."),
            ("human", _load("frontier_master_prompt.md")),
        ],
        template_format="mustache",
    )


def planner_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", "You are a strategy-selection node in a proof-search graph."),
            ("human", _load("planner_prompt.md")),
        ],
        template_format="mustache",
    )


def strategy_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", "You are a single-strategy proof attempt node. Falsify first."),
            ("human", _load("strategy_prompt.md")),
        ],
        template_format="mustache",
    )


def synthesis_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", "You synthesize proof-search iterations conservatively."),
            ("human", _load("synthesis_prompt.md")),
        ],
        template_format="mustache",
    )


def meta_strategy_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", "You propose new proof strategies and falsification tests."),
            ("human", _load("meta_strategy_prompt.md")),
        ],
        template_format="mustache",
    )


def default_inputs() -> Dict[str, Any]:
    """Example runtime variables for the current frontier."""
    return {
        "project_setup": """
K(n)=3n+12-2σ(n), s(n)=σ(n)-n, and A(n) counts admissible divisors d|K(n). The primitive semiprime-side count satisfies S(n)<=A(n).
""".strip(),
        "current_frontier": """
Off-identity product energy of the trace-zero Möbius involution family M_{p,q}=[[-B,12-B],[A,B]], with A=2(q+1)-p(q-2), B=2(p+1)(q+1). The corrected obstruction is exact short-box product-fiber curve incidence retaining both A and B.
""".strip(),
        "known_facts": """
PROVED: tr(M)=0. PROVED: M^2=(B^2-AC)I. PROVED: projective injectivity. PROVED: product-fiber hyperbola and exact first-pair curve. FAILED/CORRECTED: shifted-product multiset alone overcounts because it drops the A constraint.
""".strip(),
        "primary_target": """
Prove random-sized second moment for exact short-box product-fiber curve intersections: M_{p1,q1}M_{p2,q2}~R retaining A_i and B_i constraints.
""".strip(),
        "strategy_portfolio": """
1. Exact product-fiber curve incidence.
2. Hyperbola-Möbius correlation theorem.
3. Averaged product-fiber large sieve.
4. Short-box Möbius random energy.
5. Near-injectivity/collision energy.
6. Geometric divisor-window rigidity.
""".strip(),
        "work_checks": """
Verify M1M2 formula, hyperbola completion, A/B recovery of p,q, discriminant identity, exceptional branches s=0, alpha=0, beta=0, Q(R)=0, poles.
""".strip(),
        "related_theorems": """
Bourgain-Garaev-Konyagin-Shparlinski shifted-product congruences; Warren-Wheeler Möbius incidence; Fouvry-Kowalski-Michel trace functions; Burgess/Type-II mixed character sums; product-growth in PGL2.
""".strip(),
        "dependency_chain": """
exact product-fiber incidence -> off-identity Möbius energy -> Möbius incidence -> final-core occupancy -> rank-two branch -> sum A(n)<<X(log X)^C.
""".strip(),
        "failed_strategies": "integer lifting globally; shifted-product multiset without A constraint; individual very-short character sum without lower-size or averaging; generic incidence alone.",
        "parallel_strategies": 3,
        "strategy_name": "exact_product_fiber_curve_incidence",
        "strategy_instructions": "Attack M_{p1,q1}M_{p2,q2}~R by retaining exact A and B constraints; derive curve equations; falsify high-fiber families; prove or sharpen second moment.",
        "strategy_outputs": "",
        "symbolic_checks": "",
        "formalization_results": "",
        "sharpest_remaining_theorem": "Exact Short-Box Product-Fiber Curve-Intersection Theorem",
        "computational_evidence": "Near-injectivity, low map multiplicity, low off-identity fibers, random-like inverse hits.",
    }
