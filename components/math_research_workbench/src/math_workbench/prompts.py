from __future__ import annotations

SYSTEM_PROMPT = """
You are a mathematical proof-search assistant.

Rules:
1. Do not overclaim.
2. Every mathematical claim must be labeled exactly one of:
   PROVED, CONDITIONAL, COMPUTATIONAL, HEURISTIC, FAILED/OPEN.
3. Falsify before proving.
4. If a theorem fails, sharpen it and state the sharper theorem.
5. Do not restart old branches unless needed for a consistency check.
6. Prefer exact algebraic reductions, symbolic verification, counterexamples, formalization, and explicit dependency tracking.
7. If unresolved, end with the exact remaining theorem.
"""

SELECT_STRATEGIES_TEMPLATE = """
Problem:
{problem_summary}

Current frontier:
{frontier}

Available strategies:
{strategies}

Select up to {k} strategies for this iteration.
Prefer strategies that directly attack the current frontier and have falsification tests.
Return:
1. selected strategies with reasons,
2. predicted proof/falsification value,
3. computations/formalization to run,
4. what would count as progress.
"""

STRATEGY_LANE_TEMPLATE = """
Problem:
{problem_summary}

Current frontier:
{frontier}

Active strategy:
{id}: {name}

Description:
{description}

Allowed tools:
{tools}

Falsification prompts:
{falsification_prompts}

Proof prompts:
{proof_prompts}

Success criteria:
{success_criteria}

Failure modes:
{failure_modes}

Task:
1. Try to falsify the strategy first.
2. If not falsified, attempt the proof/reduction.
3. State all PROVED / CONDITIONAL / COMPUTATIONAL / HEURISTIC / FAILED/OPEN claims.
4. If unresolved, give a sharper theorem.
5. Suggest exact symbolic/CAS/formalization checks.
"""

SYNTHESIS_TEMPLATE = """
Problem:
{problem_summary}

Frontier before iteration:
{frontier}

Selected strategies:
{selected_report}

Strategy reports:
{strategy_reports}

Symbolic checks:
{symbolic_report}

CAS report:
{cas_report}

Formalization report:
{formalization_report}

Discovery report:
{discovery_report}

Synthesize the iteration.
Return:
1. PROVED statements.
2. CONDITIONAL statements.
3. COMPUTATIONAL findings.
4. HEURISTIC interpretations.
5. FAILED/OPEN statements.
6. Falsified strategies.
7. Sharpest remaining theorem.
8. Whether the full project is resolved.
9. If unresolved, the exact next theorem and why it is the true obstruction.
"""

DISCOVERY_TEMPLATE = """
Problem:
{problem_summary}

Current frontier:
{frontier}

Latest synthesis:
{synthesis}

Task:
Propose up to three materially new strategies only if they are not duplicates.
For each proposed strategy, include:
- strategy id,
- name,
- core idea,
- why it might work,
- first falsification test,
- how it combines with existing strategies,
- expected proof artifact.
If no genuinely new strategy is available, say so.
"""

FORMAL_TASK_TEMPLATE = """
Given the proof attempt below, extract small formalization tasks suitable for Lean.
Prefer polynomial identities, algebraic rearrangements, injectivity lemmas, and finite case splits.
Return Lean code snippets when possible. Avoid formalizing huge analytic estimates.

Proof attempt:
{proof_text}
"""
