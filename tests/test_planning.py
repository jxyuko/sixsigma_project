# test_planning.py
# Known answers (Recitation 12 "Planning Experiments", Examples 9-13) and degenerate cases for
# functions/planning.py (ROADMAP Section 9c, E27-E29).

import pytest
from scipy import stats

from functions.planning import (failures_for_power, required_test_time, sample_size, two_rate_power,
                                unit_hours_needed)


def test_sample_size_recitation_examples_9_and_12():
    # Example 9: 90%, MTTF 500,000 h, T = 5,000 h, up to 5 failures -> n = 928
    assert sample_size(1 / 500_000, 5000, 0.90, r=5) == 928
    # Example 12: zero failures, 90%, MTTF 40,000 h, T = 8,000 h -> n = 12
    assert sample_size(1 / 40_000, 8000, 0.90) == 12


def test_test_time_recitation_examples_10_and_13():
    # Example 10: n = 100, 95%, MTTF 20,000 h, up to 10 failures -> T = 3,392 h
    assert required_test_time(1 / 20_000, 100, 0.95, r=10) == pytest.approx(3392, abs=0.5)
    # Example 13: zero failures, 10 PPM/K = 1e-8 per hour, 80%, n = 10,000 -> T = 16,094 h
    assert required_test_time(10e-9, 10_000, 0.80) == pytest.approx(16094, abs=0.5)


def test_zero_failure_unit_hours_closed_form():
    # r = 0: n T = -ln(1 - conf) / lambda_obj
    assert unit_hours_needed(1e-6, 0.95) == pytest.approx(2.995732 / 1e-6, rel=1e-6)
    with pytest.raises(ValueError):
        unit_hours_needed(0, 0.95)


def test_power_degenerate_cases():
    assert two_rate_power(0, 0) == 0.0                         # no expected failures: no power
    # Equal rates: the test rejects at most alpha of the time
    assert two_rate_power(20, 20) <= 0.05
    # Huge evidence and a big difference: power near 1
    assert two_rate_power(200, 600) > 0.999


def test_power_known_answer_against_direct_sum():
    # Direct enumeration of the exact conditional test for mu1 = 3, mu2 = 9
    mu1, mu2, total = 3.0, 9.0, 0.0
    for n in range(1, 80):
        for f2 in range(n + 1):
            if stats.binom.sf(f2 - 1, n, 0.5) <= 0.05:
                total += stats.poisson.pmf(n - f2, mu1) * stats.poisson.pmf(f2, mu2)
    assert two_rate_power(mu1, mu2) == pytest.approx(total, abs=1e-6)


def test_failures_for_power_falls_with_bigger_differences():
    a, b, c = (failures_for_power(r) for r in (2, 3, 5))
    assert a > b > c > 0
    assert two_rate_power(b, 3 * b) >= 0.8
    with pytest.raises(ValueError):
        failures_for_power(1.0)
