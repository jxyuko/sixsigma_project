# test_life_models.py
# Known answers and degenerate cases for the lognormal and Weibull alternatives (ROADMAP E24-E26, A16).

import math

import numpy as np
import pytest
from scipy import stats

from functions.evidence import lambda_percentile
from functions.life_models import (LOGNORMAL_SIGMA, WEIBULL_BETA, fraction_failed, mission_unreliability, scale,
                                   series_unreliability, unreliability)


def test_shapes_from_sematech():
    # A16: sigma 0.5 (wear-out) and 1.5 (defects); beta = 1.2 / sigma
    assert LOGNORMAL_SIGMA == {"wear-out": 0.5, "defects": 1.5}
    assert WEIBULL_BETA["wear-out"] == pytest.approx(2.4) and WEIBULL_BETA["defects"] == pytest.approx(0.8)


def test_fraction_failed_known_answers():
    assert fraction_failed(0, 100) == pytest.approx(1 - 0.5 ** 0.01)              # 50% zero-failure estimate
    assert fraction_failed(0, 100, 0.95) == pytest.approx(1 - 0.05 ** 0.01)       # 1 - alpha^(1/n)
    assert fraction_failed(3, 100) == 0.03
    assert fraction_failed(3, 100, 0.975) == pytest.approx(stats.beta.ppf(0.975, 4, 97))   # Clopper-Pearson
    assert fraction_failed(3, 100, 0.025) == pytest.approx(stats.beta.ppf(0.025, 3, 98))
    assert fraction_failed(0, 100, 0.025) == 0.0                                  # degenerate lower bound
    with pytest.raises(ValueError):
        fraction_failed(5, 3)


def test_exponential_matches_course_zero_failure_formula():
    # With r = 0 the exponential version is exactly the course formula -ln(1 - p) / (n t_eq)
    n, t_eq = 1900, 1000 * 77.6454
    for p in (0.5, 0.95, 0.975):
        f = mission_unreliability("exponential", 0, n, t_eq, 2920, p=p)
        assert f == pytest.approx(-math.expm1(-lambda_percentile(p, 0, n * t_eq) * 2920), rel=1e-9)


def test_weibull_beta_one_is_exponential():
    # Degenerate: Weibull with beta = 1 is the exponential
    a = mission_unreliability("weibull", 0, 500, 1e5, 3000, shape=1.0, p=0.9)
    b = mission_unreliability("exponential", 0, 500, 1e5, 3000, p=0.9)
    assert a == pytest.approx(b, rel=1e-12)


def test_every_model_passes_through_the_test_point():
    # Each fitted model gives F(t_eq) = the test's estimated fraction failed
    f_test, t_eq = 0.002, 5e4
    for model, shape in (("exponential", None), ("weibull", 2.4), ("lognormal", 0.5), ("lognormal", 1.5)):
        assert unreliability(model, t_eq, scale(model, f_test, t_eq, shape), shape) == pytest.approx(f_test)


def test_wearout_shapes_are_less_conservative_below_the_test_time():
    # Extrapolating from t_eq down to a shorter mission, beta > 1 and small sigma give fewer failures
    n, t_eq, t = 1900, 7.8e4, 2920
    f_exp = mission_unreliability("exponential", 0, n, t_eq, t)
    assert mission_unreliability("weibull", 0, n, t_eq, t, WEIBULL_BETA["wear-out"]) < f_exp
    assert mission_unreliability("lognormal", 0, n, t_eq, t, LOGNORMAL_SIGMA["wear-out"]) < f_exp
    assert mission_unreliability("weibull", 0, n, t_eq, t, WEIBULL_BETA["defects"]) > f_exp


def test_series_unreliability():
    assert series_unreliability([0.1, 0.2]) == pytest.approx(1 - 0.9 * 0.8)
    assert series_unreliability([0.0, 0.0]) == 0.0
    assert series_unreliability(np.array([0.01])) == pytest.approx(0.01)
