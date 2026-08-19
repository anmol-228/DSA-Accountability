"""Functional test specifications for standalone Java exercises (spec
sections 15-19). Only defines cases for exercises the master curriculum
prompt actually gave a specification for (Day 1's four). Exercises without
a registered spec still get compile + non-skeleton validation — they are
never silently marked "tested" without real test cases, and never
fabricated to look more complete than they are.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from app.services import build_service


@dataclass
class TestCase:
    description: str
    stdin: str
    check: Callable[[str], bool]
    expected_label: str
    # Additional stdin orderings to accept as equally valid, tried in order
    # after `stdin` if it doesn't pass. Only ever set for an exercise whose
    # own scaffold comment doesn't disambiguate input order (see
    # SimpleCalculator below) -- every other exercise leaves this empty and
    # is completely unaffected.
    stdin_alternates: tuple[str, ...] = ()


@dataclass
class TestCaseResult:
    description: str
    passed: bool
    stdin: str
    expected: str
    actual: str
    timed_out: bool = False


@dataclass
class TestSuiteResult:
    defined: bool
    total: int = 0
    passed: int = 0
    results: list[TestCaseResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.defined and self.total > 0 and self.passed == self.total


def _last_number(text: str) -> float | None:
    """Extracts the last number in the output, decimal-aware -- a
    perfectly reasonable beginner SimpleCalculator implementation using
    `double` will print "15.0", not "15", and that must still be accepted
    (spec section 12: never reject on superficial formatting)."""
    matches = re.findall(r"-?\d+\.?\d*", text)
    return float(matches[-1]) if matches else None


def _matches_number(text: str, expected: int) -> bool:
    value = _last_number(text)
    return value is not None and abs(value - expected) < 1e-6


def _classify_even_odd(text: str) -> str | None:
    low = text.lower()
    if "odd" in low:
        return "odd"
    if "even" in low:
        return "even"
    return None


def _classify_leap(text: str) -> bool | None:
    low = text.lower()
    if "leap" not in low:
        return None
    if "not" in low:
        return False
    return True


def _even_odd_case(stdin: str, expect: str) -> TestCase:
    return TestCase(f"input {stdin.strip()}", stdin, lambda out: _classify_even_odd(out) == expect, expect)


def _leap_case(stdin: str, expect: bool) -> TestCase:
    label = "leap year" if expect else "not a leap year"
    return TestCase(f"input {stdin.strip()}", stdin, lambda out: _classify_leap(out) == expect, label)


def _number_case(stdin: str, expect: int, description: str | None = None) -> TestCase:
    return TestCase(description or f"input {stdin.strip().splitlines()}", stdin,
                     lambda out: _matches_number(out, expect), str(expect))


def _calculator_case(num1: int, num2: int, op: str, expect: int, description: str) -> TestCase:
    """SimpleCalculator's own scaffold comment ("Read two numbers and an
    operator, print the result") never specified a read order -- both
    number/operator/number and number/number/operator are equally valid
    readings of it, and real historical learner code has used the latter.
    Accept either: try number/operator/number first (the original test
    convention), then number/number/operator."""
    primary = f"{num1}\n{op}\n{num2}\n"
    alternate = f"{num1}\n{num2}\n{op}\n"
    return TestCase(description, primary, lambda out: _matches_number(out, expect), str(expect), (alternate,))


EXERCISE_TEST_SPECS: dict[str, list[TestCase]] = {
    "EvenOdd": [
        _even_odd_case("4\n", "even"),
        _even_odd_case("7\n", "odd"),
        _even_odd_case("0\n", "even"),
        _even_odd_case("-3\n", "odd"),
    ],
    "MaximumOfThree": [
        _number_case("10\n20\n15\n", 20, "10, 20, 15"),
        _number_case("5\n5\n3\n", 5, "5, 5, 3"),
        _number_case("-5\n-2\n-8\n", -2, "-5, -2, -8"),
        _number_case("7\n7\n7\n", 7, "7, 7, 7"),
    ],
    "LeapYear": [
        _leap_case("2024\n", True),
        _leap_case("2023\n", False),
        _leap_case("1900\n", False),  # century-handling check: divisible by 4 and 100 but not 400
        _leap_case("2000\n", True),   # divisible by 400 -> leap despite being a century year
    ],
    "SimpleCalculator": [
        _calculator_case(10, 5, "+", 15, "10 + 5"),
        _calculator_case(10, 5, "-", 5, "10 - 5"),
        _calculator_case(10, 5, "*", 50, "10 * 5"),
        _calculator_case(10, 5, "/", 2, "10 / 5"),
    ],
}


def has_test_spec(canonical_filename: str) -> bool:
    return canonical_filename in EXERCISE_TEST_SPECS


def run_functional_tests(canonical_filename: str, class_name: str, build_dir,
                          run_timeout: float = 5.0) -> TestSuiteResult:
    cases = EXERCISE_TEST_SPECS.get(canonical_filename)
    if not cases:
        return TestSuiteResult(defined=False)

    results = []
    passed = 0
    for case in cases:
        # Try the primary stdin first, then any accepted alternate orderings
        # (see TestCase.stdin_alternates) -- pass on the first one that
        # succeeds; if none succeed, report the primary attempt's failure
        # (most representative/first-documented ordering) for debugging.
        first_attempt: TestCaseResult | None = None
        case_passed = False
        for stdin in (case.stdin, *case.stdin_alternates):
            run = build_service.run_java_class(class_name, build_dir, stdin, timeout=run_timeout)
            if run.timed_out:
                attempt = TestCaseResult(case.description, False, stdin, case.expected_label,
                                          "(timed out)", timed_out=True)
            else:
                ok = run.ok and case.check(run.stdout)
                attempt = TestCaseResult(case.description, ok, stdin, case.expected_label,
                                          run.stdout.strip() or "(no output)")
            if first_attempt is None:
                first_attempt = attempt
            if attempt.passed:
                case_passed = True
                first_attempt = attempt  # report the ordering that actually worked
                break

        if case_passed:
            passed += 1
        results.append(first_attempt)

    return TestSuiteResult(defined=True, total=len(cases), passed=passed, results=results)
