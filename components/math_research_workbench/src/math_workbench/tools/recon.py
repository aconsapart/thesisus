"""Turn a hostile prior-art search into structured, auditable findings.

The model does the searching; this parses what it returns and reports what the
search actually established. Same shape as `tools.refutation`: fenced blocks are
the actionable output, prose is commentary, and a claim of "nothing found" is
checked against the search log rather than taken at face value.

Blocks understood:

    ```threat
    {"claim": "c1", "verdict": "KILLS", "source": "Author (2019), Title",
     "locator": "Thm 3.2, arXiv:1234.5678", "evidence": "...", "angle": "SYNONYM"}
    ```

    ```search
    {"pass": "p1", "angle": "ADJACENT_FIELD", "query": "...",
     "engine": "...", "results": 0, "notes": "claim:c1"}
    ```

A search block with `"results": 0` is a *negative search*, and negative searches
are the only thing that can earn a CLEAR verdict.
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from math_workbench.prior_art import (
    ANGLES,
    STATUS_CLEAR,
    STATUS_KILLED,
    STATUS_UNDER_SEARCHED,
    STATUS_WOUNDED,
    VERDICT_ADJACENT,
    VERDICT_KILLS,
    VERDICT_WOUNDS,
    Claim,
    ClaimAssessment,
    PriorArtError,
    PriorArtPolicy,
    SearchPass,
    SearchQuery,
    Threat,
    assess_claims,
)

__all__ = [
    "extract_threats",
    "extract_queries",
    "parse_search_pass",
    "merge_passes",
    "render_report",
    "render_claims_file",
    "summarise_for_prompt",
]

_BLOCK = re.compile(r"```(?P<kind>threat|search)\s*\n(?P<body>.*?)```", re.DOTALL | re.IGNORECASE)


def _blocks(text: str, kind: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for match in _BLOCK.finditer(text or ""):
        if match.group("kind").lower() != kind:
            continue
        body = match.group("body").strip()
        if not body:
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        for item in payload if isinstance(payload, list) else [payload]:
            if isinstance(item, dict):
                out.append(item)
    return out


def extract_threats(text: str, claims: Sequence[Claim], pass_id: str = "") -> tuple[list[Threat], list[str]]:
    """Parse threat blocks. Returns the threats and any rejection reasons.

    A malformed threat is reported rather than dropped: a search pass that
    produced three unusable threat blocks looks identical to one that found
    nothing, and those are very different outcomes.
    """
    known = {c.id for c in claims}
    threats: list[Threat] = []
    problems: list[str] = []
    for item in _blocks(text, "threat"):
        claim_id = str(item.get("claim", item.get("claim_id", ""))).strip()
        source = str(item.get("source", "")).strip()
        if not source:
            problems.append(f"threat block with no source, ignored: {item!r}"[:200])
            continue
        if claim_id and claim_id not in known:
            problems.append(f"threat cites unknown claim id {claim_id!r} ({source}); not counted against any claim")
            continue
        targets = [claim_id] if claim_id else sorted(known)
        for target in targets:
            try:
                threats.append(
                    Threat(
                        claim_id=target,
                        verdict=str(item.get("verdict", VERDICT_ADJACENT)),
                        source=source,
                        locator=str(item.get("locator", "")),
                        evidence=str(item.get("evidence", "")),
                        angle=str(item.get("angle", "")),
                        pass_id=pass_id,
                    )
                )
            except PriorArtError as exc:
                problems.append(str(exc))
    return threats, problems


def extract_queries(text: str) -> tuple[list[SearchQuery], list[str]]:
    queries: list[SearchQuery] = []
    problems: list[str] = []
    for item in _blocks(text, "search"):
        query_text = str(item.get("query", item.get("text", ""))).strip()
        if not query_text:
            problems.append(f"search block with no query text, ignored: {item!r}"[:200])
            continue
        raw_results = item.get("results", 0)
        try:
            results = int(raw_results)
        except (TypeError, ValueError):
            problems.append(f"search block for {query_text!r} has non-numeric results {raw_results!r}; treated as 1")
            results = 1
        try:
            queries.append(
                SearchQuery(
                    text=query_text,
                    angle=str(item.get("angle", "")),
                    engine=str(item.get("engine", "")),
                    results=results,
                    notes=str(item.get("notes", "")),
                )
            )
        except PriorArtError as exc:
            problems.append(str(exc))
    return queries, problems


def parse_search_pass(
    text: str,
    claims: Sequence[Claim],
    pass_id: str,
    phrasing: str = "",
    engine: str = "",
) -> tuple[SearchPass, list[str]]:
    """Build one search pass from a model response."""
    threats, threat_problems = extract_threats(text, claims, pass_id=pass_id)
    queries, query_problems = extract_queries(text)
    sweep = SearchPass(
        id=pass_id,
        phrasing=phrasing,
        engine=engine,
        queries=queries,
        threats=threats,
    )
    return sweep, threat_problems + query_problems


def merge_passes(
    claims: Sequence[Claim],
    passes: Sequence[SearchPass],
    policy: PriorArtPolicy | None = None,
) -> list[ClaimAssessment]:
    return assess_claims(claims, passes, policy)


# --------------------------------------------------------------------------
# Reporting.
# --------------------------------------------------------------------------

_STATUS_ORDER = {STATUS_KILLED: 0, STATUS_WOUNDED: 1, STATUS_UNDER_SEARCHED: 2, STATUS_CLEAR: 3}


def render_report(
    assessments: Sequence[ClaimAssessment],
    passes: Sequence[SearchPass] = (),
    problems: Sequence[str] = (),
) -> str:
    """The threat table, the search log, and what has to change."""
    lines = ["# Prior-art threat table", ""]
    if not assessments:
        return "\n".join(
            lines
            + [
                "No claims were declared for this problem.",
                "",
                "Add a `claims:` block to the problem YAML listing each separately "
                "attackable contribution. A claim that cannot be attacked on its own "
                "is a summary, not a claim, and cannot be searched for.",
            ]
        )

    ordered = sorted(assessments, key=lambda a: (_STATUS_ORDER.get(a.status, 9), a.claim_id))
    killed = [a for a in ordered if a.status == STATUS_KILLED]
    wounded = [a for a in ordered if a.status == STATUS_WOUNDED]
    under = [a for a in ordered if a.status == STATUS_UNDER_SEARCHED]
    clear = [a for a in ordered if a.status == STATUS_CLEAR]

    lines += [
        "## Summary",
        "",
        f"- claims assessed: {len(ordered)}",
        f"- KILLED (already in the literature): {len(killed)}",
        f"- WOUNDED (must be narrowed): {len(wounded)}",
        f"- UNDER_SEARCHED (verdict not yet earned): {len(under)}",
        f"- CLEAR: {len(clear)}",
        "",
        "| Claim | Status | Worst threat | Passes | Angles | Negative searches |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for a in ordered:
        worst = a.worst_threat
        lines.append(
            f"| {a.claim_id} | {a.status} | {worst.describe() if worst else '--'} | "
            f"{a.passes_searched} | {len(a.angles_covered)}/{len(ANGLES)} | {a.negative_queries} |"
        )
    lines.append("")

    if killed or wounded:
        lines += [
            "## Claim surgery required",
            "",
            "These claims cannot be stated as written.",
            "",
        ]
        for a in killed + wounded:
            lines.append(f"### {a.claim_id} -- {a.status}")
            lines.append("")
            lines.append(a.statement)
            lines.append("")
            for threat in a.threats:
                if threat.verdict in {VERDICT_KILLS, VERDICT_WOUNDS}:
                    lines.append(f"- **{threat.verdict}**: {threat.describe()}")
                    if threat.evidence:
                        lines.append(f"  - {threat.evidence}")
            lines.append("")

    if under:
        lines += [
            "## Verdict not yet earned",
            "",
            "Nothing was found against these claims, but the search does not yet "
            "support saying so. Finding a killer is evidence however you looked; "
            "finding nothing is evidence only if you looked properly.",
            "",
        ]
        for a in under:
            lines.append(f"- **{a.claim_id}**")
            for reason in a.reasons:
                lines.append(f"  - {reason}")
        lines.append("")

    if clear:
        lines += ["## Clear", ""]
        for a in clear:
            lines.append(f"- **{a.claim_id}**: {a.reasons[0] if a.reasons else 'no threats found'}")
            citations = a.must_cite()
            if citations:
                lines.append(f"  - still must cite and distinguish: {'; '.join(t.describe() for t in citations)}")
        lines.append("")

    overclaimed = [a for a in ordered if a.unearned_overclaims()]
    if overclaimed:
        lines += [
            "## Banned overclaims",
            "",
            "Priority language that the search has not earned the right to use.",
            "",
        ]
        for a in overclaimed:
            for over in a.unearned_overclaims():
                lines.append(f"- {a.claim_id}: {over} (claim is {a.status})")
        lines.append("")

    if passes:
        lines += ["## Search log", ""]
        for sweep in passes:
            angles = ", ".join(sorted(sweep.angles_covered())) or "none tagged"
            lines.append(
                f"### {sweep.id}"
                + (f" -- {sweep.phrasing}" if sweep.phrasing else "")
                + (f" [{sweep.engine}]" if sweep.engine else "")
            )
            lines.append("")
            lines.append(f"{len(sweep.queries)} quer(ies), angles covered: {angles}")
            lines.append("")
            for query in sweep.queries:
                marker = "no results" if query.is_negative else f"{query.results} result(s)"
                tag = f" [{query.angle}]" if query.angle else ""
                lines.append(f"- `{query.text}`{tag} -- {marker}")
            lines.append("")

    if problems:
        lines += [
            "## Unusable output",
            "",
            "These blocks could not be used. A pass that emits unusable blocks "
            "looks the same as one that found nothing, so they are listed rather "
            "than dropped.",
            "",
        ]
        lines += [f"- {p}" for p in problems]
        lines.append("")
    return "\n".join(lines)


def render_claims_file(assessments: Sequence[ClaimAssessment]) -> str:
    """The maximally-defensible claim set, plus what was cut and why.

    Kept as a file rather than a report section because it is the thing you
    paste into a paper, and because superseding it in version control is how the
    history of what you were once willing to claim stays visible.
    """
    ordered = sorted(assessments, key=lambda a: (_STATUS_ORDER.get(a.status, 9), a.claim_id))
    lines = [
        "# Claims",
        "",
        "Generated from the prior-art threat table. Supersede this file; do not",
        "quietly edit it. What you were once willing to claim is part of the record.",
        "",
        "## Defensible as written",
        "",
    ]
    defensible = [a for a in ordered if a.status == STATUS_CLEAR]
    if defensible:
        for a in defensible:
            lines.append(f"- **{a.claim_id}**: {a.statement}")
            citations = a.must_cite()
            if citations:
                lines.append(f"  - cite and distinguish: {'; '.join(t.describe() for t in citations)}")
    else:
        lines.append("- (none yet -- every claim is killed, wounded, or under-searched)")
    lines += ["", "## Requires surgery before use", ""]
    needs = [a for a in ordered if a.surgery_required]
    if needs:
        for a in needs:
            lines.append(f"- **{a.claim_id}** ({a.status}): {a.statement}")
            for reason in a.reasons:
                lines.append(f"  - {reason}")
    else:
        lines.append("- (none)")
    lines += ["", "## Banned overclaims", ""]
    banned = [(a, o) for a in ordered for o in a.unearned_overclaims()]
    if banned:
        for a, over in banned:
            lines.append(f"- {a.claim_id}: {over} -- not backed by a CLEAR verdict")
    else:
        lines.append("- (none detected)")
    lines += ["", "## Threat table", "", "| Claim | Status | Sources |", "| --- | --- | --- |"]
    for a in ordered:
        sources = "; ".join(t.describe() for t in a.threats) or "--"
        lines.append(f"| {a.claim_id} | {a.status} | {sources} |")
    return "\n".join(lines) + "\n"


def summarise_for_prompt(assessments: Sequence[ClaimAssessment]) -> str:
    """Compact digest for feeding back into a later model call."""
    if not assessments:
        return "no claims declared, so no prior-art recon was run"
    parts = []
    for a in sorted(assessments, key=lambda x: _STATUS_ORDER.get(x.status, 9)):
        head = f"{a.claim_id}: {a.status}"
        worst = a.worst_threat
        if worst:
            head += f" -- worst: {worst.describe()}"
        elif a.status == STATUS_UNDER_SEARCHED:
            head += f" -- {a.reasons[0] if a.reasons else 'search incomplete'}"
        parts.append(head)
    return "\n".join(parts)
