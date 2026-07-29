"""Hostile prior-art recon: the third way a claim can die.

A claim can fail three ways, in increasing order of cost to discover:

1. it is already known -- someone published it (this module);
2. it is false -- a counterexample exists (`conjecture` / `tools.refutation`);
3. it is unproved -- nobody can establish it (the proof lanes).

Checking (1) first is day-zero work, not day-two work. A theorem already in the
literature is not wrong, but it is not a contribution either, and finding that
out after a proof campaign is the most avoidable waste available.

The model does the searching. This module enforces the discipline that makes a
search result mean something, because "we looked and found nothing" is a claim
about the *search*, not about the literature:

- **Union over at least two passes.** A single search reliably misses severe
  threats, so a claim assessed by one pass is `UNDER_SEARCHED`, not `CLEAR`.
  Threats are unioned across passes; the worst verdict wins.
- **Angle coverage.** Concepts hide under other vocabularies, so a clear verdict
  requires searching by mechanism, by synonym, by application, *and* in an
  adjacent field. The killing citation is often in another literature.
- **Negative searches are the evidence.** A `CLEAR` verdict must be backed by
  logged queries that returned nothing. An unlogged clear verdict is an opinion.
- **Overclaims are detected, not trusted.** "First", "novel", "we introduce" are
  priority claims; each must be backed by a `CLEAR` assessment or removed.

The asymmetry is deliberate and mirrors `VERIFIED_EXHAUSTIVE` in the refutation
track: finding a killer is evidence however sloppily you looked, but finding
nothing is evidence only if you looked properly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

__all__ = [
    "Claim",
    "Threat",
    "SearchQuery",
    "SearchPass",
    "ClaimAssessment",
    "PriorArtPolicy",
    "PriorArtError",
    "assess_claims",
    "scan_overclaims",
    "load_claims",
    "VERDICTS",
    "ANGLES",
]


class PriorArtError(ValueError):
    """A claim or search-pass specification is malformed."""


# --------------------------------------------------------------------------
# Vocabulary.
# --------------------------------------------------------------------------

VERDICT_KILLS = "KILLS"          # prior art already reports this claim
VERDICT_WOUNDS = "WOUNDS"        # prior art forces the claim to be narrowed
VERDICT_ADJACENT = "ADJACENT"    # close enough that it must be cited and distinguished
VERDICT_BACKGROUND = "BACKGROUND"  # context, no threat

VERDICTS = (VERDICT_KILLS, VERDICT_WOUNDS, VERDICT_ADJACENT, VERDICT_BACKGROUND)
_SEVERITY = {VERDICT_KILLS: 3, VERDICT_WOUNDS: 2, VERDICT_ADJACENT: 1, VERDICT_BACKGROUND: 0}

ANGLE_MECHANISM = "MECHANISM"            # the thing itself, in its own vocabulary
ANGLE_SYNONYM = "SYNONYM"                # the same idea under a different name
ANGLE_APPLICATION = "APPLICATION"        # where it would be used
ANGLE_ADJACENT_FIELD = "ADJACENT_FIELD"  # another literature entirely

ANGLES = (ANGLE_MECHANISM, ANGLE_SYNONYM, ANGLE_APPLICATION, ANGLE_ADJACENT_FIELD)
REQUIRED_ANGLES = frozenset(ANGLES)

STATUS_KILLED = "KILLED"
STATUS_WOUNDED = "WOUNDED"
STATUS_CLEAR = "CLEAR"
STATUS_UNDER_SEARCHED = "UNDER_SEARCHED"

CLAIM_STATUSES = (STATUS_KILLED, STATUS_WOUNDED, STATUS_CLEAR, STATUS_UNDER_SEARCHED)


# Phrases that assert priority. Each is only defensible behind a CLEAR
# assessment; behind anything else it is an overclaim to cut before publication.
BANNED_PHRASES: dict[str, str] = {
    r"\bfirst\b": "priority claim ('first')",
    r"\bnovel\b": "novelty claim ('novel')",
    r"\bnew(?:ly)?\s+(?:method|approach|technique|framework|algorithm)\b": "novelty claim ('new X')",
    r"\bwe\s+introduce\b": "priority claim ('we introduce')",
    r"\bwe\s+are\s+the\s+first\b": "priority claim ('we are the first')",
    r"\bunprecedented\b": "priority claim ('unprecedented')",
    r"\bno\s+(?:prior|previous|existing)\s+work\b": "absence claim ('no prior work')",
    r"\bhas\s+never\s+been\b": "absence claim ('has never been')",
    r"\bstate[- ]of[- ]the[- ]art\b": "comparative claim ('state of the art')",
    r"\bbest\s+known\b": "comparative claim ('best known')",
}


@dataclass(frozen=True)
class Overclaim:
    phrase: str
    reason: str

    def __str__(self) -> str:
        return f"{self.phrase!r} -- {self.reason}"


def scan_overclaims(text: str) -> list[Overclaim]:
    """Find priority/novelty language that a search must earn the right to use."""
    found: list[Overclaim] = []
    for pattern, reason in BANNED_PHRASES.items():
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            found.append(Overclaim(phrase=match.group(0), reason=reason))
    return found


# --------------------------------------------------------------------------
# The objects.
# --------------------------------------------------------------------------


@dataclass
class Claim:
    """One separately attackable contribution.

    Decomposition matters: "our method is new" cannot be searched, while "using
    a diagonal enumeration order to surface minimal counterexamples in
    multivariate predicate search" can. A claim that cannot be attacked on its
    own is not a claim, it is a summary.
    """

    id: str
    statement: str
    kind: str = "CONTRIBUTION"
    novelty_basis: str = ""
    known_prior_art: list[str] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    adjacent_fields: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            raise PriorArtError("claim requires an id")
        if not self.statement.strip():
            raise PriorArtError(f"claim {self.id!r} requires a statement")

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> "Claim":
        if not isinstance(spec, dict):
            raise PriorArtError(f"claim spec must be a mapping, got {spec!r}")
        return cls(
            id=str(spec.get("id") or spec.get("slug") or ""),
            statement=str(spec.get("statement", "")),
            kind=str(spec.get("kind", "CONTRIBUTION")).upper(),
            novelty_basis=str(spec.get("novelty_basis", "")),
            known_prior_art=[str(x) for x in (spec.get("known_prior_art") or [])],
            search_terms=[str(x) for x in (spec.get("search_terms") or [])],
            adjacent_fields=[str(x) for x in (spec.get("adjacent_fields") or [])],
        )

    def overclaims(self) -> list[Overclaim]:
        return scan_overclaims(self.statement)


@dataclass
class Threat:
    """A piece of prior art aimed at a specific claim."""

    claim_id: str
    verdict: str
    source: str
    locator: str = ""
    evidence: str = ""
    angle: str = ""
    pass_id: str = ""

    def __post_init__(self) -> None:
        self.verdict = str(self.verdict).upper()
        if self.verdict not in VERDICTS:
            raise PriorArtError(
                f"threat against {self.claim_id!r}: verdict must be one of {list(VERDICTS)}, "
                f"got {self.verdict!r}"
            )
        self.angle = str(self.angle).upper() if self.angle else ""

    @property
    def severity(self) -> int:
        return _SEVERITY[self.verdict]

    def describe(self) -> str:
        where = f" ({self.locator})" if self.locator else ""
        return f"[{self.verdict}] {self.source}{where}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "verdict": self.verdict,
            "source": self.source,
            "locator": self.locator,
            "evidence": self.evidence,
            "angle": self.angle,
            "pass_id": self.pass_id,
        }


@dataclass
class SearchQuery:
    """One query actually issued.

    `results` is the load-bearing field: a query that returned nothing is the
    evidence behind a CLEAR verdict, and there is no way to earn CLEAR without
    logging some.
    """

    text: str
    angle: str = ""
    engine: str = ""
    results: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        self.angle = str(self.angle).upper() if self.angle else ""
        if self.angle and self.angle not in ANGLES:
            raise PriorArtError(f"query {self.text!r}: unknown angle {self.angle!r}; expected one of {list(ANGLES)}")

    @property
    def is_negative(self) -> bool:
        return self.results == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "angle": self.angle,
            "engine": self.engine,
            "results": self.results,
            "notes": self.notes,
        }


@dataclass
class SearchPass:
    """One independent sweep of the literature.

    Two passes must differ in phrasing or engine to count as independent; that
    is checked by `assess_claims`, not assumed.
    """

    id: str
    phrasing: str = ""
    engine: str = ""
    queries: list[SearchQuery] = field(default_factory=list)
    threats: list[Threat] = field(default_factory=list)
    notes: str = ""

    def angles_covered(self) -> set[str]:
        return {q.angle for q in self.queries if q.angle}

    def negative_queries(self) -> list[SearchQuery]:
        return [q for q in self.queries if q.is_negative]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "phrasing": self.phrasing,
            "engine": self.engine,
            "queries": [q.as_dict() for q in self.queries],
            "threats": [t.as_dict() for t in self.threats],
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PriorArtPolicy:
    """What a search has to do before its silence counts as evidence."""

    min_passes: int = 2
    required_angles: frozenset[str] = REQUIRED_ANGLES
    min_negative_queries: int = 3
    require_distinct_phrasing: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PriorArtPolicy":
        data = data or {}
        angles = data.get("required_angles")
        if angles:
            unknown = {str(a).upper() for a in angles} - set(ANGLES)
            if unknown:
                raise PriorArtError(f"unknown search angle(s) {sorted(unknown)}; expected {list(ANGLES)}")
            required = frozenset(str(a).upper() for a in angles)
        else:
            required = REQUIRED_ANGLES
        return cls(
            min_passes=int(data.get("min_passes", 2)),
            required_angles=required,
            min_negative_queries=int(data.get("min_negative_queries", 3)),
            require_distinct_phrasing=bool(data.get("require_distinct_phrasing", True)),
        )


@dataclass
class ClaimAssessment:
    """The verdict on one claim, and why."""

    claim_id: str
    statement: str
    status: str
    threats: list[Threat] = field(default_factory=list)
    passes_searched: int = 0
    angles_covered: set[str] = field(default_factory=set)
    missing_angles: set[str] = field(default_factory=set)
    negative_queries: int = 0
    reasons: list[str] = field(default_factory=list)
    overclaims: list[Overclaim] = field(default_factory=list)
    surgery_required: bool = False

    @property
    def worst_threat(self) -> Threat | None:
        return max(self.threats, key=lambda t: t.severity, default=None)

    def killers(self) -> list[Threat]:
        return [t for t in self.threats if t.verdict == VERDICT_KILLS]

    def wounds(self) -> list[Threat]:
        return [t for t in self.threats if t.verdict == VERDICT_WOUNDS]

    def must_cite(self) -> list[Threat]:
        """Adjacent work has to be cited and distinguished even when it costs nothing."""
        return [t for t in self.threats if t.verdict in {VERDICT_ADJACENT, VERDICT_WOUNDS, VERDICT_KILLS}]

    def blocks_publication(self) -> bool:
        """True when this claim cannot be stated as written."""
        return self.status in {STATUS_KILLED, STATUS_WOUNDED} or bool(self.unearned_overclaims())

    def unearned_overclaims(self) -> list[Overclaim]:
        """Priority language not backed by a CLEAR verdict."""
        return [] if self.status == STATUS_CLEAR else list(self.overclaims)

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "status": self.status,
            "threats": [t.as_dict() for t in self.threats],
            "passes_searched": self.passes_searched,
            "angles_covered": sorted(self.angles_covered),
            "missing_angles": sorted(self.missing_angles),
            "negative_queries": self.negative_queries,
            "reasons": list(self.reasons),
            "overclaims": [str(o) for o in self.overclaims],
            "unearned_overclaims": [str(o) for o in self.unearned_overclaims()],
            "surgery_required": self.surgery_required,
        }


# --------------------------------------------------------------------------
# Assessment.
# --------------------------------------------------------------------------


def assess_claims(
    claims: Sequence[Claim],
    passes: Sequence[SearchPass],
    policy: PriorArtPolicy | None = None,
) -> list[ClaimAssessment]:
    """Union the passes and decide each claim's status.

    Threats are unioned across every pass -- a threat found by one pass counts
    even if the others missed it, which is the entire reason for running more
    than one. The discipline checks apply only when nothing was found, because
    a killer is evidence however it was discovered, while silence is evidence
    only when the search was thorough.
    """
    policy = policy or PriorArtPolicy()
    independent = _independent_passes(passes, policy)

    assessments: list[ClaimAssessment] = []
    for claim in claims:
        threats = _dedupe_threats(t for p in passes for t in p.threats if t.claim_id == claim.id)
        angles = {q.angle for p in passes for q in p.queries if q.angle and _query_targets(q, claim)}
        negatives = sum(1 for p in passes for q in p.queries if q.is_negative and _query_targets(q, claim))

        assessment = ClaimAssessment(
            claim_id=claim.id,
            statement=claim.statement,
            status=STATUS_CLEAR,
            threats=sorted(threats, key=lambda t: -t.severity),
            passes_searched=independent,
            angles_covered=angles,
            missing_angles=set(policy.required_angles) - angles,
            negative_queries=negatives,
            overclaims=claim.overclaims(),
        )

        killers = assessment.killers()
        wounds = assessment.wounds()
        if killers:
            assessment.status = STATUS_KILLED
            assessment.surgery_required = True
            assessment.reasons.append(
                f"{len(killers)} source(s) already report this claim: "
                + "; ".join(t.describe() for t in killers[:3])
            )
        elif wounds:
            assessment.status = STATUS_WOUNDED
            assessment.surgery_required = True
            assessment.reasons.append(
                f"{len(wounds)} source(s) force this claim to be narrowed: "
                + "; ".join(t.describe() for t in wounds[:3])
            )
        else:
            # Nothing found. Now the quality of the search is what is on trial.
            shortfalls: list[str] = []
            if independent < policy.min_passes:
                shortfalls.append(
                    f"only {independent} independent search pass(es); {policy.min_passes} required "
                    "(a single search reliably misses severe threats)"
                )
            if assessment.missing_angles:
                shortfalls.append(
                    "no queries logged for angle(s): " + ", ".join(sorted(assessment.missing_angles))
                )
            if negatives < policy.min_negative_queries:
                shortfalls.append(
                    f"only {negatives} logged negative search(es); {policy.min_negative_queries} required "
                    "(an unlogged clear verdict is an opinion)"
                )
            if shortfalls:
                assessment.status = STATUS_UNDER_SEARCHED
                assessment.reasons.extend(shortfalls)
            else:
                assessment.reasons.append(
                    f"{independent} independent passes covering {len(angles)} angle(s) with "
                    f"{negatives} logged negative searches found no KILLS or WOUNDS"
                )

        if assessment.unearned_overclaims():
            assessment.surgery_required = True
            assessment.reasons.append(
                "claim uses priority language not backed by a CLEAR verdict: "
                + "; ".join(str(o) for o in assessment.unearned_overclaims())
            )
        assessments.append(assessment)

    return assessments


def _independent_passes(passes: Sequence[SearchPass], policy: PriorArtPolicy) -> int:
    """Count passes that genuinely differ.

    Re-running the same phrasing twice is one search, not two, and counting it
    as two is the easiest way to fake compliance with the union rule.
    """
    if not policy.require_distinct_phrasing:
        return len(passes)
    seen: set[tuple[str, str]] = set()
    for p in passes:
        key = (p.phrasing.strip().lower(), p.engine.strip().lower())
        if key == ("", ""):
            key = (p.id.strip().lower(), "")
        seen.add(key)
    return len(seen)


def _dedupe_threats(threats: Iterable[Threat]) -> list[Threat]:
    """The same citation found by two passes is one threat, at its worst verdict."""
    best: dict[tuple[str, str], Threat] = {}
    for threat in threats:
        key = (threat.source.strip().lower(), threat.locator.strip().lower())
        current = best.get(key)
        if current is None or threat.severity > current.severity:
            best[key] = threat
    return list(best.values())


def _query_targets(query: SearchQuery, claim: Claim) -> bool:
    """Whether a logged query counts towards this claim's coverage.

    Queries may be tagged with a claim id in `notes`; untagged queries count for
    every claim, which is the lenient reading. Being stricter would make the
    common case (one sweep covering the whole project) impossible to satisfy.
    """
    tag = f"claim:{claim.id}"
    if "claim:" in (query.notes or ""):
        return tag in query.notes
    return True


def load_claims(specs: Sequence[dict[str, Any]] | None) -> list[Claim]:
    claims = [Claim.from_dict(spec) for spec in specs or []]
    ids = [c.id for c in claims]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise PriorArtError(f"duplicate claim ids: {sorted(duplicates)}")
    return claims
