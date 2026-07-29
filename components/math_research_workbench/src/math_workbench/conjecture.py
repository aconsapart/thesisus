"""Executable conjectures: claims a counterexample search can actually refute.

The workbench previously treated falsification as prompt rhetoric -- the system
prompt said "falsify before proving", but nothing in the pipeline could decide
whether a proposed counterexample was real.  A `Conjecture` closes that gap: it
is a universally quantified claim over declared variable domains whose body is a
machine-checkable predicate.

Every candidate witness is evaluated **twice, by independent implementations**:

1. a SymPy path (exact symbolic arithmetic, SymPy's number theory);
2. a pure-Python path (`int`/`Fraction`, hand-written number theory --
   Euclid's algorithm, Miller-Rabin, trial-division factorisation).

A witness is only ever recorded as `DUAL_EXACT` when both agree.  Disagreement
produces `CONTESTED`, which is reported and never silently upgraded to a
refutation: a counterexample that only one evaluator believes is a bug report,
not a theorem.

Predicates are parsed from a restricted expression grammar (see `_assert_safe`)
and never passed to `eval` on an unfiltered namespace.
"""

from __future__ import annotations

import ast
import math
import random
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable, Iterator, Sequence

import sympy as sp

__all__ = [
    "ConjectureError",
    "EvaluationError",
    "UndecidedError",
    "InexactError",
    "Domain",
    "Conjecture",
    "Evaluation",
    "ALLOWED_FUNCTIONS",
]


class ConjectureError(ValueError):
    """A conjecture specification is malformed."""


class EvaluationError(RuntimeError):
    """A predicate could not be evaluated (bad arity, guard tripped, ...)."""


class UndecidedError(EvaluationError):
    """A predicate evaluated to something that is not a definite truth value."""


class InexactError(EvaluationError):
    """The rational evaluator cannot represent a value exactly."""


# --------------------------------------------------------------------------
# Guards.  A predicate is attacker-adjacent input (it comes from YAML written
# by a collaborator, or from an LLM proposing a repaired statement), so the
# grammar is a whitelist and every unbounded operation is capped.
# --------------------------------------------------------------------------

MAX_POW_BITS = 200_000
MAX_FACTORIAL = 5_000
MAX_TRIAL_DIVISION = 10**14

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.IfExp,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Call,
    ast.List,
    ast.Tuple,
    ast.Set,
)


def _assert_safe(tree: ast.AST, expr: str) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ConjectureError(
                f"disallowed syntax {type(node).__name__!r} in predicate: {expr!r}"
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ConjectureError(f"only direct calls to named functions are allowed: {expr!r}")
            if node.func.id not in ALLOWED_FUNCTIONS:
                raise ConjectureError(f"unknown function {node.func.id!r} in predicate: {expr!r}")
            if node.keywords:
                raise ConjectureError(f"keyword arguments are not allowed: {expr!r}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            raise ConjectureError(f"only numeric/boolean constants are allowed: {expr!r}")


def _parse(expr: str) -> ast.Expression:
    if not isinstance(expr, str) or not expr.strip():
        raise ConjectureError("predicate must be a non-empty string")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:  # pragma: no cover - message varies by version
        raise ConjectureError(f"cannot parse predicate {expr!r}: {exc}") from exc
    _assert_safe(tree, expr)
    return tree


# --------------------------------------------------------------------------
# Independent evaluator #1: pure Python over int / Fraction.
#
# These deliberately do NOT call SymPy.  Their whole purpose is to be a second
# opinion, so they use different algorithms: Euclid rather than SymPy's gcd,
# Miller-Rabin rather than BPSW, trial-division factorisation rather than
# SymPy's factorint.
# --------------------------------------------------------------------------


def _as_int(x: Any, who: str) -> int:
    if isinstance(x, bool):
        raise EvaluationError(f"{who} expects a number, got a boolean")
    if isinstance(x, int):
        return x
    if isinstance(x, Fraction) and x.denominator == 1:
        return int(x)
    raise EvaluationError(f"{who} expects an integer, got {x!r}")


def _py_gcd(a: int, b: int) -> int:
    a, b = abs(a), abs(b)
    while b:
        a, b = b, a % b
    return a


def _py_is_prime(n: int) -> bool:
    """Deterministic Miller-Rabin for 64-bit inputs, with a fallback warning."""
    if n < 2:
        return False
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in small_primes:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in small_primes:  # deterministic for n < 3.3 * 10^24
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _py_factorize(n: int) -> dict[int, int]:
    """Trial-division factorisation, capped so a huge input fails loudly."""
    n = abs(n)
    if n == 0:
        raise EvaluationError("cannot factor 0")
    if n > MAX_TRIAL_DIVISION:
        raise EvaluationError(f"refusing to factor {n} (> {MAX_TRIAL_DIVISION})")
    factors: dict[int, int] = {}
    for p in (2, 3):
        while n % p == 0:
            factors[p] = factors.get(p, 0) + 1
            n //= p
    f = 5
    while f * f <= n:
        for step in (2, 4):
            while n % f == 0:
                factors[f] = factors.get(f, 0) + 1
                n //= f
            f += step
    if n > 1:
        factors[n] = factors.get(n, 0) + 1
    return factors


def _py_divisor_count(n: int) -> int:
    if n == 0:
        raise EvaluationError("divisor_count(0) is undefined")
    count = 1
    for e in _py_factorize(n).values():
        count *= e + 1
    return count


def _py_divisor_sigma(n: int, k: int = 1) -> int:
    if n == 0:
        raise EvaluationError("divisor_sigma(0) is undefined")
    total = 1
    for p, e in _py_factorize(n).items():
        if k == 0:
            total *= e + 1
        else:
            total *= (p ** (k * (e + 1)) - 1) // (p**k - 1)
    return total


def _py_totient(n: int) -> int:
    if n < 1:
        raise EvaluationError("totient expects a positive integer")
    if n == 1:
        return 1
    result = n
    for p in _py_factorize(n):
        result = result // p * (p - 1)
    return result


def _py_mobius(n: int) -> int:
    if n < 1:
        raise EvaluationError("mobius expects a positive integer")
    if n == 1:
        return 1
    factors = _py_factorize(n)
    if any(e > 1 for e in factors.values()):
        return 0
    return -1 if len(factors) % 2 else 1


def _py_factorial(n: int) -> int:
    if n < 0:
        raise EvaluationError("factorial expects a non-negative integer")
    if n > MAX_FACTORIAL:
        raise EvaluationError(f"refusing to compute {n}! (> {MAX_FACTORIAL})")
    return math.factorial(n)


def _py_binomial(n: int, k: int) -> int:
    if k < 0:
        return 0
    if n < 0:
        raise EvaluationError("binomial expects a non-negative first argument")
    if n > MAX_FACTORIAL:
        raise EvaluationError(f"refusing to compute binomial({n}, {k})")
    return math.comb(n, k)


def _py_sqrt(x: Any) -> Any:
    """Exact square root, or a loud failure.

    The rational evaluator refuses to approximate.  An irrational value makes
    this path abstain (`InexactError`), which downgrades the witness to
    `SYMBOLIC_ONLY` rather than silently comparing floats.
    """
    if isinstance(x, int):
        if x < 0:
            raise InexactError("sqrt of a negative number is not rational")
        root = math.isqrt(x)
        if root * root != x:
            raise InexactError(f"sqrt({x}) is irrational")
        return root
    if isinstance(x, Fraction):
        if x < 0:
            raise InexactError("sqrt of a negative number is not rational")
        num, den = math.isqrt(x.numerator), math.isqrt(x.denominator)
        if num * num != x.numerator or den * den != x.denominator:
            raise InexactError(f"sqrt({x}) is irrational")
        return Fraction(num, den)
    raise EvaluationError(f"sqrt expects a number, got {x!r}")


def _py_prime(k: int) -> int:
    """The k-th prime (1-indexed), by sieve."""
    if k < 1:
        raise EvaluationError("prime expects a positive index")
    if k > 100_000:
        raise EvaluationError("refusing to compute a prime index above 100000")
    limit = 20 if k < 6 else int(k * (math.log(k) + math.log(math.log(k)))) + 10
    while True:
        sieve = bytearray([1]) * (limit + 1)
        sieve[0:2] = b"\x00\x00"
        for i in range(2, math.isqrt(limit) + 1):
            if sieve[i]:
                sieve[i * i :: i] = bytearray(len(sieve[i * i :: i]))
        primes = [i for i, flag in enumerate(sieve) if flag]
        if len(primes) >= k:
            return primes[k - 1]
        limit *= 2


def _py_primepi(n: int) -> int:
    if n < 2:
        return 0
    if n > 10_000_000:
        raise EvaluationError("refusing to compute primepi above 10^7")
    sieve = bytearray([1]) * (n + 1)
    sieve[0:2] = b"\x00\x00"
    for i in range(2, math.isqrt(n) + 1):
        if sieve[i]:
            sieve[i * i :: i] = bytearray(len(sieve[i * i :: i]))
    return sum(sieve)


def _py_pow(base: Any, exponent: Any) -> Any:
    exp = _as_int(exponent, "**") if not isinstance(exponent, Fraction) or exponent.denominator == 1 else None
    if exp is None:
        raise InexactError("fractional exponents are not evaluated exactly")
    if isinstance(base, bool) or isinstance(exponent, bool):
        raise EvaluationError("** expects numbers, got a boolean")
    magnitude = abs(base.numerator if isinstance(base, Fraction) else base)
    bits = max(magnitude.bit_length(), 1) * abs(exp)
    if bits > MAX_POW_BITS:
        raise EvaluationError(f"refusing to compute a power with ~{bits} bits")
    if exp < 0:
        if base == 0:
            raise EvaluationError("0 raised to a negative power")
        return Fraction(1, 1) / Fraction(base) ** (-exp)
    return base**exp


# Each entry is (python implementation, sympy implementation, arity range).
ALLOWED_FUNCTIONS: dict[str, tuple[Callable[..., Any], Callable[..., Any], tuple[int, int]]] = {
    "abs": (abs, sp.Abs, (1, 1)),
    "min": (min, sp.Min, (1, 8)),
    "max": (max, sp.Max, (1, 8)),
    "gcd": (lambda *xs: _py_gcd_many(xs), lambda *xs: sp.gcd(list(xs)), (1, 8)),
    "lcm": (lambda *xs: _py_lcm_many(xs), lambda *xs: sp.lcm(list(xs)), (1, 8)),
    "floor": (math.floor, sp.floor, (1, 1)),
    "ceiling": (math.ceil, sp.ceiling, (1, 1)),
    "sqrt": (_py_sqrt, sp.sqrt, (1, 1)),
    "factorial": (lambda n: _py_factorial(_as_int(n, "factorial")), sp.factorial, (1, 1)),
    "binomial": (
        lambda n, k: _py_binomial(_as_int(n, "binomial"), _as_int(k, "binomial")),
        sp.binomial,
        (2, 2),
    ),
    "is_prime": (lambda n: _py_is_prime(_as_int(n, "is_prime")), lambda n: sp.sympify(sp.isprime(n)), (1, 1)),
    "divisor_count": (
        lambda n: _py_divisor_count(_as_int(n, "divisor_count")),
        sp.divisor_count,
        (1, 1),
    ),
    "divisor_sigma": (
        lambda n, k=1: _py_divisor_sigma(_as_int(n, "divisor_sigma"), _as_int(k, "divisor_sigma")),
        sp.divisor_sigma,
        (1, 2),
    ),
    "totient": (lambda n: _py_totient(_as_int(n, "totient")), sp.totient, (1, 1)),
    "mobius": (lambda n: _py_mobius(_as_int(n, "mobius")), sp.mobius, (1, 1)),
    "prime": (lambda k: _py_prime(_as_int(k, "prime")), sp.prime, (1, 1)),
    "primepi": (lambda n: _py_primepi(_as_int(n, "primepi")), sp.primepi, (1, 1)),
    "log": (lambda *a: _inexact("log"), sp.log, (1, 2)),
    "exp": (lambda *a: _inexact("exp"), sp.exp, (1, 1)),
}


def _inexact(name: str) -> Any:
    raise InexactError(f"{name} has no exact rational evaluation")


def _py_gcd_many(xs: Sequence[Any]) -> int:
    out = 0
    for x in xs:
        out = _py_gcd(out, _as_int(x, "gcd"))
    return out


def _py_lcm_many(xs: Sequence[Any]) -> int:
    out = 1
    for x in xs:
        v = _as_int(x, "lcm")
        if v == 0:
            return 0
        out = abs(out * v) // _py_gcd(out, v)
    return out


# --------------------------------------------------------------------------
# The two evaluators.
# --------------------------------------------------------------------------


class _RationalEvaluator(ast.NodeVisitor):
    """Evaluate a predicate over `int` / `Fraction` / `bool` -- no SymPy."""

    def __init__(self, env: dict[str, Any]) -> None:
        self.env = env

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, float):
            return Fraction(node.value).limit_denominator(10**12)
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.env:
            return self.env[node.id]
        raise EvaluationError(f"unbound variable {node.id!r}")

    def visit_List(self, node: ast.List) -> Any:
        return [self.visit(e) for e in node.elts]

    visit_Tuple = visit_List  # type: ignore[assignment]
    visit_Set = visit_List  # type: ignore[assignment]

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        return self.visit(node.body) if _truth(self.visit(node.test)) else self.visit(node.orelse)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [_truth(self.visit(v)) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not _truth(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        return +operand

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left, right = self.visit(node.left), self.visit(node.right)
        op = node.op
        if isinstance(op, ast.Pow):
            return _py_pow(left, right)
        if isinstance(op, ast.Div):
            if right == 0:
                raise EvaluationError("division by zero")
            return Fraction(left) / Fraction(right)
        if isinstance(op, ast.FloorDiv):
            if right == 0:
                raise EvaluationError("floor division by zero")
            return left // right
        if isinstance(op, ast.Mod):
            if right == 0:
                raise EvaluationError("modulo by zero")
            return left % right
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        return left * right

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            elif isinstance(op, ast.In):
                ok = any(left == item for item in right)
            else:
                ok = all(left != item for item in right)
            if not ok:
                return False
            left = right
        return True

    def visit_Call(self, node: ast.Call) -> Any:
        name = node.func.id  # type: ignore[union-attr]
        impl, _sym, (lo, hi) = ALLOWED_FUNCTIONS[name]
        args = [self.visit(a) for a in node.args]
        if not lo <= len(args) <= hi:
            raise EvaluationError(f"{name} takes {lo}..{hi} arguments, got {len(args)}")
        return impl(*args)

    def generic_visit(self, node: ast.AST) -> Any:  # pragma: no cover - guarded upstream
        raise EvaluationError(f"unsupported node {type(node).__name__}")


class _SymbolicEvaluator(ast.NodeVisitor):
    """Evaluate a predicate with SymPy exact arithmetic."""

    def __init__(self, env: dict[str, Any]) -> None:
        self.env = {k: _to_sympy(v) for k, v in env.items()}

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, bool):
            return sp.true if node.value else sp.false
        return sp.nsimplify(sp.Rational(str(node.value))) if isinstance(node.value, float) else sp.Integer(node.value)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.env:
            return self.env[node.id]
        raise EvaluationError(f"unbound variable {node.id!r}")

    def visit_List(self, node: ast.List) -> Any:
        return [self.visit(e) for e in node.elts]

    visit_Tuple = visit_List  # type: ignore[assignment]
    visit_Set = visit_List  # type: ignore[assignment]

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        return self.visit(node.body) if _sympy_truth(self.visit(node.test)) else self.visit(node.orelse)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [_sympy_truth(self.visit(v)) for v in node.values]
        result = all(values) if isinstance(node.op, ast.And) else any(values)
        return sp.true if result else sp.false

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return sp.false if _sympy_truth(operand) else sp.true
        if isinstance(node.op, ast.USub):
            return -operand
        return +operand

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left, right = self.visit(node.left), self.visit(node.right)
        op = node.op
        if isinstance(op, ast.Pow):
            if left.is_Integer and right.is_Integer:
                bits = max(int(abs(left)).bit_length(), 1) * abs(int(right))
                if bits > MAX_POW_BITS:
                    raise EvaluationError(f"refusing to compute a power with ~{bits} bits")
            return left**right
        if isinstance(op, ast.Div):
            if right == 0:
                raise EvaluationError("division by zero")
            return left / right
        if isinstance(op, ast.FloorDiv):
            if right == 0:
                raise EvaluationError("floor division by zero")
            return sp.floor(left / right)
        if isinstance(op, ast.Mod):
            if right == 0:
                raise EvaluationError("modulo by zero")
            return sp.Mod(left, right)
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        return left * right

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if isinstance(op, ast.Eq):
                rel: Any = sp.Eq(left, right)
            elif isinstance(op, ast.NotEq):
                rel = sp.Ne(left, right)
            elif isinstance(op, ast.Lt):
                rel = sp.Lt(left, right)
            elif isinstance(op, ast.LtE):
                rel = sp.Le(left, right)
            elif isinstance(op, ast.Gt):
                rel = sp.Gt(left, right)
            elif isinstance(op, ast.GtE):
                rel = sp.Ge(left, right)
            elif isinstance(op, ast.In):
                rel = sp.true if any(_sympy_truth(sp.Eq(left, item)) for item in right) else sp.false
            else:
                rel = sp.true if all(not _sympy_truth(sp.Eq(left, item)) for item in right) else sp.false
            if not _sympy_truth(rel):
                return sp.false
            left = right
        return sp.true

    def visit_Call(self, node: ast.Call) -> Any:
        name = node.func.id  # type: ignore[union-attr]
        _impl, sym, (lo, hi) = ALLOWED_FUNCTIONS[name]
        args = [self.visit(a) for a in node.args]
        if not lo <= len(args) <= hi:
            raise EvaluationError(f"{name} takes {lo}..{hi} arguments, got {len(args)}")
        return sym(*args)

    def generic_visit(self, node: ast.AST) -> Any:  # pragma: no cover - guarded upstream
        raise EvaluationError(f"unsupported node {type(node).__name__}")


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise UndecidedError(f"expected a truth value, got {value!r}")


def _sympy_truth(value: Any) -> bool:
    if value is sp.true or value is True:
        return True
    if value is sp.false or value is False:
        return False
    simplified = sp.simplify(value)
    if simplified is sp.true or simplified is True:
        return True
    if simplified is sp.false or simplified is False:
        return False
    raise UndecidedError(f"predicate did not reduce to a definite truth value: {value!r}")


def _to_sympy(value: Any) -> Any:
    if isinstance(value, bool):
        return sp.true if value else sp.false
    if isinstance(value, int):
        return sp.Integer(value)
    if isinstance(value, Fraction):
        return sp.Rational(value.numerator, value.denominator)
    if isinstance(value, float):
        return sp.Rational(str(value))
    return sp.sympify(value)


# --------------------------------------------------------------------------
# Domains.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Domain:
    """A finite, indexable search space for one variable.

    Indexable rather than merely iterable so the search can enumerate
    *diagonally* across several variables (see `search.shell_indices`) instead
    of exhausting the first variable's range before touching the second.
    """

    name: str
    kind: str
    low: int = 0
    high: int = 0
    step: int = 1
    values: tuple[Any, ...] = ()
    max_denominator: int = 1

    @classmethod
    def from_dict(cls, name: str, spec: Any) -> "Domain":
        if isinstance(spec, (list, tuple)):
            spec = {"kind": "values", "values": list(spec)}
        if not isinstance(spec, dict):
            raise ConjectureError(f"domain for {name!r} must be a mapping or a list, got {spec!r}")
        kind = str(spec.get("kind", "integers")).lower()
        if kind in {"integers", "integer", "int", "naturals", "natural"}:
            low = int(spec.get("low", 1 if kind.startswith("natural") else 0))
            high = int(spec.get("high", low + 99))
            step = int(spec.get("step", 1))
            if step <= 0:
                raise ConjectureError(f"domain {name!r}: step must be positive")
            if high < low:
                raise ConjectureError(f"domain {name!r}: high < low")
            return cls(name=name, kind="integers", low=low, high=high, step=step)
        if kind in {"primes", "prime"}:
            low = int(spec.get("low", 2))
            high = int(spec.get("high", 100))
            if high < low:
                raise ConjectureError(f"domain {name!r}: high < low")
            primes = tuple(p for p in _primes_up_to(high) if p >= low)
            return cls(name=name, kind="values", values=primes)
        if kind in {"values", "enum", "list"}:
            raw = spec.get("values", [])
            if not raw:
                raise ConjectureError(f"domain {name!r}: 'values' must be non-empty")
            return cls(name=name, kind="values", values=tuple(_coerce_value(v) for v in raw))
        if kind in {"rationals", "rational"}:
            low = int(spec.get("low", 0))
            high = int(spec.get("high", 1))
            den = int(spec.get("max_denominator", 6))
            if den < 1:
                raise ConjectureError(f"domain {name!r}: max_denominator must be >= 1")
            seen: list[Fraction] = []
            for q in range(1, den + 1):
                for p in range(low * q, high * q + 1):
                    value = Fraction(p, q)
                    if low <= value <= high and value not in seen:
                        seen.append(value)
            seen.sort(key=lambda f: (abs(f), f.denominator, f))
            return cls(name=name, kind="values", values=tuple(seen))
        raise ConjectureError(f"domain {name!r}: unknown kind {kind!r}")

    def size(self) -> int:
        if self.kind == "values":
            return len(self.values)
        return (self.high - self.low) // self.step + 1

    def at(self, index: int) -> Any:
        if self.kind == "values":
            return self.values[index]
        return self.low + index * self.step

    def sample(self, rng: random.Random) -> Any:
        return self.at(rng.randrange(self.size()))

    def describe(self) -> str:
        if self.kind == "values":
            shown = ", ".join(str(v) for v in self.values[:6])
            suffix = ", ..." if len(self.values) > 6 else ""
            return f"{self.name} in {{{shown}{suffix}}} ({len(self.values)} values)"
        return f"{self.name} in [{self.low}, {self.high}] step {self.step} ({self.size()} values)"


def _coerce_value(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return Fraction(str(v))
    if isinstance(v, str):
        try:
            return Fraction(v) if "/" in v else int(v)
        except ValueError as exc:
            raise ConjectureError(f"cannot interpret domain value {v!r}") from exc
    raise ConjectureError(f"cannot interpret domain value {v!r}")


def _primes_up_to(n: int) -> list[int]:
    if n < 2:
        return []
    if n > 10_000_000:
        raise ConjectureError("prime domain upper bound above 10^7 is refused")
    sieve = bytearray([1]) * (n + 1)
    sieve[0:2] = b"\x00\x00"
    for i in range(2, math.isqrt(n) + 1):
        if sieve[i]:
            sieve[i * i :: i] = bytearray(len(sieve[i * i :: i]))
    return [i for i, flag in enumerate(sieve) if flag]


# --------------------------------------------------------------------------
# Evaluation result.
# --------------------------------------------------------------------------

AGREEMENT_DUAL_EXACT = "DUAL_EXACT"
AGREEMENT_SYMBOLIC_ONLY = "SYMBOLIC_ONLY"
AGREEMENT_RATIONAL_ONLY = "RATIONAL_ONLY"
AGREEMENT_CONTESTED = "CONTESTED"
AGREEMENT_ERROR = "ERROR"

TRUSTED_AGREEMENTS = frozenset({AGREEMENT_DUAL_EXACT, AGREEMENT_SYMBOLIC_ONLY, AGREEMENT_RATIONAL_ONLY})


@dataclass(frozen=True)
class Evaluation:
    """The outcome of testing one assignment against one conjecture."""

    assignment: dict[str, Any]
    holds: bool | None
    assumptions_hold: bool | None
    agreement: str
    detail: str = ""

    def is_counterexample(self) -> bool:
        """A refutation we are willing to report at all."""
        return (
            self.assumptions_hold is True
            and self.holds is False
            and self.agreement in TRUSTED_AGREEMENTS
        )

    def is_verified_counterexample(self) -> bool:
        """A refutation two independent evaluators agree on."""
        return self.is_counterexample() and self.agreement == AGREEMENT_DUAL_EXACT

    def as_dict(self) -> dict[str, Any]:
        return {
            "assignment": {k: _jsonable(v) for k, v in self.assignment.items()},
            "holds": self.holds,
            "assumptions_hold": self.assumptions_hold,
            "agreement": self.agreement,
            "detail": self.detail,
        }


def _jsonable(v: Any) -> Any:
    if isinstance(v, Fraction):
        return str(v) if v.denominator != 1 else int(v)
    if isinstance(v, (int, bool, str)) or v is None:
        return v
    return str(v)


# --------------------------------------------------------------------------
# Conjecture.
# --------------------------------------------------------------------------


@dataclass
class Conjecture:
    """A universally quantified, machine-checkable claim.

    `predicate` is asserted to hold for every assignment of the declared
    variables that satisfies every expression in `assumptions`.
    """

    id: str
    statement: str
    predicate: str
    variables: dict[str, Domain] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    quantifier: str = "FORALL"
    notes: str = ""
    targets: list[str] = field(default_factory=list)

    _predicate_ast: ast.Expression = field(init=False, repr=False)
    _assumption_asts: list[ast.Expression] = field(init=False, repr=False, default_factory=list)

    def __post_init__(self) -> None:
        if self.quantifier.upper() not in {"FORALL", "FOR_ALL", "ALL"}:
            raise ConjectureError(
                f"conjecture {self.id!r}: only universally quantified claims are refutable by "
                f"witness search, got quantifier {self.quantifier!r}"
            )
        self.quantifier = "FORALL"
        if not self.variables:
            raise ConjectureError(f"conjecture {self.id!r}: at least one variable is required")
        self._predicate_ast = _parse(self.predicate)
        self._assumption_asts = [_parse(a) for a in self.assumptions]
        free = _free_names(self._predicate_ast) | {
            n for tree in self._assumption_asts for n in _free_names(tree)
        }
        unknown = free - set(self.variables)
        if unknown:
            raise ConjectureError(
                f"conjecture {self.id!r}: undeclared variable(s) {sorted(unknown)} in predicate"
            )

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> "Conjecture":
        if not isinstance(spec, dict):
            raise ConjectureError(f"conjecture spec must be a mapping, got {spec!r}")
        cid = str(spec.get("id") or spec.get("slug") or "")
        if not cid:
            raise ConjectureError("conjecture spec requires an 'id'")
        raw_vars = spec.get("variables") or {}
        if isinstance(raw_vars, list):  # allow [{name: n, kind: integers, ...}]
            raw_vars = {v["name"]: {k: x for k, x in v.items() if k != "name"} for v in raw_vars}
        variables = {name: Domain.from_dict(name, dom) for name, dom in raw_vars.items()}
        return cls(
            id=cid,
            statement=str(spec.get("statement", cid)),
            predicate=str(spec.get("predicate", "")),
            variables=variables,
            assumptions=[str(a) for a in (spec.get("assumptions") or [])],
            quantifier=str(spec.get("quantifier", "FORALL")),
            notes=str(spec.get("notes", "")),
            targets=[str(t) for t in (spec.get("targets") or [])],
        )

    @property
    def variable_names(self) -> list[str]:
        return list(self.variables)

    def space_size(self) -> int:
        total = 1
        for domain in self.variables.values():
            total *= domain.size()
        return total

    def evaluate(self, assignment: dict[str, Any]) -> Evaluation:
        """Test one assignment with both evaluators and compare their verdicts."""
        missing = set(self.variables) - set(assignment)
        if missing:
            return Evaluation(
                assignment=dict(assignment),
                holds=None,
                assumptions_hold=None,
                agreement=AGREEMENT_ERROR,
                detail=f"missing values for {sorted(missing)}",
            )
        env = {k: _coerce_value(v) if isinstance(v, (str, float)) else v for k, v in assignment.items()}

        assumptions = self._eval_both_all(self._assumption_asts, env)
        if assumptions.agreement == AGREEMENT_ERROR:
            return Evaluation(dict(env), None, None, AGREEMENT_ERROR, f"assumptions: {assumptions.detail}")
        if assumptions.value is False:
            return Evaluation(dict(env), None, False, assumptions.agreement, "assumptions do not hold")

        predicate = self._eval_both(self._predicate_ast, env)
        return Evaluation(
            assignment=dict(env),
            holds=predicate.value,
            assumptions_hold=True,
            agreement=predicate.agreement,
            detail=predicate.detail,
        )

    # -- internals ------------------------------------------------------

    def _eval_both(self, tree: ast.Expression, env: dict[str, Any]) -> "_DualResult":
        rational: bool | None = None
        rational_error = ""
        try:
            rational = _truth(_RationalEvaluator(env).visit(tree))
        except InexactError as exc:
            rational_error = f"rational evaluator abstained: {exc}"
        except EvaluationError as exc:
            rational_error = f"rational evaluator failed: {exc}"
        except (ArithmeticError, ValueError, TypeError, RecursionError) as exc:
            rational_error = f"rational evaluator raised {type(exc).__name__}: {exc}"

        symbolic: bool | None = None
        symbolic_error = ""
        try:
            symbolic = _sympy_truth(_SymbolicEvaluator(env).visit(tree))
        except EvaluationError as exc:
            symbolic_error = f"symbolic evaluator failed: {exc}"
        except (ArithmeticError, ValueError, TypeError, RecursionError) as exc:
            symbolic_error = f"symbolic evaluator raised {type(exc).__name__}: {exc}"

        if rational is not None and symbolic is not None:
            if rational == symbolic:
                return _DualResult(rational, AGREEMENT_DUAL_EXACT, "")
            return _DualResult(
                None,
                AGREEMENT_CONTESTED,
                f"rational evaluator said {rational}, symbolic evaluator said {symbolic} -- "
                "this is a bug in one of them and must be investigated before the witness is used",
            )
        if symbolic is not None:
            return _DualResult(symbolic, AGREEMENT_SYMBOLIC_ONLY, rational_error)
        if rational is not None:
            return _DualResult(rational, AGREEMENT_RATIONAL_ONLY, symbolic_error)
        return _DualResult(None, AGREEMENT_ERROR, "; ".join(x for x in (rational_error, symbolic_error) if x))

    def _eval_both_all(self, trees: list[ast.Expression], env: dict[str, Any]) -> "_DualResult":
        if not trees:
            return _DualResult(True, AGREEMENT_DUAL_EXACT, "")
        weakest = AGREEMENT_DUAL_EXACT
        details: list[str] = []
        for tree in trees:
            result = self._eval_both(tree, env)
            if result.agreement in {AGREEMENT_ERROR, AGREEMENT_CONTESTED}:
                return result
            if result.value is False:
                return _DualResult(False, result.agreement, result.detail)
            if result.agreement != AGREEMENT_DUAL_EXACT:
                weakest = result.agreement
            if result.detail:
                details.append(result.detail)
        return _DualResult(True, weakest, "; ".join(details))


@dataclass(frozen=True)
class _DualResult:
    value: bool | None
    agreement: str
    detail: str


def _free_names(tree: ast.AST) -> set[str]:
    """Variable names in an expression, excluding whitelisted call targets."""
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    call_targets = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return names - call_targets


def load_conjectures(specs: Sequence[dict[str, Any]] | None) -> list[Conjecture]:
    """Build conjectures from problem-spec dictionaries, reporting bad ones by id."""
    out: list[Conjecture] = []
    for spec in specs or []:
        out.append(Conjecture.from_dict(spec))
    ids = [c.id for c in out]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ConjectureError(f"duplicate conjecture ids: {sorted(duplicates)}")
    return out


def iter_assignments(conjecture: Conjecture, indices: Iterator[tuple[int, ...]]) -> Iterator[dict[str, Any]]:
    names = conjecture.variable_names
    domains = [conjecture.variables[n] for n in names]
    for idx in indices:
        yield {name: domain.at(i) for name, domain, i in zip(names, domains, idx)}
