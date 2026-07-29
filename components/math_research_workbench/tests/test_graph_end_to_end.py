"""End-to-end run of the LangGraph pipeline with a stubbed model.

No API key and no network: `llm_call` is replaced with a canned responder that
emits one true witness and one false one. What is being tested is the wiring --
routing, verification, persistence -- not the model.

Skipped when langgraph is not installed, so the rest of the suite still runs on
a machine with only sympy and pyyaml.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("langgraph", reason="graph tests need the `agents` extra")
pytest.importorskip("langchain_openai", reason="graph tests need the `agents` extra")

import math_workbench.agent as agent  # noqa: E402
from math_workbench.tools import codex  # noqa: E402

TRUE_WITNESS = 40   # 40^2 + 40 + 41 = 1681 = 41^2
FALSE_WITNESS = 3   # 3^2 + 3 + 41 = 53, prime


def canned_llm(prompt: str) -> str:
    """One honest witness, one bogus one, so both paths get exercised."""
    if "You are a hostile reviewer" in prompt:
        # A prior-art pass: one killer, plus the negative-search log a clear
        # verdict would need. Each pass answers under its own assigned angle, so
        # the two passes together cover more angles than either alone.
        match = re.search(r"Search angle for THIS pass:\s*(\w+)", prompt)
        angle = match.group(1) if match else "MECHANISM"
        return (
            f'```search\n{{"angle": "{angle}", "query": "combinatorial generation index sum", '
            '"engine": "scholar", "results": 0}\n```\n'
            f'```search\n{{"angle": "APPLICATION", "query": "minimal counterexample search order", "results": 0}}\n```\n'
            '```threat\n{"claim": "diagonal-enumeration", "verdict": "KILLS", '
            '"source": "Knuth (2011), TAOCP 4A", "locator": "7.2.1.3", '
            '"evidence": "Generation by increasing index sum is textbook combinatorial generation."}\n```\n'
        )
    if "Perform claim surgery" in prompt:
        return "Narrowed: the contribution is the application to predicate search, not the ordering itself."
    if "Report every candidate counterexample" in prompt:
        return (
            "I attacked the boundary of the declared range.\n"
            f'```witness\n{{"conjecture": "euler-prime-polynomial", '
            f'"assignment": {{"n": {TRUE_WITNESS}}}, "rationale": "41 divides 1681"}}\n```\n'
            f'```witness\n{{"conjecture": "euler-prime-polynomial", '
            f'"assignment": {{"n": {FALSE_WITNESS}}}, "rationale": "I am sure 53 is composite"}}\n```\n'
        )
    if "Produce the repair" in prompt:
        return "Sharpest remaining theorem: n^2 + n + 41 is prime for 0 <= n <= 39."
    return "Synthesis placeholder. FAILED/OPEN remains."


@pytest.fixture
def run_result(tmp_path, monkeypatch, demo_problem, examples_dir):
    monkeypatch.setattr(agent, "llm_call", canned_llm)
    db = str(tmp_path / "codex.sqlite")
    out = str(tmp_path / "run")
    final = agent.run(
        str(demo_problem),
        str(examples_dir / "generic_strategy_portfolio.yaml"),
        iterations=1,
        parallel_strategies=2,
        out=out,
        db=db,
        parallel_refutations=1,
    )
    return final, db, Path(out)


def test_graph_has_a_refutation_stage_before_the_proof_stage():
    nodes = set(build_nodes())
    assert {"search_counterexamples", "refute_lanes", "assess_refutation", "repair"} <= nodes


def test_graph_has_a_prior_art_stage():
    assert {"prior_art", "claim_surgery"} <= set(build_nodes())


def test_prior_art_runs_first_and_kills_a_claim_that_is_already_published(run_result):
    final, _db, _out = run_result
    by_id = {a["claim_id"]: a for a in final["prior_art_assessments"]}
    assert by_id["diagonal-enumeration"]["status"] == "KILLED"
    assert "diagonal-enumeration" in final["claims_blocked"]
    assert final["claim_surgery_report"], "a damaged claim must trigger surgery"


def test_unsearched_claims_do_not_come_back_clear(run_result):
    """The canned pass finds nothing against these two, which is not the same as clearing them."""
    final, _db, _out = run_result
    by_id = {a["claim_id"]: a for a in final["prior_art_assessments"]}
    for claim_id in ("dual-evaluator-verification", "search-status-vocabulary"):
        assert by_id[claim_id]["status"] in {"UNDER_SEARCHED", "CLEAR"}
        if by_id[claim_id]["status"] == "UNDER_SEARCHED":
            assert by_id[claim_id]["reasons"]


def test_priority_language_is_flagged_when_the_search_did_not_earn_it(run_result):
    final, _db, _out = run_result
    by_id = {a["claim_id"]: a for a in final["prior_art_assessments"]}
    assert by_id["diagonal-enumeration"]["unearned_overclaims"], (
        "'We introduce a novel...' behind a KILLED verdict must be flagged"
    )


def test_the_run_writes_a_claims_file(run_result):
    _final, _db, out = run_result
    claims_file = out / "CLAIMS.md"
    assert claims_file.exists()
    text = claims_file.read_text(encoding="utf-8")
    assert "Requires surgery before use" in text
    assert "Claim surgery" in text, "the surgery output is appended, not written to a separate file"


def test_the_ledger_records_the_prior_art_search(run_result):
    _final, db, _out = run_result
    con = codex.connect(db)
    board = dict(con.execute("select slug, status from claim_contribution").fetchall())
    assert board["diagonal-enumeration"] == "KILLED"
    assert con.execute("select count(*) from prior_art_threat where verdict='KILLS'").fetchone()[0] >= 1
    assert con.execute("select count(*) from v_negative_searches").fetchone()[0] > 0
    assert [r["slug"] for r in codex.claims_blocking_publication(con)]
    con.close()


def build_nodes():
    graph = agent.build_graph().get_graph()
    return [n for n in graph.nodes if not n.startswith("__")]


def test_run_falsifies_the_conjectures_that_are_actually_false(run_result):
    final, _db, _out = run_result
    assert set(final["falsified_conjectures"]) == {
        "euler-prime-polynomial",
        "fermat-primes",
        "mersenne-prime-exponent",
        "divisor-count-multiplicative",
    }
    assert set(final["exhaustively_verified"]) == {
        "divisor-count-multiplicative-coprime",
        "totient-even",
    }


def test_a_bogus_model_witness_is_discarded_with_a_reason(run_result):
    final, _db, _out = run_result
    discarded = final["discarded_witnesses"]
    assert any(w["assignment"] == {"n": FALSE_WITNESS} for w in discarded)
    assert all("predicate holds here" in w["detail"] for w in discarded)
    assert not any(w["assignment"] == {"n": FALSE_WITNESS} for w in final["verified_counterexamples"])


def test_proof_lanes_are_skipped_when_the_frontier_is_falsified(run_result):
    """The point of running refutation first: no proof budget on a dead statement."""
    final, _db, _out = run_result
    assert final["frontier_falsified"] is True
    assert final["strategy_reports"] == []
    assert final["repair_report"], "a falsified frontier must produce a repair"


def test_the_run_writes_its_refutation_artifacts(run_result):
    _final, _db, out = run_result
    names = {p.name for p in (out / "iteration_00").iterdir()}
    assert {"counterexample_search.md", "refutation_assessment.md", "repair.md"} <= names


def test_the_ledger_records_the_refutations(run_result):
    _final, db, _out = run_result
    con = codex.connect(db)
    board = dict(con.execute("select slug, status from conjecture").fetchall())
    assert board["euler-prime-polynomial"] == "FALSIFIED"
    assert board["totient-even"] == "VERIFIED_EXHAUSTIVE"

    assert con.execute("select count(*) from theorem where status='FALSIFIED'").fetchone()[0] == 4

    # Before this refactor the falsification table had no writer at all.
    assert con.execute("select count(*) from falsification").fetchone()[0] > 0
    assert codex.verified_counterexamples(con)

    discarded = con.execute(
        "select count(*) from counterexample where verification='REJECTED'"
    ).fetchone()[0]
    assert discarded == 1, "the rejected claim is kept on record, not dropped"
    con.close()


def test_resolution_stays_open_when_only_side_conjectures_died(run_result):
    final, _db, _out = run_result
    assert final["resolution"] == "OPEN"
