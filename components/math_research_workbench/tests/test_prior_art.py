"""Tests for the prior-art track.

The rules being pinned here are the ones that make a search result mean
something: union over independent passes, angle coverage, negative searches as
evidence, and the asymmetry between finding a killer and finding nothing.
"""

from __future__ import annotations

import pytest

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
    PriorArtError,
    PriorArtPolicy,
    SearchPass,
    SearchQuery,
    Threat,
    assess_claims,
    load_claims,
    scan_overclaims,
)
from math_workbench.tools.recon import (
    extract_queries,
    extract_threats,
    parse_search_pass,
    render_claims_file,
    render_report,
)

CLAIM_A = {"id": "a", "statement": "A thing we did."}
CLAIM_B = {"id": "b", "statement": "Another thing we did."}


def full_queries(pass_id: str, results: int = 0) -> list[SearchQuery]:
    """One logged query per angle, negative by default."""
    return [SearchQuery(text=f"{pass_id}-{a}", angle=a, results=results) for a in ANGLES]


def thorough(pass_id: str, phrasing: str, threats: list[Threat] | None = None) -> SearchPass:
    return SearchPass(id=pass_id, phrasing=phrasing, queries=full_queries(pass_id), threats=threats or [])


# --------------------------------------------------------------------------
# The union rule.
# --------------------------------------------------------------------------


def test_a_single_pass_cannot_earn_a_clear_verdict():
    """A single search reliably misses severe threats, so silence from one is not evidence."""
    claims = load_claims([CLAIM_A])
    [result] = assess_claims(claims, [thorough("p1", "first phrasing")])
    assert result.status == STATUS_UNDER_SEARCHED
    assert any("independent search pass" in r for r in result.reasons)


def test_two_independent_passes_can_earn_clear():
    claims = load_claims([CLAIM_A])
    [result] = assess_claims(claims, [thorough("p1", "first"), thorough("p2", "second")])
    assert result.status == STATUS_CLEAR


def test_rerunning_the_same_phrasing_counts_as_one_pass():
    """Otherwise the union rule is satisfied by running the same query twice."""
    claims = load_claims([CLAIM_A])
    [result] = assess_claims(claims, [thorough("p1", "same words"), thorough("p2", "same words")])
    assert result.status == STATUS_UNDER_SEARCHED


def test_a_threat_found_by_only_one_pass_still_counts():
    """The union is the whole reason for running more than one pass."""
    claims = load_claims([CLAIM_A])
    found = Threat(claim_id="a", verdict=VERDICT_KILLS, source="Someone (2001)")
    passes = [thorough("p1", "first"), thorough("p2", "second", [found])]
    [result] = assess_claims(claims, passes)
    assert result.status == STATUS_KILLED


def test_the_same_source_found_twice_is_one_threat_at_its_worst_verdict():
    claims = load_claims([CLAIM_A])
    mild = Threat(claim_id="a", verdict=VERDICT_ADJACENT, source="Someone (2001)", locator="p.4")
    severe = Threat(claim_id="a", verdict=VERDICT_WOUNDS, source="someone (2001)", locator="P.4")
    [result] = assess_claims(claims, [thorough("p1", "x", [mild]), thorough("p2", "y", [severe])])
    assert len(result.threats) == 1
    assert result.threats[0].verdict == VERDICT_WOUNDS
    assert result.status == STATUS_WOUNDED


# --------------------------------------------------------------------------
# The asymmetry: killers count regardless, silence has to be earned.
# --------------------------------------------------------------------------


def test_a_killer_found_by_a_sloppy_search_still_kills():
    """Finding a citation is evidence however badly you looked."""
    claims = load_claims([CLAIM_A])
    sloppy = SearchPass(id="p1", phrasing="one query", queries=[], threats=[
        Threat(claim_id="a", verdict=VERDICT_KILLS, source="Someone (2001)")
    ])
    [result] = assess_claims(claims, [sloppy])
    assert result.status == STATUS_KILLED
    assert result.surgery_required


def test_missing_angles_block_a_clear_verdict_and_are_named():
    claims = load_claims([CLAIM_A])
    partial = [
        SearchPass(id=p, phrasing=p, queries=[SearchQuery(text="q", angle="MECHANISM", results=0)] * 3)
        for p in ("p1", "p2")
    ]
    [result] = assess_claims(claims, partial)
    assert result.status == STATUS_UNDER_SEARCHED
    assert result.missing_angles == {"SYNONYM", "APPLICATION", "ADJACENT_FIELD"}
    assert any("ADJACENT_FIELD" in r for r in result.reasons)


def test_a_clear_verdict_requires_logged_negative_searches():
    """An unlogged clear verdict is an opinion."""
    claims = load_claims([CLAIM_A])
    all_hits = [
        SearchPass(id=p, phrasing=p, queries=full_queries(p, results=5)) for p in ("p1", "p2")
    ]
    [result] = assess_claims(claims, all_hits)
    assert result.status == STATUS_UNDER_SEARCHED
    assert any("negative search" in r for r in result.reasons)


def test_policy_thresholds_are_configurable():
    claims = load_claims([CLAIM_A])
    lenient = PriorArtPolicy.from_dict({"min_passes": 1, "min_negative_queries": 1, "required_angles": ["MECHANISM"]})
    one = SearchPass(id="p1", phrasing="p1", queries=[SearchQuery(text="q", angle="MECHANISM", results=0)])
    [result] = assess_claims(claims, [one], lenient)
    assert result.status == STATUS_CLEAR


def test_an_unknown_required_angle_is_rejected():
    with pytest.raises(PriorArtError, match="unknown search angle"):
        PriorArtPolicy.from_dict({"required_angles": ["VIBES"]})


# --------------------------------------------------------------------------
# Overclaims.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "We are the first to do this.",
        "A novel approach to the problem.",
        "This is a new method for counting.",
        "We introduce a technique for bounding.",
        "No prior work addresses this case.",
        "Our result is state-of-the-art.",
        "This is the best known bound.",
    ],
)
def test_priority_language_is_detected(statement):
    assert scan_overclaims(statement)


def test_ordinary_statements_are_not_flagged():
    assert scan_overclaims("We bound the divisor sum by an explicit constant.") == []


def test_priority_language_is_unearned_until_the_claim_is_clear():
    claims = load_claims([{"id": "a", "statement": "We are the first to enumerate diagonally."}])
    [under] = assess_claims(claims, [thorough("p1", "only one")])
    assert under.status == STATUS_UNDER_SEARCHED
    assert under.unearned_overclaims()
    assert under.surgery_required, "an unearned priority claim needs surgery even with no threats"
    assert under.blocks_publication()


def test_priority_language_is_allowed_once_the_claim_is_clear():
    claims = load_claims([{"id": "a", "statement": "We are the first to enumerate diagonally."}])
    [clear] = assess_claims(claims, [thorough("p1", "first"), thorough("p2", "second")])
    assert clear.status == STATUS_CLEAR
    assert clear.unearned_overclaims() == []
    assert not clear.blocks_publication()


# --------------------------------------------------------------------------
# Parsing model output.
# --------------------------------------------------------------------------


def test_threat_and_search_blocks_are_extracted():
    text = """
    Some commentary that should be ignored.
    ```search
    {"pass":"p1","angle":"MECHANISM","query":"foo","results":0}
    ```
    ```threat
    {"claim":"a","verdict":"KILLS","source":"Someone (2001)","locator":"Thm 1"}
    ```
    """
    claims = load_claims([CLAIM_A])
    threats, problems = extract_threats(text, claims)
    queries, _ = extract_queries(text)
    assert len(threats) == 1 and threats[0].verdict == VERDICT_KILLS
    assert len(queries) == 1 and queries[0].is_negative
    assert problems == []


def test_a_threat_with_no_claim_id_lands_on_every_claim():
    text = '```threat\n{"verdict":"ADJACENT","source":"Someone (2001)"}\n```'
    threats, _ = extract_threats(text, load_claims([CLAIM_A, CLAIM_B]))
    assert {t.claim_id for t in threats} == {"a", "b"}


def test_unusable_blocks_are_reported_rather_than_dropped():
    """A pass emitting three broken blocks must not look like one that found nothing."""
    claims = load_claims([CLAIM_A])
    text = """
    ```threat
    {"claim":"a","verdict":"MAYBE","source":"Someone (2001)"}
    ```
    ```threat
    {"claim":"nonexistent","verdict":"KILLS","source":"Other (2002)"}
    ```
    ```threat
    {"claim":"a","verdict":"KILLS"}
    ```
    """
    threats, problems = extract_threats(text, claims)
    assert threats == []
    assert len(problems) == 3
    assert any("nonexistent" in p for p in problems)
    assert any("no source" in p for p in problems)


def test_malformed_json_is_skipped_without_raising():
    threats, problems = extract_threats("```threat\nnot json\n```", load_claims([CLAIM_A]))
    assert threats == [] and problems == []


def test_non_numeric_result_counts_are_not_treated_as_negative_searches():
    """Otherwise a garbled result count silently becomes evidence of absence."""
    queries, problems = extract_queries('```search\n{"query":"foo","results":"none"}\n```')
    assert queries[0].results == 1
    assert not queries[0].is_negative
    assert any("non-numeric" in p for p in problems)


def test_parse_search_pass_builds_a_usable_pass():
    text = """
    ```search
    {"angle":"SYNONYM","query":"foo","results":0}
    ```
    ```threat
    {"claim":"a","verdict":"WOUNDS","source":"Someone (2001)"}
    ```
    """
    sweep, problems = parse_search_pass(text, load_claims([CLAIM_A]), pass_id="p1", phrasing="alt")
    assert sweep.id == "p1" and sweep.phrasing == "alt"
    assert sweep.angles_covered() == {"SYNONYM"}
    assert len(sweep.negative_queries()) == 1
    assert problems == []


# --------------------------------------------------------------------------
# Specs and reporting.
# --------------------------------------------------------------------------


def test_duplicate_claim_ids_are_rejected():
    with pytest.raises(PriorArtError, match="duplicate"):
        load_claims([CLAIM_A, dict(CLAIM_A)])


def test_a_claim_without_a_statement_is_rejected():
    with pytest.raises(PriorArtError, match="requires a statement"):
        Claim.from_dict({"id": "a", "statement": "   "})


def test_an_unknown_threat_verdict_is_rejected():
    with pytest.raises(PriorArtError, match="verdict must be one of"):
        Threat(claim_id="a", verdict="PROBABLY", source="x")


def test_report_explains_what_is_missing_for_under_searched_claims():
    claims = load_claims([CLAIM_A])
    report = render_report(assess_claims(claims, [thorough("p1", "one")]))
    assert "Verdict not yet earned" in report
    assert "finding nothing is evidence only if you looked properly" in report


def test_report_with_no_claims_explains_how_to_declare_one():
    assert "Add a `claims:` block" in render_report([])


def test_claims_file_separates_defensible_from_damaged():
    claims = load_claims([CLAIM_A, {"id": "b", "statement": "We are the first at this."}])
    killed = Threat(claim_id="a", verdict=VERDICT_KILLS, source="Someone (2001)")
    text = render_claims_file(
        assess_claims(claims, [thorough("p1", "one", [killed]), thorough("p2", "two")])
    )
    assert "## Defensible as written" in text
    assert "## Requires surgery before use" in text
    assert "Supersede this file" in text
    assert "**b**" in text.split("## Requires surgery")[0], "clean claim belongs in the defensible section"
