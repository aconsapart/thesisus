"""End-to-end tests for the shipped examples and the standalone sweep.

These also pin the documented behaviour of the demo problem: if a claim listed
in its notes as false stops being reported as falsified, either the mathematics
or the machinery has changed, and both are worth failing a build over.
"""

from __future__ import annotations

import pytest
import yaml

from math_workbench.config import PROVE, REFUTE, ProblemSpec, StrategyPortfolio
from math_workbench.sweep import sweep


@pytest.fixture
def portfolio_path(examples_dir):
    return examples_dir / "generic_strategy_portfolio.yaml"


# --------------------------------------------------------------------------
# The shipped example, end to end.
# --------------------------------------------------------------------------


def test_demo_problem_sweep_reproduces_known_mathematics(demo_problem):
    result = sweep(str(demo_problem), quiet=True)

    assert set(result["falsified"]) == {
        "euler-prime-polynomial",
        "fermat-primes",
        "mersenne-prime-exponent",
        "divisor-count-multiplicative",
    }
    assert set(result["verified_exhaustive"]) == {
        "divisor-count-multiplicative-coprime",
        "totient-even",
    }
    assert result["contested"] == [], "an evaluator disagreement in the demo is a bug"


def test_demo_problem_finds_the_expected_minimal_witnesses(demo_problem):
    outcomes = {o["conjecture_id"]: o for o in sweep(str(demo_problem), quiet=True)["outcomes"]}

    def first(cid):
        return outcomes[cid]["witnesses"][0]["assignment"]

    assert first("euler-prime-polynomial") == {"n": 40}
    assert first("fermat-primes") == {"k": 5}, "Euler's 1732 refutation of Fermat's conjecture"
    assert first("mersenne-prime-exponent") == {"p": 11}, "2047 = 23 * 89"
    assert first("divisor-count-multiplicative") == {"m": 2, "n": 2}


def test_repairing_a_conjecture_changes_its_verdict(demo_problem):
    """The naive claim dies; the coprime-guarded repair survives the same space."""
    outcomes = {o["conjecture_id"]: o for o in sweep(str(demo_problem), quiet=True)["outcomes"]}
    naive = outcomes["divisor-count-multiplicative"]
    repaired = outcomes["divisor-count-multiplicative-coprime"]

    assert naive["status"] == "FALSIFIED"
    assert repaired["status"] == "VERIFIED_EXHAUSTIVE"
    assert naive["space_size"] == repaired["space_size"], "the repair is a hypothesis, not a smaller box"
    assert repaired["assumption_skips"] > 0


def test_sweep_persists_to_a_database(demo_problem, tmp_path):
    db = str(tmp_path / "codex.sqlite")
    sweep(str(demo_problem), db=db, quiet=True)

    from math_workbench.tools import codex

    con = codex.connect(db)
    board = dict(con.execute("select slug, status from conjecture").fetchall())
    assert board["fermat-primes"] == "FALSIFIED"
    assert board["totient-even"] == "VERIFIED_EXHAUSTIVE"
    assert codex.verified_counterexamples(con), "witnesses must be persisted, not just printed"
    con.close()


def test_sweep_writes_a_report_file(demo_problem, tmp_path):
    out = tmp_path / "report.md"
    sweep(str(demo_problem), out=str(out), quiet=True)
    text = out.read_text(encoding="utf-8")
    assert "# Counterexample search report" in text
    assert "fermat-primes -- FALSIFIED" in text


def test_generic_example_problem_still_parses(examples_dir):
    spec = ProblemSpec.from_yaml(str(examples_dir / "generic_number_theory_problem.yaml"))
    assert spec.build_conjectures(), "the generic example should demonstrate the conjecture schema"


# --------------------------------------------------------------------------
# Spec validation.
# --------------------------------------------------------------------------


def test_strategy_portfolio_declares_both_modes(portfolio_path):
    portfolio = StrategyPortfolio.from_yaml(str(portfolio_path))
    modes = {s.mode for s in portfolio.strategies}
    assert PROVE in modes and REFUTE in modes

    refuters = portfolio.top_by_mode(5, refuting=True)
    provers = portfolio.top_by_mode(5, refuting=False)
    assert refuters and provers
    assert all(s.refutes() for s in refuters)
    assert all(s.proves() for s in provers)


def test_every_refute_strategy_ships_counterexample_prompts(portfolio_path):
    portfolio = StrategyPortfolio.from_yaml(str(portfolio_path))
    for strategy in portfolio.strategies:
        if strategy.mode == REFUTE:
            assert strategy.counterexample_prompts, f"{strategy.id} has no counterexample prompts"


def test_an_invalid_strategy_mode_is_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        yaml.safe_dump({"strategies": [{"id": "s", "name": "S", "rank": 1, "description": "d", "mode": "GUESS"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="mode must be one of"):
        StrategyPortfolio.from_yaml(str(path))


def test_a_typo_in_a_problem_spec_key_is_caught_at_load(tmp_path):
    """A silently ignored `conjecture:` key would disable the whole track."""
    path = tmp_path / "typo.yaml"
    path.write_text(
        yaml.safe_dump({"slug": "s", "title": "T", "conjecture": [{"id": "c"}]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unknown problem-spec key"):
        ProblemSpec.from_yaml(str(path))


def test_a_typo_in_a_strategy_key_is_caught_at_load(tmp_path):
    path = tmp_path / "typo.yaml"
    path.write_text(
        yaml.safe_dump(
            {"strategies": [{"id": "s", "name": "S", "rank": 1, "description": "d", "counterexample_prompt": ["x"]}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown key"):
        StrategyPortfolio.from_yaml(str(path))


def test_search_budget_merges_machine_defaults_with_problem_overrides(demo_problem):
    from math_workbench.config import load_app_config

    spec = ProblemSpec.from_yaml(str(demo_problem))
    budget = load_app_config("/nonexistent.yaml").search_budget(spec.refutation)
    assert budget.max_evaluations == 4000, "the problem's override wins"
    assert budget.random_samples == 200
    assert budget.seed == 20240729, "unspecified fields fall back to the machine default"
