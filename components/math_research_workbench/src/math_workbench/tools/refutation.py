"""Counterexample search: the refutation half of the workbench.

Three entry points, in increasing order of trust:

- `search_conjecture` -- enumerate a declared search space looking for a witness.
  Enumeration is *diagonal* (by increasing index sum), so a two-variable search
  finds small counterexamples in both variables instead of exhausting the first
  variable's range first.
- `verify_witness` -- re-check one assignment with both evaluators.  Nothing is
  recorded as a refutation without this.
- `check_claimed_witnesses` -- take the witnesses an LLM lane *claims* to have
  found, and put each one through `verify_witness`.  Claimed witnesses are
  routinely wrong; this is the step that stops a plausible-looking assignment
  from entering the ledger as a refutation.

Exhausting a finite space without finding a witness is also a result: it is a
proof by exhaustion over that space, and is reported as `VERIFIED_EXHAUSTIVE`.
It is only claimed when every point was evaluated with no errors and no
evaluator disagreements -- a search that skipped points proves nothing.
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

from math_workbench.conjecture import (
    AGREEMENT_CONTESTED,
    AGREEMENT_DUAL_EXACT,
    AGREEMENT_ERROR,
    Conjecture,
    Evaluation,
    _jsonable,
)

__all__ = [
    "SearchBudget",
    "SearchOutcome",
    "Witness",
    "shell_indices",
    "search_conjecture",
    "search_conjectures",
    "verify_witness",
    "extract_claimed_witnesses",
    "check_claimed_witnesses",
    "render_report",
    "VERIFIED_EXACT",
    "VERIFIED_SINGLE",
    "CONTESTED",
    "REJECTED",
    "UNCHECKED",
]

# Verification verdicts, strongest first.
VERIFIED_EXACT = "VERIFIED_EXACT"      # both independent evaluators agree it refutes
VERIFIED_SINGLE = "VERIFIED_SINGLE"    # only one evaluator could decide
CONTESTED = "CONTESTED"                # the evaluators disagree -- investigate before use
REJECTED = "REJECTED"                  # not a counterexample (predicate holds, or assumptions fail)
UNCHECKED = "UNCHECKED"                # could not be evaluated at all

# Conjecture-level statuses.
STATUS_OPEN = "OPEN"
STATUS_FALSIFIED = "FALSIFIED"
STATUS_VERIFIED_EXHAUSTIVE = "VERIFIED_EXHAUSTIVE"
STATUS_CONTESTED = "CONTESTED"

SOURCE_AUTO = "AUTO_SEARCH"
SOURCE_LLM = "LLM_LANE"
SOURCE_MANUAL = "MANUAL"


@dataclass(frozen=True)
class SearchBudget:
    """How much work one conjecture is allowed to consume."""

    max_evaluations: int = 5_000
    random_samples: int = 0
    seed: int = 20240729
    time_limit_s: float = 30.0
    max_witnesses: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SearchBudget":
        data = data or {}
        return cls(
            max_evaluations=int(data.get("max_evaluations", 5_000)),
            random_samples=int(data.get("random_samples", 0)),
            seed=int(data.get("seed", 20240729)),
            time_limit_s=float(data.get("time_limit_s", 30.0)),
            max_witnesses=int(data.get("max_witnesses", 3)),
        )


@dataclass
class Witness:
    """A concrete assignment offered as a refutation, plus how it was checked."""

    conjecture_id: str
    assignment: dict[str, Any]
    verification: str
    source: str = SOURCE_AUTO
    detail: str = ""
    rationale: str = ""
    minimal: bool = False

    def refutes(self) -> bool:
        return self.verification in {VERIFIED_EXACT, VERIFIED_SINGLE}

    def as_dict(self) -> dict[str, Any]:
        return {
            "conjecture_id": self.conjecture_id,
            "assignment": {k: _jsonable(v) for k, v in self.assignment.items()},
            "verification": self.verification,
            "source": self.source,
            "detail": self.detail,
            "rationale": self.rationale,
            "minimal": self.minimal,
        }

    def describe(self) -> str:
        args = ", ".join(f"{k} = {_jsonable(v)}" for k, v in self.assignment.items())
        return f"{self.conjecture_id} at {args} [{self.verification}]"


@dataclass
class SearchOutcome:
    """What a search over one conjecture established."""

    conjecture_id: str
    statement: str
    status: str
    witnesses: list[Witness] = field(default_factory=list)
    contested: list[Witness] = field(default_factory=list)
    evaluated: int = 0
    space_size: int = 0
    exhausted: bool = False
    errors: int = 0
    assumption_skips: int = 0
    elapsed_s: float = 0.0
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "conjecture_id": self.conjecture_id,
            "statement": self.statement,
            "status": self.status,
            "witnesses": [w.as_dict() for w in self.witnesses],
            "contested": [w.as_dict() for w in self.contested],
            "evaluated": self.evaluated,
            "space_size": self.space_size,
            "exhausted": self.exhausted,
            "errors": self.errors,
            "assumption_skips": self.assumption_skips,
            "elapsed_s": round(self.elapsed_s, 3),
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# Enumeration order.
# --------------------------------------------------------------------------


def shell_indices(sizes: Sequence[int], limit: int | None = None) -> Iterator[tuple[int, ...]]:
    """Index tuples ordered by increasing sum, i.e. smallest candidates first.

    `itertools.product` would walk the first variable's entire range before
    advancing the second, so a search over `m in [1,10**4], n in [1,10**4]`
    with a 5000-evaluation budget would never test any `n` but `n = 1`.  This
    walks the diagonal shells instead: sum 0, then sum 1, and so on.
    """
    if not sizes:
        return
    if any(s <= 0 for s in sizes):
        return
    emitted = 0
    for total in range(sum(s - 1 for s in sizes) + 1):
        for idx in _compositions(total, sizes, 0):
            yield idx
            emitted += 1
            if limit is not None and emitted >= limit:
                return


def _compositions(total: int, sizes: Sequence[int], pos: int) -> Iterator[tuple[int, ...]]:
    if pos == len(sizes) - 1:
        if 0 <= total < sizes[pos]:
            yield (total,)
        return
    for i in range(min(total, sizes[pos] - 1) + 1):
        for rest in _compositions(total - i, sizes, pos + 1):
            yield (i,) + rest


# --------------------------------------------------------------------------
# Verification.
# --------------------------------------------------------------------------


def _classify(evaluation: Evaluation) -> tuple[str, str]:
    """Map an evaluation onto a verification verdict and an explanation."""
    if evaluation.agreement == AGREEMENT_CONTESTED:
        return CONTESTED, evaluation.detail
    if evaluation.agreement == AGREEMENT_ERROR:
        return UNCHECKED, evaluation.detail or "predicate could not be evaluated"
    if evaluation.assumptions_hold is False:
        return REJECTED, "assumptions do not hold at this assignment"
    if evaluation.holds is True:
        return REJECTED, "the predicate holds here, so this is not a counterexample"
    if evaluation.holds is None:
        return UNCHECKED, evaluation.detail or "predicate has no definite truth value here"
    if evaluation.agreement == AGREEMENT_DUAL_EXACT:
        return VERIFIED_EXACT, "rational and symbolic evaluators agree the predicate fails here"
    return VERIFIED_SINGLE, evaluation.detail or "only one evaluator could decide this assignment"


def verify_witness(
    conjecture: Conjecture,
    assignment: dict[str, Any],
    source: str = SOURCE_MANUAL,
    rationale: str = "",
) -> Witness:
    """Independently check a single claimed counterexample."""
    evaluation = conjecture.evaluate(assignment)
    verification, detail = _classify(evaluation)
    return Witness(
        conjecture_id=conjecture.id,
        assignment=evaluation.assignment or dict(assignment),
        verification=verification,
        source=source,
        detail=detail,
        rationale=rationale,
    )


# --------------------------------------------------------------------------
# Search.
# --------------------------------------------------------------------------


def search_conjecture(conjecture: Conjecture, budget: SearchBudget | None = None) -> SearchOutcome:
    """Hunt for counterexamples to one conjecture within a budget."""
    budget = budget or SearchBudget()
    started = time.monotonic()
    names = conjecture.variable_names
    domains = [conjecture.variables[n] for n in names]
    sizes = [d.size() for d in domains]
    space = conjecture.space_size()

    outcome = SearchOutcome(
        conjecture_id=conjecture.id,
        statement=conjecture.statement,
        status=STATUS_OPEN,
        space_size=space,
    )

    seen: set[tuple[Any, ...]] = set()

    def consider(assignment: dict[str, Any]) -> bool:
        """Evaluate one point; return True when the search should stop."""
        key = tuple(assignment[n] for n in names)
        if key in seen:
            return False
        seen.add(key)
        outcome.evaluated += 1
        evaluation = conjecture.evaluate(assignment)
        verification, detail = _classify(evaluation)
        if verification in {VERIFIED_EXACT, VERIFIED_SINGLE}:
            outcome.witnesses.append(
                Witness(
                    conjecture_id=conjecture.id,
                    assignment=evaluation.assignment,
                    verification=verification,
                    source=SOURCE_AUTO,
                    detail=detail,
                    minimal=not outcome.witnesses,
                )
            )
            return len(outcome.witnesses) >= budget.max_witnesses
        if verification == CONTESTED:
            outcome.contested.append(
                Witness(
                    conjecture_id=conjecture.id,
                    assignment=evaluation.assignment,
                    verification=CONTESTED,
                    source=SOURCE_AUTO,
                    detail=detail,
                )
            )
        elif verification == UNCHECKED:
            outcome.errors += 1
        elif evaluation.assumptions_hold is False:
            outcome.assumption_skips += 1
        return False

    stopped_early = False
    for idx in shell_indices(sizes, limit=budget.max_evaluations):
        if time.monotonic() - started > budget.time_limit_s:
            stopped_early = True
            outcome.notes = f"time limit of {budget.time_limit_s}s reached"
            break
        assignment = {n: d.at(i) for n, d, i in zip(names, domains, idx)}
        if consider(assignment):
            stopped_early = True
            break
    else:
        stopped_early = outcome.evaluated < space

    if not outcome.witnesses and budget.random_samples > 0 and outcome.evaluated < space:
        rng = random.Random(budget.seed)
        for _ in range(budget.random_samples):
            if time.monotonic() - started > budget.time_limit_s:
                outcome.notes = f"time limit of {budget.time_limit_s}s reached during sampling"
                break
            assignment = {n: d.sample(rng) for n, d in zip(names, domains)}
            if consider(assignment):
                break

    outcome.elapsed_s = time.monotonic() - started
    outcome.exhausted = outcome.evaluated >= space and not stopped_early

    # CONTESTED outranks FALSIFIED deliberately. A disagreement anywhere in a
    # search means one of the two evaluators has a bug, and a buggy evaluator
    # taints the verdicts it produced elsewhere in the same search -- including
    # the ones that looked like clean refutations. Reporting FALSIFIED and
    # quietly dropping the disagreement is how a wrong result ships.
    if outcome.contested:
        outcome.status = STATUS_CONTESTED
        outcome.notes = (
            f"{len(outcome.contested)} evaluator disagreement(s) in this search; "
            "one of the two evaluators is wrong. "
            + (
                f"{len(outcome.witnesses)} witness(es) were found but are not counted as "
                "refutations until the disagreement is resolved. "
                if outcome.witnesses
                else ""
            )
            + (outcome.notes or "")
        ).strip()
    elif outcome.witnesses:
        outcome.status = STATUS_FALSIFIED
    elif outcome.exhausted and outcome.errors == 0:
        outcome.status = STATUS_VERIFIED_EXHAUSTIVE
    else:
        outcome.status = STATUS_OPEN
        if outcome.errors and not outcome.notes:
            outcome.notes = f"{outcome.errors} assignment(s) could not be evaluated"

    if outcome.exhausted and outcome.errors:
        outcome.notes = (
            f"space covered but {outcome.errors} assignment(s) failed to evaluate; "
            "exhaustive verification is not claimed"
        )
    return outcome


def search_conjectures(
    conjectures: Sequence[Conjecture], budget: SearchBudget | None = None
) -> list[SearchOutcome]:
    return [search_conjecture(c, budget) for c in conjectures]


# --------------------------------------------------------------------------
# Witnesses claimed by a model.
# --------------------------------------------------------------------------

_WITNESS_BLOCK = re.compile(r"```(?:witness|json)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_claimed_witnesses(text: str) -> list[dict[str, Any]]:
    """Pull `witness` blocks out of a model response.

    Accepts a fenced ```witness block holding either one object or a list of
    them.  Plain ```json blocks are accepted too, but only when they actually
    carry an `assignment` key, so ordinary JSON in a report is not mistaken for
    a refutation claim.
    """
    claims: list[dict[str, Any]] = []
    for match in _WITNESS_BLOCK.finditer(text or ""):
        body = match.group(1).strip()
        if not body:
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        for item in payload if isinstance(payload, list) else [payload]:
            if isinstance(item, dict) and "assignment" in item:
                claims.append(item)
    return claims


def check_claimed_witnesses(
    conjectures: Sequence[Conjecture], text: str, source: str = SOURCE_LLM
) -> list[Witness]:
    """Verify every witness a model claimed, including ones naming no conjecture."""
    by_id = {c.id: c for c in conjectures}
    checked: list[Witness] = []
    for claim in extract_claimed_witnesses(text):
        assignment = claim.get("assignment")
        if not isinstance(assignment, dict):
            continue
        rationale = str(claim.get("rationale", claim.get("reason", "")))
        cid = str(claim.get("conjecture", claim.get("conjecture_id", "")))
        targets = [by_id[cid]] if cid in by_id else list(conjectures)
        if cid and cid not in by_id:
            rationale = f"(claimed conjecture id {cid!r} is not declared) {rationale}".strip()
        for conjecture in targets:
            if set(assignment) != set(conjecture.variable_names):
                continue
            checked.append(verify_witness(conjecture, assignment, source=source, rationale=rationale))
    return checked


# --------------------------------------------------------------------------
# Reporting.
# --------------------------------------------------------------------------


def render_report(outcomes: Sequence[SearchOutcome], claimed: Sequence[Witness] = ()) -> str:
    """A markdown refutation report suitable for the iteration directory."""
    lines = ["# Counterexample search report", ""]
    if not outcomes and not claimed:
        lines.append("No executable conjectures were declared for this problem.")
        lines.append("")
        lines.append(
            "Add a `conjectures:` block to the problem YAML to enable automated "
            "refutation; without one, only the model-proposed witnesses are checked."
        )
        return "\n".join(lines)

    falsified = [o for o in outcomes if o.status == STATUS_FALSIFIED]
    exhaustive = [o for o in outcomes if o.status == STATUS_VERIFIED_EXHAUSTIVE]
    contested = [o for o in outcomes if o.status == STATUS_CONTESTED]

    lines += [
        "## Summary",
        "",
        f"- conjectures searched: {len(outcomes)}",
        f"- falsified: {len(falsified)}",
        f"- verified exhaustively over the declared space: {len(exhaustive)}",
        f"- contested (evaluators disagree -- treat as a bug): {len(contested)}",
        f"- still open: {len(outcomes) - len(falsified) - len(exhaustive) - len(contested)}",
        "",
    ]

    for outcome in outcomes:
        lines += [f"## {outcome.conjecture_id} -- {outcome.status}", "", outcome.statement, ""]
        coverage = (
            f"{outcome.evaluated} of {outcome.space_size} points"
            if outcome.space_size
            else f"{outcome.evaluated} points"
        )
        lines.append(
            f"Searched {coverage} in {outcome.elapsed_s:.2f}s"
            + (" (space exhausted)." if outcome.exhausted else ".")
        )
        if outcome.assumption_skips:
            lines.append(f"{outcome.assumption_skips} point(s) skipped because assumptions failed.")
        if outcome.notes:
            lines.append(f"Note: {outcome.notes}")
        lines.append("")
        for witness in outcome.witnesses:
            marker = " (minimal in search order)" if witness.minimal else ""
            lines.append(f"- **Counterexample**{marker}: {witness.describe()}")
            lines.append(f"  - {witness.detail}")
        for witness in outcome.contested:
            lines.append(f"- **CONTESTED**: {witness.describe()}")
            lines.append(f"  - {witness.detail}")
        if outcome.status == STATUS_VERIFIED_EXHAUSTIVE:
            lines.append(
                "- No counterexample exists in the declared space. This is a proof by "
                "exhaustion over that space only, not a proof of the general statement."
            )
        lines.append("")

    if claimed:
        lines += ["## Model-proposed witnesses", ""]
        for witness in claimed:
            lines.append(f"- {witness.describe()}")
            lines.append(f"  - {witness.detail}")
            if witness.rationale:
                lines.append(f"  - claimed because: {witness.rationale[:400]}")
        rejected = [w for w in claimed if w.verification == REJECTED]
        if rejected:
            lines += [
                "",
                f"{len(rejected)} of {len(claimed)} proposed witness(es) did not survive "
                "independent checking and were discarded.",
            ]
        lines.append("")
    return "\n".join(lines)


def summarise_for_prompt(outcomes: Sequence[SearchOutcome], claimed: Sequence[Witness] = ()) -> str:
    """A compact digest to feed back into the next model call."""
    parts: list[str] = []
    for outcome in outcomes:
        head = f"{outcome.conjecture_id}: {outcome.status}"
        if outcome.witnesses:
            head += " -- " + "; ".join(w.describe() for w in outcome.witnesses[:3])
        elif outcome.status == STATUS_VERIFIED_EXHAUSTIVE:
            head += f" -- no counterexample in {outcome.space_size} points"
        parts.append(head)
    verified = [w for w in claimed if w.refutes()]
    discarded = [w for w in claimed if not w.refutes()]
    if verified:
        parts.append("model witnesses that survived checking: " + "; ".join(w.describe() for w in verified))
    if discarded:
        parts.append(
            "model witnesses discarded on checking: "
            + "; ".join(f"{w.describe()} ({w.detail})" for w in discarded[:5])
        )
    return "\n".join(parts) if parts else "no refutation signal this iteration"
