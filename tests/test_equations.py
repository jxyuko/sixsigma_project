# test_equations.py
# Known-answer and degenerate-case tests for E1-E6 and the Monte Carlo draws (ROADMAP Sections 7, 8, 11a).

import math

import numpy as np
import pytest

from functions.arrhenius import BOLTZMANN_EV, accel_factor, draw_ea, effective_af, kelvin
from functions.evidence import device_hours, draw_lambda, fit, lambda_bound


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


def test_effective_af_vectorized_over_ea_draws():
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


# --- A2: Ea draws --------------------------------------------------------------------------------

def test_ea_draws_triangular():
    ea = draw_ea(200_000, np.random.default_rng(1))
    assert ea.min() >= 0.5 and ea.max() <= 0.9
    assert ea.mean() == pytest.approx(0.7, abs=0.002)   # symmetric triangle: mean = mode


# --- E4 / A5: Gamma failure-rate draws -------------------------------------------------------------

def test_gamma_60th_percentile_is_chi_square_bound():
    # 11a: 60th percentile of 100,000 Gamma(f+1, D) draws within 1% of lambda_0.60
    rng = np.random.default_rng(2)
    for f in (0, 1, 3):
        lam = draw_lambda(f, n=1900, t_hours=1000, size=100_000, rng=rng)
        assert np.quantile(lam, 0.60) == pytest.approx(lambda_bound(f, 1900 * 1000, 0.60), rel=0.01)


def test_gamma_draws_known_answer_ti_c2000_fit():
    # Draws at T_test divided by AF(55 C) reproduce the 6.21 FIT known answer at the 60th percentile
    lam = draw_lambda(0, 1900, 1000, 200_000, np.random.default_rng(3)) / accel_factor(55, 125, 0.7)
    assert fit(np.quantile(lam, 0.60)) == pytest.approx(6.21, rel=0.01)


def test_gamma_mean_and_jeffreys():
    rng = np.random.default_rng(4)
    d = 1e6
    assert draw_lambda(0, 1000, 1000, 200_000, rng).mean() == pytest.approx(1 / d, rel=0.01)
    assert draw_lambda(0, 1000, 1000, 200_000, rng, prior="jeffreys").mean() == pytest.approx(0.5 / d, rel=0.01)


def test_gamma_draws_reject_bad_inputs():
    rng = np.random.default_rng(5)
    with pytest.raises(ValueError):
        draw_lambda(0, 0, 1000, 10, rng)
    with pytest.raises(ValueError):
        draw_lambda(-1, 100, 1000, 10, rng)
