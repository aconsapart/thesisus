"""Tests for the executable conjecture model and its dual evaluator.

The claims checked here are ones mathematics already settled, so a failure means
the machinery is wrong rather than the mathematics being interesting.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from math_workbench.conjecture import (
    AGREEMENT_CONTESTED,
    AGREEMENT_DUAL_EXACT,
    AGREEMENT_SYMBOLIC_ONLY,
    ALLOWED_FUNCTIONS,
    Conjecture,
    ConjectureError,
    Domain,
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
# Known mathematics.
# --------------------------------------------------------------------------


def test_euler_polynomial_is_prime_below_40_and_fails_at_40():
    c = make("is_prime(n*n + n + 41)")
    for n in (0, 1, 5, 39):
        assert c.evaluate({"n": n}).holds is True
    failure = c.evaluate({"n": 40})
    assert failure.holds is False
    assert failure.is_verified_counterexample()


def test_fermat_number_five_is_composite():
    c = make("is_prime(2**(2**k) + 1)", variables={"k": {"kind": "integers", "low": 0, "high": 6}})
    assert all(c.evaluate({"k": k}).holds for k in range(5))
    assert c.evaluate({"k": 5}).is_verified_counterexample()


def test_divisor_count_is_multiplicative_only_on_coprime_arguments():
    variables = {"m": {"kind": "integers", "low": 1, "high": 20}, "n": {"kind": "integers", "low": 1, "high": 20}}
    naive = make("divisor_count(m*n) == divisor_count(m)*divisor_count(n)", variables=variables)
    assert naive.evaluate({"m": 2, "n": 2}).is_verified_counterexample()
    assert naive.evaluate({"m": 2, "n": 3}).holds is True

    guarded = make(
        "divisor_count(m*n) == divisor_count(m)*divisor_count(n)",
        variables=variables,
        assumptions=["gcd(m, n) == 1"],
    )
    blocked = guarded.evaluate({"m": 2, "n": 2})
    assert blocked.assumptions_hold is False
    assert not blocked.is_counterexample(), "an assignment failing the assumptions is not a counterexample"


# --------------------------------------------------------------------------
# The dual evaluator is the load-bearing safety property.
# --------------------------------------------------------------------------


def test_agreement_is_reported_as_dual_exact_when_both_paths_decide():
    assert make("n > 0", low=1, high=5).evaluate({"n": 3}).agreement == AGREEMENT_DUAL_EXACT


def test_irrational_values_degrade_to_symbolic_only_rather_than_comparing_floats():
    c = make("sqrt(n)*sqrt(n) == n", low=1, high=10)
    assert c.evaluate({"n": 4}).agreement == AGREEMENT_DUAL_EXACT
    assert c.evaluate({"n": 2}).agreement == AGREEMENT_SYMBOLIC_ONLY


def test_evaluator_disagreement_is_contested_and_never_a_verified_counterexample(monkeypatch):
    """If the two implementations disagree, that is a bug, not a refutation."""
    liar = (lambda n: False, ALLOWED_FUNCTIONS["is_prime"][1], (1, 1))
    monkeypatch.setitem(ALLOWED_FUNCTIONS, "is_prime", liar)

    c = make("is_prime(n)", low=2, high=20)
    result = c.evaluate({"n": 7})
    assert result.agreement == AGREEMENT_CONTESTED
    assert result.holds is None
    assert not result.is_counterexample(), "a contested assignment must not be reported as a refutation"
    assert not result.is_verified_counterexample()
    assert "rational evaluator said" in result.detail


def test_single_path_counterexample_is_reported_but_not_as_verified():
    c = make("sqrt(n) > n", low=2, high=3)
    result = c.evaluate({"n": 2})
    assert result.holds is False
    assert result.is_counterexample()
    assert not result.is_verified_counterexample(), "one evaluator alone is not agreement"


# --------------------------------------------------------------------------
# Predicates are untrusted input.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "predicate",
    [
        "__import__('os').system('true')",
        "open('/etc/passwd').read() == ''",
        "n.__class__ == int",
        "[x for x in range(10)] == []",
        "(lambda: 1)() == 1",
        "globals()",
        "n if n else exec('pass')",
    ],
)
def test_predicate_grammar_rejects_arbitrary_python(predicate):
    with pytest.raises(ConjectureError):
        make(predicate)


def test_unknown_function_is_rejected():
    with pytest.raises(ConjectureError, match="unknown function"):
        make("collatz_length(n) < 100")


def test_undeclared_variable_is_rejected():
    with pytest.raises(ConjectureError, match="undeclared variable"):
        make("n + m > 0")


def test_existential_quantifier_is_rejected_with_an_explanation():
    with pytest.raises(ConjectureError, match="universally quantified"):
        make("n > 0", quantifier="EXISTS")


def test_enormous_power_is_refused_rather_than_hanging():
    c = make("2**(2**n) > 0", low=0, high=40)
    result = c.evaluate({"n": 40})
    assert result.holds is None
    assert "refusing" in result.detail


def test_duplicate_conjecture_ids_are_rejected():
    from math_workbench.conjecture import load_conjectures

    spec = {"id": "dup", "statement": "s", "predicate": "n > 0", "variables": {"n": {"kind": "integers", "low": 1, "high": 2}}}
    with pytest.raises(ConjectureError, match="duplicate"):
        load_conjectures([spec, dict(spec)])


# --------------------------------------------------------------------------
# Domains.
# --------------------------------------------------------------------------


def test_integer_domain_indexing_and_size():
    d = Domain.from_dict("n", {"kind": "integers", "low": 4, "high": 10, "step": 2})
    assert d.size() == 4
    assert [d.at(i) for i in range(4)] == [4, 6, 8, 10]


def test_prime_domain_contains_only_primes_in_range():
    d = Domain.from_dict("p", {"kind": "primes", "low": 10, "high": 30})
    assert [d.at(i) for i in range(d.size())] == [11, 13, 17, 19, 23, 29]


def test_values_domain_accepts_a_bare_list_and_exact_fractions():
    d = Domain.from_dict("x", [1, "3/4", 2])
    assert [d.at(i) for i in range(d.size())] == [1, Fraction(3, 4), 2]


def test_rational_domain_is_exact():
    d = Domain.from_dict("q", {"kind": "rationals", "low": 0, "high": 1, "max_denominator": 3})
    values = [d.at(i) for i in range(d.size())]
    assert Fraction(1, 3) in values and Fraction(2, 3) in values
    assert all(isinstance(v, Fraction) for v in values)


def test_bad_domain_is_rejected():
    with pytest.raises(ConjectureError):
        Domain.from_dict("n", {"kind": "quaternions"})
    with pytest.raises(ConjectureError):
        Domain.from_dict("n", {"kind": "integers", "low": 10, "high": 1})


def test_conjecture_requires_at_least_one_variable():
    with pytest.raises(ConjectureError, match="at least one variable"):
        Conjecture.from_dict({"id": "c", "statement": "s", "predicate": "1 > 0", "variables": {}})


# --------------------------------------------------------------------------
# The two number-theory implementations must agree with each other.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "predicate,values",
    [
        ("divisor_count(n) > 0", range(1, 200)),
        ("totient(n) >= 1", range(1, 200)),
        ("mobius(n) * mobius(n) <= 1", range(1, 200)),
        ("divisor_sigma(n) >= n", range(1, 200)),
        ("gcd(n, n + 1) == 1", range(1, 200)),
        ("is_prime(n) or n < 2 or divisor_count(n) > 2", range(1, 200)),
        ("factorial(n) > 0", range(0, 30)),
        ("binomial(n, 2) * 2 == n * (n - 1)", range(2, 60)),
        ("prime(primepi(n)) <= n", range(2, 100)),
    ],
)
def test_independent_implementations_agree_across_a_range(predicate, values):
    """Every one of these must come back DUAL_EXACT.

    This is the cross-check that makes a VERIFIED_EXACT verdict mean something:
    hand-written Euclid/Miller-Rabin/trial-division against SymPy's own
    implementations, over a few hundred points each.
    """
    variables = {"n": {"kind": "integers", "low": min(values), "high": max(values)}}
    c = make(predicate, variables=variables)
    for n in values:
        result = c.evaluate({"n": n})
        assert result.agreement == AGREEMENT_DUAL_EXACT, f"{predicate} at n={n}: {result.detail}"
        assert result.holds is True, f"{predicate} is false at n={n}"
