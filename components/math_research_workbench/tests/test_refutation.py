"""Tests for the counterexample search, its honesty rules, and witness checking."""

from __future__ import annotations

import itertools

import pytest

from math_workbench.conjecture import ALLOWED_FUNCTIONS, Conjecture
from math_workbench.tools.refutation import (
    CONTESTED,
    REJECTED,
    SOURCE_LLM,
    STATUS_CONTESTED,
    STATUS_FALSIFIED,
    STATUS_OPEN,
    STATUS_VERIFIED_EXHAUSTIVE,
    UNCHECKED,
    VERIFIED_EXACT,
    SearchBudget,
    check_claimed_witnesses,
    extract_claimed_witnesses,
    render_report,
    search_conjecture,
    shell_indices,
    verify_witness,
)


def make(predicate: str, low: int = 0, high: int = 50, **kwargs) -> Conjecture:
    return Conjecture.from_dict(
        {
            "id": kwargs.pop("id", "c"),
            "statement": kwargs.pop("statement", "test conjecture"),
            "predicate": predicate,
            "variables": kwargs.pop("variables", {"n": {"kind": "integers", "low": low, "high": high}}),
            **kwargs,
        }
    )


# --------------------------------------------------------------------------
# Enumeration order.
# --------------------------------------------------------------------------


def test_shell_enumeration_is_ordered_by_increasing_index_sum():
    order = list(shell_indices([3, 3]))
    sums = [sum(idx) for idx in order]
    assert sums == sorted(sums)
    assert len(order) == 9 and len(set(order)) == 9


def test_shell_enumeration_reaches_the_second_variable_under_a_small_budget():
    """The reason enumeration is diagonal rather than lexicographic.

    `itertools.product` over two large ranges spends its whole budget on the
    first variable, so a counterexample needing both variables to move is
    unreachable.
    """
    budget = 20
    shell = list(shell_indices([10_000, 10_000], limit=budget))
    product = list(itertools.islice(itertools.product(range(10_000), range(10_000)), budget))

    assert max(idx[0] for idx in shell) > 0, "diagonal search must vary the first variable"
    assert max(idx[1] for idx in shell) > 0, "diagonal search must vary the second variable"
    assert max(idx[0] for idx in product) == 0, "lexicographic search never moves the first variable"


def test_two_variable_counterexample_is_found_almost_immediately():
    variables = {"m": {"kind": "integers", "low": 1, "high": 500}, "n": {"kind": "integers", "low": 1, "high": 500}}
    c = make("divisor_count(m*n) == divisor_count(m)*divisor_count(n)", variables=variables, id="dc")
    outcome = search_conjecture(c, SearchBudget(max_evaluations=100))
    assert outcome.status == STATUS_FALSIFIED
    assert outcome.witnesses[0].assignment == {"m": 2, "n": 2}
    assert outcome.evaluated < 100


def test_first_witness_is_marked_minimal_in_search_order():
    outcome = search_conjecture(make("is_prime(n*n + n + 41)"))
    assert outcome.witnesses[0].assignment == {"n": 40}
    assert outcome.witnesses[0].minimal is True
    assert all(not w.minimal for w in outcome.witnesses[1:])


# --------------------------------------------------------------------------
# What each status is allowed to mean.
# --------------------------------------------------------------------------


def test_exhausting_a_finite_space_reports_verified_exhaustive():
    outcome = search_conjecture(make("totient(n) % 2 == 0", low=3, high=200))
    assert outcome.status == STATUS_VERIFIED_EXHAUSTIVE
    assert outcome.exhausted and outcome.evaluated == outcome.space_size


def test_running_out_of_budget_reports_open_not_verified():
    """A truncated search proves nothing and must not claim otherwise."""
    outcome = search_conjecture(make("totient(n) % 2 == 0", low=3, high=5000), SearchBudget(max_evaluations=50))
    assert outcome.status == STATUS_OPEN
    assert not outcome.exhausted
    assert outcome.evaluated == 50


def test_exhaustive_verification_is_withheld_when_some_points_failed_to_evaluate():
    """Covering the space is not enough; the coverage has to have worked."""
    c = make("2**(2**n) > 0", low=39, high=41)
    outcome = search_conjecture(c)
    assert outcome.errors > 0
    assert outcome.status != STATUS_VERIFIED_EXHAUSTIVE
    assert "not claimed" in outcome.notes


def test_contested_evaluations_outrank_witnesses_found_in_the_same_search(monkeypatch):
    """A buggy evaluator taints every verdict it produced, including the good-looking ones.

    Here `is_prime` is sabotaged to always return False. The search over
    n in [2, 10] genuinely does contain composite values, so it finds real
    witnesses -- but it also finds disagreements at the primes. Reporting
    FALSIFIED and dropping the disagreement would ship a result derived partly
    from an evaluator known to be wrong.
    """
    monkeypatch.setitem(
        ALLOWED_FUNCTIONS, "is_prime", (lambda n: False, ALLOWED_FUNCTIONS["is_prime"][1], (1, 1))
    )
    outcome = search_conjecture(make("is_prime(n)", low=2, high=10))
    assert outcome.contested, "the disagreement must be recorded, not swallowed"
    assert outcome.witnesses, "this search does find genuine witnesses at the composites"
    assert outcome.status == STATUS_CONTESTED, "the disagreement must dominate the status"
    assert "not counted as refutations" in outcome.notes


def test_contested_status_is_reported_even_with_no_witnesses(monkeypatch):
    monkeypatch.setitem(
        ALLOWED_FUNCTIONS, "is_prime", (lambda n: False, ALLOWED_FUNCTIONS["is_prime"][1], (1, 1))
    )
    outcome = search_conjecture(make("is_prime(p)", variables={"p": {"kind": "primes", "low": 2, "high": 30}}))
    assert outcome.status == STATUS_CONTESTED
    assert outcome.witnesses == []


def test_assumption_failures_are_counted_not_treated_as_witnesses():
    c = make("n % 2 == 0", low=1, high=20, assumptions=["n % 2 == 0"])
    outcome = search_conjecture(c)
    assert outcome.status == STATUS_VERIFIED_EXHAUSTIVE
    assert outcome.assumption_skips == 10


def test_random_sampling_is_deterministic_under_a_fixed_seed():
    c = make("n < 10**9", low=1, high=10**6)
    budget = SearchBudget(max_evaluations=10, random_samples=50, seed=99)
    first = search_conjecture(c, budget)
    second = search_conjecture(c, budget)
    assert first.evaluated == second.evaluated


# --------------------------------------------------------------------------
# Witnesses claimed by a model.
# --------------------------------------------------------------------------


def test_extracts_witness_blocks_and_ignores_ordinary_prose():
    text = """
    I think the claim fails somewhere around n = 40, probably.
    ```witness
    {"conjecture": "c", "assignment": {"n": 40}, "rationale": "41 divides it"}
    ```
    ```json
    {"unrelated": "config blob"}
    ```
    """
    claims = extract_claimed_witnesses(text)
    assert len(claims) == 1
    assert claims[0]["assignment"] == {"n": 40}


def test_a_witness_list_in_one_block_is_accepted():
    text = '```witness\n[{"assignment": {"n": 40}}, {"assignment": {"n": 41}}]\n```'
    assert len(extract_claimed_witnesses(text)) == 2


def test_malformed_witness_blocks_are_skipped_without_raising():
    assert extract_claimed_witnesses("```witness\nnot json at all\n```") == []
    assert extract_claimed_witnesses("") == []


def test_a_wrong_claimed_witness_is_rejected_not_recorded():
    """The central guard: an LLM asserting a counterexample does not make one."""
    c = make("is_prime(n*n + n + 41)")
    text = """
    ```witness
    {"conjecture": "c", "assignment": {"n": 7}, "rationale": "I am confident 97 is composite"}
    ```
    ```witness
    {"conjecture": "c", "assignment": {"n": 40}, "rationale": "41 divides 1681"}
    ```
    """
    checked = check_claimed_witnesses([c], text, source=SOURCE_LLM)
    by_n = {w.assignment["n"]: w for w in checked}
    assert by_n[7].verification == REJECTED
    assert not by_n[7].refutes()
    assert by_n[40].verification == VERIFIED_EXACT
    assert by_n[40].refutes()


def test_claimed_witness_naming_an_unknown_conjecture_is_still_checked():
    c = make("is_prime(n*n + n + 41)")
    text = '```witness\n{"conjecture": "typo-id", "assignment": {"n": 40}}\n```'
    checked = check_claimed_witnesses([c], text)
    assert len(checked) == 1
    assert checked[0].verification == VERIFIED_EXACT
    assert "not declared" in checked[0].rationale


def test_claimed_witness_with_the_wrong_variables_is_ignored():
    c = make("is_prime(n*n + n + 41)")
    assert check_claimed_witnesses([c], '```witness\n{"assignment": {"x": 40, "y": 1}}\n```') == []


def test_verify_witness_on_an_incomplete_assignment_is_unchecked_not_verified():
    c = make("m + n > 0", variables={"m": {"kind": "integers", "low": 1, "high": 5}, "n": {"kind": "integers", "low": 1, "high": 5}})
    witness = verify_witness(c, {"m": 1})
    assert witness.verification == UNCHECKED
    assert not witness.refutes()


# --------------------------------------------------------------------------
# Reporting.
# --------------------------------------------------------------------------


def test_report_states_the_limits_of_exhaustive_verification():
    outcome = search_conjecture(make("totient(n) % 2 == 0", low=3, high=50))
    report = render_report([outcome])
    assert "proof by exhaustion over that space only" in report
    assert "not a proof of the general statement" in report


def test_report_says_how_many_proposed_witnesses_were_discarded():
    c = make("is_prime(n*n + n + 41)")
    claimed = check_claimed_witnesses([c], '```witness\n{"assignment": {"n": 7}}\n```')
    report = render_report([], claimed)
    assert "did not survive independent checking" in report


def test_report_with_no_conjectures_explains_how_to_declare_one():
    assert "Add a `conjectures:` block" in render_report([])
