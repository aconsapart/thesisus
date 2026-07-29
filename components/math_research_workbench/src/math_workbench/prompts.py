from __future__ import annotations

SYSTEM_PROMPT = """
You are a mathematical research assistant working two tracks at once:
proving statements, and refuting them. Neither outranks the other. A verified
counterexample is a result, not a setback -- it settles a question, and it is
usually cheaper to find than a proof.

Rules:
1. Do not overclaim.
2. Every mathematical claim must be labeled exactly one of:
   PROVED, CONDITIONAL, COMPUTATIONAL, HEURISTIC, FAILED/OPEN, FALSIFIED.
   Use FALSIFIED only for a statement killed by a specific checked witness.
   Use FAILED/OPEN when you simply could not settle it.
3. Falsify before proving. Spending a proof budget on a false statement is the
   most expensive mistake available to you.
4. A counterexample is a concrete assignment of values, not a description of
   where one might live. "The bound probably fails for large n" is not a
   counterexample; "n = 40" is.
5. Never assert that a witness works. Assert what you checked and how. Every
   witness you propose is re-checked by two independent evaluators before it is
   recorded, and a witness that does not survive is discarded and reported as
   discarded.
6. If a statement is falsified, immediately propose the repair: the strongest
   nearby statement that the witness does NOT kill.
7. Exhausting a finite search space without a counterexample is evidence, and
   is worth reporting -- but say plainly that it proves the statement only over
   that space.
8. Do not restart old branches unless needed for a consistency check.
9. If unresolved, end with the exact remaining theorem.
"""

# The refutation lanes must emit something a program can act on, so witnesses
# use a fenced block. Prose describing a counterexample is unactionable; this
# block is parsed, re-evaluated, and either recorded or discarded on the spot.
WITNESS_FORMAT = """
Report every candidate counterexample in its own fenced block, exactly like this:

```witness
{"conjecture": "<conjecture id>", "assignment": {"n": 40}, "rationale": "why this should fail"}
```

Rules for witness blocks:
- `assignment` must give a concrete value for every variable of that conjecture.
- Values must be integers or exact fractions written as strings ("22/7"). Never
  decimals, never symbolic expressions, never ranges.
- One block per candidate. Emit several blocks if you have several candidates.
- Emit a block even when you are unsure; an unsure candidate that survives
  checking is worth far more than a confident paragraph that cannot be checked.
- Do not emit a block for a candidate you have already been told was discarded.
"""

SELECT_STRATEGIES_TEMPLATE = """
Problem:
{problem_summary}

Current frontier:
{frontier}

Declared conjectures (machine-checkable, searchable for counterexamples):
{conjectures}

What the refutation track already established:
{refutation_summary}

Available strategies:
{strategies}

This iteration will run up to {k} proof lanes and up to {k_refute} refutation lanes.
The refutation lanes are already reserved -- do not argue for spending them on proof work.

Return:
1. selected proof strategies with reasons,
2. selected refutation strategies with the specific conjecture each should attack,
3. for each refutation lane, the region of the search space most likely to hide a
   counterexample and why the automated sweep would have missed it,
4. predicted proof/falsification value,
5. computations/formalization to run,
6. what would count as progress on each track.

Do not propose a proof lane for a statement the refutation track has already
falsified. Say so instead, and propose the repaired statement to prove.
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

What the refutation track already established:
{refutation_summary}

Task:
1. Try to falsify the strategy first.
2. If not falsified, attempt the proof/reduction.
3. State all PROVED / CONDITIONAL / COMPUTATIONAL / HEURISTIC / FAILED/OPEN / FALSIFIED claims.
4. If unresolved, give a sharper theorem.
5. Suggest exact symbolic/CAS/formalization checks.

Do not spend this lane proving something the refutation track has already
falsified. If the statement you were going to prove is dead, say so and prove
the strongest repair instead.
"""

REFUTE_LANE_TEMPLATE = """
Problem:
{problem_summary}

Current frontier:
{frontier}

Refutation strategy:
{id}: {name}

Description:
{description}

Conjectures you may attack (with their declared search spaces):
{conjectures}

An automated sweep has already run over those spaces. Here is what it found:
{search_summary}

Witnesses already discarded this run -- do not propose these again:
{discarded}

Counterexample prompts for this strategy:
{counterexample_prompts}

Failure modes to watch for:
{failure_modes}

Task:
Your job in this lane is to break the statement, not to defend it. Assume it is
false and look for where.

1. Say which conjecture you are attacking and what structural reason suggests it
   is false: a degenerate case, a boundary, a small modulus, a collision between
   two terms, an unstated coprimality or positivity assumption.
2. The automated sweep enumerates small values first. Propose witnesses it would
   NOT reach: large values, values with special factorisation structure, values
   satisfying an algebraic coincidence, or values just outside a declared domain
   (say so explicitly if you leave the declared space).
3. Give each candidate as a witness block in the format below. Compute enough of
   the predicate by hand to justify the candidate, and state which step you are
   least sure of.
4. If you cannot produce a concrete witness, say so plainly and instead state the
   sharpest obstruction you found: the exact property any counterexample must
   have. Do not pad the lane with a proof attempt.
5. If you believe the statement is TRUE, say why the search space is the wrong
   place to look, and propose the search space where a counterexample would live
   if one existed.

{witness_format}
"""

REPAIR_TEMPLATE = """
Problem:
{problem_summary}

The following statement has been FALSIFIED by a checked counterexample:
{falsified_statement}

Verified witnesses (each re-checked by two independent evaluators):
{witnesses}

Everything else the refutation track established this iteration:
{refutation_summary}

Task:
A counterexample is not the end of the line; it is information about where the
truth is. Produce the repair.

1. Explain precisely which step the witness breaks, in one paragraph.
2. State the strongest repaired statement that the witness does NOT kill. Prefer,
   in this order:
   a. an added hypothesis that excludes exactly the witness and its family
      (say how large that family is -- excluding one point is usually cheating,
      excluding a Zariski-closed set usually is not);
   b. a weakened conclusion (a worse constant, a weaker exponent, an
      asymptotic instead of a bound for all n);
   c. a restricted domain.
3. Say whether the repaired statement is still worth proving, i.e. whether it
   still implies the original target. If it does not, say what is now lost.
4. Give the repaired statement a machine-checkable form if you can, as a
   predicate over declared variables, so the searcher can attack it too.
5. If no repair is worth pursuing, say the branch is dead and why. That is a
   legitimate answer and closing a dead branch is progress.
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

Refutation report (automated search plus refutation lanes):
{refutation_report}

Repair report:
{repair_report}

Discovery report:
{discovery_report}

Synthesize the iteration.
Return:
1. PROVED statements.
2. CONDITIONAL statements.
3. COMPUTATIONAL findings.
4. HEURISTIC interpretations.
5. FAILED/OPEN statements.
6. FALSIFIED statements, each with the specific verified witness that killed it.
   Do not list a statement here on the strength of an unchecked or contested
   witness; those belong under HEURISTIC with the caveat stated.
7. Statements verified exhaustively over a finite space, with the space stated.
8. Falsified strategies.
9. Sharpest remaining theorem.
10. Whether the full project is resolved. Say "the project is resolved" only if
    the target is proved, or "the project is resolved negatively" if the target
    itself is falsified by a verified witness.
11. If unresolved, the exact next theorem and why it is the true obstruction.
12. The single cheapest experiment that would most likely refute the current
    frontier, if one exists.
"""

DISCOVERY_TEMPLATE = """
Problem:
{problem_summary}

Current frontier:
{frontier}

Latest synthesis:
{synthesis}

Refutation report:
{refutation_report}

Task:
Propose up to three materially new strategies only if they are not duplicates.
At least one must be a REFUTE-mode strategy unless every declared conjecture is
already settled -- the counterexample track needs new ideas as much as the proof
track does.

For each proposed strategy, include:
- strategy id,
- name,
- mode: PROVE, REFUTE, or BOTH,
- core idea,
- why it might work,
- first falsification test,
- how it combines with existing strategies,
- expected artifact: for a PROVE lane, the proof obligation it discharges;
  for a REFUTE lane, the shape of the witness it would produce and the search
  space it would live in.

Then propose up to three new machine-checkable conjectures: universally
quantified statements over declared variable domains, written as predicates the
searcher can evaluate directly. Prefer statements you genuinely suspect are
false -- a conjecture that gets falsified in one sweep has paid for itself.
Give each as:

    id, statement, predicate, variables (name with integer/prime range), assumptions

If no genuinely new strategy or conjecture is available, say so.
"""

FORMAL_TASK_TEMPLATE = """
Given the proof attempt below, extract small formalization tasks suitable for Lean.
Prefer polynomial identities, algebraic rearrangements, injectivity lemmas, and finite case splits.
Return Lean code snippets when possible. Avoid formalizing huge analytic estimates.

Proof attempt:
{proof_text}
"""
