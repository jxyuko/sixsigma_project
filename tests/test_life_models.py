# test_life_models.py
# Known answers and degenerate cases for the lognormal and Weibull alternatives (ROADMAP E24-E26, A16):
# each model is matched to the test's expected failures and reported as its AFR over the mission.

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from functions.candidates import select
from functions.life_models import (LOGNORMAL_SIGMA, WEIBULL_BETA, lognormal_cum_hazard, lognormal_t50,
                                   mission_afr)

ROOT = Path(__file__).resolve().parents[1]


def raw(name, n, slot="Gate driver", t_test=125, f=0, **kw):
    return {"slot": slot, "name": name, "test_temp_c": t_test, "test_hours": 1000, "sample_size": n,
            "failures": f, **kw}


def test_shapes_from_sematech():
    # A16: sigma 0.5 (wear-out) and 1.5 (defects); beta = 1.2 / sigma
    assert LOGNORMAL_SIGMA == {"wear-out": 0.5, "defects": 1.5}
    assert WEIBULL_BETA["wear-out"] == pytest.approx(2.4) and WEIBULL_BETA["defects"] == pytest.approx(0.8)


def test_weibayes_known_answer():
    # One group, n = 1,000 devices, t = 1e5 equivalent hours, zero failures, mu = ln 2 (the 50% estimate):
    # eta^beta = n t^beta / mu, so H(m) = mu (m / t)^beta / n and AFR = H(m) / m
    n, t, m, beta, mu = 1000, 1e5, 3000, 2.4, math.log(2)
    expected = mu * (m / t) ** beta / n / m
    assert mission_afr("weibull", [(n, t)], mu, m, beta) == pytest.approx(expected, rel=1e-12)


def test_weibull_beta_one_is_exponential():
    # Degenerate: beta = 1 gives exactly the exponential mu / D, also through select()
    units = [(500, 2e4), (300, 5e4)]
    assert mission_afr("weibull", units, 2.0, 1234, 1.0) == pytest.approx(mission_afr("exponential", units, 2.0, 1234))
    a = select([raw("a", 1000)], 55, 2920, life_model="weibull", shape=1.0).candidates.iloc[0]
    b = select([raw("a", 1000)], 55, 2920).candidates.iloc[0]
    for k in ("fit_estimate", "fit_upper", "fit_upper_one_sided"):
        assert a[k] == pytest.approx(b[k], rel=1e-9)


def test_lognormal_reproduces_the_test_evidence():
    # E25: the fitted t50 makes the summed cumulative hazards over the test groups equal mu
    units, sigma = [(400, 3e4), (100, 9e4)], 1.5
    for mu in (0.693, 3.689, 7.0):
        t50 = lognormal_t50(units, mu, sigma)
        assert sum(n * lognormal_cum_hazard(t, t50, sigma) for n, t in units) == pytest.approx(mu, rel=1e-6)


def test_zero_mu_gives_zero_rate_and_arrays_work():
    for model in ("exponential", "lognormal", "weibull"):
        assert mission_afr(model, [(100, 1e4)], 0.0, 1000) == 0.0
    # Vectorized over Ea draws (one t per draw) equals the scalar results
    ts = np.array([1e4, 5e4])
    vec = mission_afr("lognormal", [(100, ts)], 0.693, 1000, 1.5)
    assert vec[1] == pytest.approx(mission_afr("lognormal", [(100, 5e4)], 0.693, 1000, 1.5), rel=1e-9)


def test_wearout_shapes_are_less_conservative_below_the_test_time():
    # Mission (2,920 h) far below the equivalent test time (~78,000 h): beta > 1 and small sigma give fewer
    # failures than the exponential; beta < 1 gives more
    sel = {m: select([raw("a", 1900)], 55, 2920, life_model=m[0], shape=m[1]).candidates.iloc[0]["fit_estimate"]
           for m in (("exponential", None), ("weibull", 2.4), ("weibull", 0.8), ("lognormal", 0.5))}
    exp = sel[("exponential", None)]
    assert sel[("weibull", 2.4)] < exp < sel[("weibull", 0.8)]
    assert sel[("lognormal", 0.5)] < exp


def test_life_model_errors():
    with pytest.raises(ValueError):
        select([raw("a", 1000)], 55, 1000, life_model="gamma")
    with pytest.raises(ValueError):
        mission_afr("weibull", [(10, 1e3)], -1, 1000)


def test_compare_script_runs():
    out = subprocess.run([sys.executable, str(ROOT / "code" / "03_compare_life_models.py"), "--temp", "55",
                          "--hours", "2920"], capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert out.returncode == 0, out.stderr
    assert "Do the picks agree across the models?" in out.stdout and "Weibull, beta 0.8" in out.stdout
