# test_significance.py
# Known answers and degenerate cases for functions/significance.py (E18-E21, Section 9b).

import math

import numpy as np
import pytest
from scipy import stats

from functions.arrhenius import accel_factor
from functions.significance import (bootstrap_ci, max_demonstrated_temp, max_failure_rate, mc_standard_error,
                                    one_sample_t, proportion_ci, target_rate, target_test, two_rate_test)

D55 = 1900 * 1000 * accel_factor(55, 125, 0.7)        # TI C2000 device-hours at 55 C


# --- E18: course maximum failure rate -----------------------------------------------------------

def test_max_rate_zero_failures_course_formula():
    # r = 0: lambda_95 = -ln(0.05) / (n T)
    assert max_failure_rate(0, 1e6, 0.95) == pytest.approx(-math.log(0.05) / 1e6, rel=1e-12)


def test_max_rate_k_factor_form():
    # r >= 1: lambda_hat * k with k = chi2(0.95; 2(r+1)) / (2r) (course Table 3)
    r, d = 2, 5e5
    k = stats.chi2.ppf(0.95, 2 * (r + 1)) / (2 * r)
    assert max_failure_rate(r, d, 0.95) == pytest.approx((r / d) * k, rel=1e-12)
    assert k == pytest.approx(3.15, abs=0.01)                    # the table's value for r = 2, 95%


def test_max_rate_known_answer_ti_c2000_60pct():
    assert max_failure_rate(0, D55, 0.60) * 1e9 == pytest.approx(6.21, abs=0.01)


# --- E19: target test -------------------------------------------------------------------------

def test_target_rate():
    assert target_rate(0.999, 2920) == pytest.approx(-math.log(0.999) / 2920)
    with pytest.raises(ValueError):
        target_rate(1.0, 2920)


def test_target_test_consistent_with_bound():
    # p < 0.05 exactly when the 95% maximum rate is below the target rate
    lam_t = target_rate(0.999, 2920)
    for d in (0.5 * -math.log(0.05) / lam_t, 2 * -math.log(0.05) / lam_t):
        res = target_test(0, d, 0.999, 2920)
        assert res["p_value"] == pytest.approx(math.exp(-lam_t * d))     # f = 0: P(0 failures | H0)
        assert res["demonstrated"] == (res["lambda_max"] < res["lambda_target"])
    assert target_test(0, 2 * -math.log(0.05) / lam_t, 0.999, 2920)["demonstrated"]
    assert not target_test(0, 0.5 * -math.log(0.05) / lam_t, 0.999, 2920)["demonstrated"]


def test_target_test_degenerate_boundary():
    # Evidence exactly at the boundary: p = alpha
    lam_t = target_rate(0.999, 2920)
    res = target_test(0, -math.log(0.05) / lam_t, 0.999, 2920)
    assert res["p_value"] == pytest.approx(0.05)
    assert res["r_mission_min"] == pytest.approx(0.999)


# --- E20: maximum demonstrated temperature ----------------------------------------------------------

def test_max_demonstrated_temp_round_trip():
    t_max = max_demonstrated_temp(0, 1.9e6, 125, 0.7, 0.999, 2920)
    d = 1.9e6 * accel_factor(t_max, 125, 0.7)
    assert max_failure_rate(0, d, 0.95) == pytest.approx(target_rate(0.999, 2920), rel=1e-9)


def test_max_demonstrated_temp_degenerate():
    # Evidence that exactly meets the target at the test temperature: T_max = T_test
    d = -math.log(0.05) / target_rate(0.999, 2920)
    assert max_demonstrated_temp(0, d, 125, 0.7, 0.999, 2920) == pytest.approx(125, abs=1e-9)
    # More evidence -> a higher demonstrated temperature
    assert max_demonstrated_temp(0, 10 * d, 125, 0.7, 0.999, 2920) > 125


# --- E21: two-rate test ------------------------------------------------------------------------

def test_two_rate_test_no_failures_is_uninformative():
    assert two_rate_test(0, 1e6, 0, 1e9) == {"p_one_sided": 1.0, "p_two_sided": 1.0}


def test_two_rate_test_known_answer():
    # f1 = 0, f2 = 3, equal device-hours: under H0 each failure is equally likely in either group,
    # so P(all 3 in group 2) = 0.5^3 = 0.125
    res = two_rate_test(0, 1e6, 3, 1e6)
    assert res["p_one_sided"] == pytest.approx(0.125)
    assert res["p_two_sided"] == pytest.approx(0.25)


# --- t-test, proportions, bootstrap, MC error ---------------------------------------------------

def test_one_sample_t_known_answer():
    res = one_sample_t([1.0, 2.0, 3.0], mu0=0)
    assert res["mean"] == 2.0
    assert res["t"] == pytest.approx(2 / (1 / math.sqrt(3)))
    assert res["lower"] == pytest.approx(2 - stats.t.ppf(0.975, 2) / math.sqrt(3))
    with pytest.raises(ValueError):
        one_sample_t([1.0])


def test_one_sample_t_degenerate_centred():
    res = one_sample_t([-1.0, 1.0, -1.0, 1.0])
    assert res["mean"] == 0 and res["p_value"] == pytest.approx(1.0)


def test_proportion_ci():
    res = proportion_ci(95, 100, p0=0.95)
    assert res["lower"] < 0.95 < res["upper"]
    assert res["p_value"] == pytest.approx(1.0, abs=0.02)
    all_in = proportion_ci(50, 50)
    assert all_in["upper"] == 1.0 and all_in["lower"] == pytest.approx(0.025 ** (1 / 50), rel=1e-9)
    assert proportion_ci(0, 10)["lower"] == 0.0
    with pytest.raises(ValueError):
        proportion_ci(5, 3)


def test_bootstrap_ci_degenerate_and_mean():
    rng = np.random.default_rng(1)
    const = bootstrap_ci(np.full(50, 2.0), np.mean, rng)
    assert const == {"estimate": 2.0, "lower": 2.0, "upper": 2.0}
    x = np.random.default_rng(2).normal(10, 1, 400)
    ci = bootstrap_ci(x, np.mean, rng)
    assert ci["lower"] < 10 < ci["upper"]
    assert ci["upper"] - ci["lower"] == pytest.approx(2 * 1.96 / math.sqrt(400), rel=0.2)


def test_mc_standard_error():
    res = mc_standard_error([1.0, 2.0, 3.0])
    assert res["se"] == 1.0 and res["relative_se"] == 0.5
    with pytest.raises(ValueError):
        mc_standard_error([1.0])
