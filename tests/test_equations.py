# test_equations.py
# Known-answer and degenerate-case tests for E1-E5 (ROADMAP Sections 7 and 11a).

import math

import pytest

from functions.arrhenius import BOLTZMANN_EV, accel_factor, kelvin
from functions.evidence import device_hours, fit, lambda_bound


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
