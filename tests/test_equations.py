# test_equations.py
# Known-answer and degenerate-case tests for E1-E6 (ROADMAP Sections 7, 11a). Known answers for E4 are the
# worked examples of Recitation 12 "Planning Experiments" (course slides, k-factor tables 3, 4 and 3.7).

import math

import numpy as np
import pytest

from functions.arrhenius import BOLTZMANN_EV, accel_factor, effective_af, kelvin
from functions.evidence import (device_hours, fit, k_factor, lambda_bound, lambda_ci, lambda_hat,
                                lambda_percentile, mttf_hours)


def test_kelvin():
    assert kelvin(0) == 273.15


def test_af_known_answer():
    # E2: Ea 0.7 eV, 125 C test -> 55 C use; the raw table lists 77.6454
    assert accel_factor(t_use_c=55, t_test_c=125, ea_ev=0.7) == pytest.approx(77.6454, rel=1e-4)


def test_af_degenerate_same_temperature():
    assert accel_factor(t_use_c=125, t_test_c=125, ea_ev=0.7) == 1.0


def test_af_hotter_use_is_below_one():
    assert accel_factor(t_use_c=150, t_test_c=125, ea_ev=0.7) < 1.0


def test_lambda_known_answer_ti_c2000():
    # E3-E5: TI F280049, n=1900, t=1000 h, 125 -> 55 C, CL 60%, f=0 -> 6.21 FIT (TI publishes 6.19)
    d = device_hours(n=1900, t_hours=1000, af=accel_factor(55, 125, 0.7))
    assert fit(lambda_bound(f=0, d=d, cl=0.60)) == pytest.approx(6.21, abs=0.01)


def test_lambda_zero_failure_closed_form():
    # E4 with f = 0: chi2(CL; 2) / 2D = -ln(1 - CL) / D
    d = 1.234e9
    assert lambda_bound(f=0, d=d, cl=0.9) == pytest.approx(-math.log(0.1) / d, rel=1e-12)


def test_lambda_increases_with_failures_and_confidence():
    d = 1e9
    assert lambda_bound(1, d, 0.6) > lambda_bound(0, d, 0.6)
    assert lambda_bound(0, d, 0.9) > lambda_bound(0, d, 0.6)


def test_lambda_rejects_bad_inputs():
    with pytest.raises(ValueError):
        lambda_bound(f=0, d=0, cl=0.6)
    with pytest.raises(ValueError):
        lambda_bound(f=0, d=1e9, cl=1.0)


def test_boltzmann_constant():
    assert BOLTZMANN_EV == 8.617333e-5


# --- E6: dynamic AF over a temperature profile ---------------------------------------------------

def test_effective_af_one_bin_equals_single_temperature():
    # Degenerate: a one-bin profile is the single-temperature AF (E2)
    assert effective_af([(55, 1.0)], 125, 0.7) == pytest.approx(accel_factor(55, 125, 0.7), rel=1e-12)
    assert effective_af(55, 125, 0.7) == pytest.approx(accel_factor(55, 125, 0.7), rel=1e-12)


def test_effective_af_known_answer_and_jensen():
    # ROADMAP Section 3 example: 40/70/105 C at 50/30/20% -> AF_eff 12.3, vs 46.3 at the 62 C mean
    profile = [(40, 0.5), (70, 0.3), (105, 0.2)]
    af_eff = effective_af(profile, 125, 0.7)
    assert af_eff == pytest.approx(12.29, abs=0.01)
    assert accel_factor(62, 125, 0.7) == pytest.approx(46.30, abs=0.01)
    # Averaging rates gives a higher rate (lower AF) than the mean temperature
    assert af_eff < accel_factor(62, 125, 0.7)


def test_effective_af_matches_arrhenius_average_temperature():
    # Tencer et al. (2004): exp(-Ea/kT_aa) = sum w_i exp(-Ea/kT_i); AF_eff = AF(T_aa)
    profile = [(40, 0.5), (70, 0.3), (105, 0.2)]
    ea = 0.7
    temps, w = np.array([40, 70, 105]) + 273.15, np.array([0.5, 0.3, 0.2])
    t_aa = -ea / (BOLTZMANN_EV * np.log(np.sum(w * np.exp(-ea / (BOLTZMANN_EV * temps)))))
    assert effective_af(profile, 125, ea) == pytest.approx(accel_factor(t_aa - 273.15, 125, ea), rel=1e-10)


def test_effective_af_vectorized_over_ea_values():
    ea = np.array([0.5, 0.7, 0.9])
    profile = [(40, 0.5), (105, 0.5)]
    out = effective_af(profile, 125, ea)
    assert out.shape == (3,)
    assert out[1] == pytest.approx(effective_af(profile, 125, 0.7))
    assert np.all(np.diff(out) > 0)   # higher Ea, more acceleration below T_test


def test_profile_rejects_bad_weights():
    with pytest.raises(ValueError):
        effective_af([(40, 0.5), (70, 0.4)], 125, 0.7)
    with pytest.raises(ValueError):
        effective_af([(40, 1.5), (70, -0.5)], 125, 0.7)


# --- E4: the course's exponential estimate and confidence bounds (Recitation 12) -------------------

def test_k_factors_recitation_examples_1_2_6():
    # Example 1: r = 20, two-sided 95% -> k = 0.6108, 1.5444; Example 2: one-sided 95% -> 1.4531
    assert k_factor(0.025, 20) == pytest.approx(0.6108, abs=1e-4)
    assert k_factor(0.975, 20) == pytest.approx(1.5444, abs=1e-4)
    assert k_factor(0.95, 20) == pytest.approx(1.4531, abs=1e-4)
    # Example 6: r = 25, two-sided 90% -> 0.6953, 1.3966
    assert k_factor(0.05, 25) == pytest.approx(0.6953, abs=1e-4)
    assert k_factor(0.95, 25) == pytest.approx(1.3966, abs=1e-4)


def test_ci_recitation_example_7():
    # Example 7: lambda_hat = 200 FIT from r = 3 failures, Type I: 95% CI 41.2 - 584.5 FIT
    d = 3 / 200e-9
    ci = lambda_ci(3, d)
    assert fit(ci["estimate"]) == pytest.approx(200)
    assert fit(ci["lower"]) == pytest.approx(41.2, abs=0.05)
    assert fit(ci["upper"]) == pytest.approx(584.5, abs=0.05)


def test_zero_failures_recitation_example_8():
    # Example 8: 0 failures in 1,600,000 unit-hours: 50% estimate 433.2 FIT, 95% bound 1,872.3, 70% bound 752.5
    d = 200 * 5000 + 200 * 3000
    assert fit(lambda_hat(0, d)) == pytest.approx(433.2, abs=0.05)
    assert fit(lambda_percentile(0.95, 0, d)) == pytest.approx(1872.3, abs=0.05)
    assert fit(lambda_percentile(0.70, 0, d)) == pytest.approx(752.5, abs=0.05)


def test_zero_failure_factors_table_3_7():
    # Table 3.7: k0 = -ln(alpha) for the 50, 60, 80, 90, 95, 97.5, 99th percentiles
    for p, k0 in ((0.5, 0.6931), (0.6, 0.9163), (0.8, 1.6094), (0.9, 2.3026), (0.95, 2.9957),
                  (0.975, 3.6889), (0.99, 4.6052)):
        assert lambda_percentile(p, 0, 1.0) == pytest.approx(k0, abs=1e-4)


def test_zero_failure_lower_bound_is_zero():
    # r = 0: chi2 with 2r = 0 degrees of freedom, so the lower bound is 0 (Table 4 starts at r = 1)
    assert lambda_percentile(0.025, 0, 1e6) == 0.0
    assert lambda_ci(0, 1e6)["lower"] == 0.0
    assert mttf_hours(0.0) == float("inf")


def test_estimate_and_bounds_ordered_and_scale_with_evidence():
    for r in (0, 1, 5):
        ci = lambda_ci(r, 1e9)
        assert ci["lower"] < ci["estimate"] < ci["upper"]
    # Degenerate: 10x the device-hours, same failures -> every value 10x lower
    a, b = lambda_ci(2, 1e8), lambda_ci(2, 1e9)
    for k in a:
        assert a[k] == pytest.approx(10 * b[k])


def test_upper_percentile_equals_supplier_bound():
    # The 60th percentile is the supplier chi-square bound (E4), so TI C2000 gives 6.21 FIT at 55 C
    d = device_hours(1900, 1000, accel_factor(55, 125, 0.7))
    assert fit(lambda_percentile(0.60, 0, d)) == pytest.approx(6.21, abs=0.01)
    assert lambda_percentile(0.6, 3, 1e9) == pytest.approx(lambda_bound(3, 1e9, 0.6))


def test_estimate_inputs_rejected():
    with pytest.raises(ValueError):
        lambda_hat(-1, 1e6)
    with pytest.raises(ValueError):
        lambda_percentile(0.5, 0, 0)
    with pytest.raises(ValueError):
        k_factor(0.95, 0)
    assert mttf_hours(1e-6) == pytest.approx(1e6)


def test_lambda_increases_with_use_temperature():
    # 11a E4 monotone in T_op: the 60% bound rises at every step of a 25-125 C grid
    temps = np.arange(25, 126, 5)
    lam = [lambda_bound(0, device_hours(1900, 1000, accel_factor(t, 125, 0.7)), 0.60) for t in temps]
    assert np.all(np.diff(lam) > 0)
