"""End-to-end run of the LangGraph pipeline with a stubbed model.

No API key and no network: `llm_call` is replaced with a canned responder that
emits one true witness and one false one. What is being tested is the wiring --
routing, verification, persistence -- not the model.

Skipped when langgraph is not installed, so the rest of the suite still runs on
a machine with only sympy and pyyaml.
"""

from __future__ import annotations

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
