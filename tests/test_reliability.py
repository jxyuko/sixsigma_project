# test_reliability.py
# Known-answer and degenerate-case tests for E7-E10 and E14 (ROADMAP Sections 7 and 11a).

import math

import numpy as np
import pytest

from functions.evidence import fit
from functions.reliability import (b_life, density, hazard, p_meets_warranty, reliability,
                                   series_lambda, unreliability, warranty_ratio)

LAM = 6.21e-9   # TI C2000 at 55 C, failures per hour


# --- E7: life functions --------------------------------------------------------------------------

def test_life_functions_known_values():
    t = 1 / LAM   # at t = MTTF, R = e^-1
    assert reliability(LAM, t) == pytest.approx(math.exp(-1))
    assert unreliability(LAM, t) == pytest.approx(1 - math.exp(-1))
    assert density(LAM, t) == pytest.approx(LAM * math.exp(-1))
    assert hazard(LAM, t) == LAM


def test_life_functions_degenerate():
    # t = 0: everything works; lambda = 0: nothing ever fails
    assert reliability(LAM, 0) == 1.0
    assert unreliability(LAM, 0) == 0.0
    assert reliability(0.0, 1e9) == 1.0


def test_unreliability_precise_for_tiny_rates():
    # F = lambda t to first order; expm1 keeps precision where 1 - exp() would round to 0
    assert unreliability(1e-15, 1.0) == pytest.approx(1e-15, rel=1e-9)


def test_hazard_is_constant_over_time():
    assert np.all(hazard(LAM, np.array([0, 1e3, 1e6])) == LAM)


# --- E8: series system ----------------------------------------------------------------------------

def test_series_one_slot_is_that_part():
    assert series_lambda([LAM]) == LAM


def test_series_fit_is_sum_of_component_fits():
    lams = [6.21e-9, 0.116e-9, 0.135e-9]
    assert fit(series_lambda(lams)) == pytest.approx(sum(fit(l) for l in lams))


def test_series_reliability_is_product():
    lams, t = [6.21e-9, 0.116e-9, 0.135e-9], 50_000
    assert reliability(series_lambda(lams), t) == pytest.approx(np.prod([reliability(l, t) for l in lams]))


def test_series_quantities_and_draw_arrays():
    a, b = np.array([1e-9, 2e-9]), np.array([3e-9, 4e-9])
    assert np.allclose(series_lambda([a, b], qty=[2, 1]), [5e-9, 8e-9])


def test_series_rejects_bad_inputs():
    with pytest.raises(ValueError):
        series_lambda([])
    with pytest.raises(ValueError):
        series_lambda([LAM, LAM], qty=[1])


# --- E9: B-life -------------------------------------------------------------------------------

def test_b01_reliability_is_0999():
    lam_sys = 7e-9
    assert reliability(lam_sys, b_life(lam_sys)) == pytest.approx(0.999, rel=1e-12)


def test_b01_known_answer():
    # B0.1 = 0.0010005 / lambda_sys; TI C2000 alone at 55 C -> about 161,000 h
    assert b_life(LAM) == pytest.approx(0.0010005003335835 / LAM, rel=1e-9)
    assert b_life(LAM) == pytest.approx(161_111, rel=1e-3)


def test_b_life_rejects_bad_p():
    with pytest.raises(ValueError):
        b_life(LAM, p=0)


# --- E10 and E14: warranty ---------------------------------------------------------------------

def test_warranty_ratio_degenerate():
    # A warranty exactly at B0.1 gives WR = 1, which counts as meeting it
    b = b_life(LAM)
    assert warranty_ratio(b, b) == pytest.approx(1.0)
    assert p_meets_warranty(np.array([1.0])) == 1.0


def test_p_meets_warranty_known_share():
    assert p_meets_warranty(np.array([0.5, 0.9, 1.0, 2.0])) == 0.5
    assert p_meets_warranty(np.zeros(10)) == 0.0


def test_warranty_ratio_rejects_bad_hours():
    with pytest.raises(ValueError):
        warranty_ratio(1e5, 0)
