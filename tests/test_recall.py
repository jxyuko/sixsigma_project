# test_recall.py
# Recall risk from reliability (ROADMAP E30-E31, A18-A19) and quantities in combination_costs (A10).

import math

import numpy as np
import pytest
from scipy.stats import poisson

from functions.candidates import select
from functions.finance import combination_costs, recall_probability, recall_risk


def raw(name, n, slot="Gate driver", f=0, **kw):
    return {"slot": slot, "name": name, "test_temp_c": 125, "test_hours": 1000, "sample_size": n,
            "failures": f, **kw}


def test_recall_probability_known_answers():
    # k = 1: P(X >= 1) = 1 - exp(-mu); mu = ln 2 gives 0.5
    assert recall_probability(math.log(2), 1) == pytest.approx(0.5)
    # mu = 3, k = 10: 1 - P(X <= 9) for Poisson(3) = 0.001102 (hand: 1 - sum e^-3 3^j / j!, j = 0..9)
    hand = 1 - sum(math.exp(-3) * 3 ** j / math.factorial(j) for j in range(10))
    assert recall_probability(3.0, 10) == pytest.approx(hand) == pytest.approx(0.0011025, rel=1e-3)
    # mu = 12, k = 10: about 0.758 (the worked example given to the team)
    assert recall_probability(12.0, 10) == pytest.approx(0.7576, abs=1e-3)


def test_recall_probability_degenerate_and_errors():
    assert recall_probability(0.0, 1) == 0.0                     # no expected failures, no recall
    assert np.allclose(recall_probability(np.array([0.0, 3.0]), 10), [0.0, poisson.sf(9, 3.0)])
    for k in (0, 2.5):
        with pytest.raises(ValueError):
            recall_probability(1.0, k)
    with pytest.raises(ValueError):
        recall_probability(-1.0, 3)


def test_recall_risk_known_answer_two_slots():
    sel = select([raw("gd", 1000, qty_per_vehicle=6), raw("iso", 2000, slot="Digital isolator", qty_per_vehicle=2)],
                 55, 2920)
    out = recall_risk(sel, ["gd", "iso"], k=5, cost_per_vehicle=440.0, fleet_size=100_000)
    mus = {r["part"]: r["expected_failures"] for r in out["parts"]}
    for name, q in (("gd", 6), ("iso", 2)):
        assert mus[name] == pytest.approx(100_000 * (1 - math.exp(-q * sel.lam[name]["estimate"] * 2920)))
    ps = [poisson.sf(4, mus["gd"]), poisson.sf(4, mus["iso"])]
    assert out["p_any_recall"] == pytest.approx(1 - (1 - ps[0]) * (1 - ps[1]))
    assert out["expected_recall_cost"] == pytest.approx(sum(ps) * 100_000 * 440.0)


def test_recall_risk_rises_with_failure_rate_and_bounds_order():
    # A less reliable part (smaller test -> higher rate) carries more recall risk; the upper bound case
    # carries more risk than the estimate, the lower bound less (0 with zero failures)
    sel = select([raw("big", 100_000), raw("small", 1_000, slot="Digital isolator")], 55, 2920)
    big = recall_risk(sel, ["big"], 3, 440.0, 1_000_000)
    small = recall_risk(sel, ["small"], 3, 440.0, 1_000_000)
    assert small["p_any_recall"] > big["p_any_recall"]
    lo, est, hi = (recall_risk(sel, ["small"], 3, 440.0, 1_000_000, case=c)["expected_recall_cost"]
                   for c in ("lower", "estimate", "upper"))
    assert lo == 0.0 and lo < est < hi


def test_combination_costs_use_quantities():
    sel = select([raw("gd", 1000, qty_per_vehicle=6, unit_price_usd=5.0)], 55, 2920)
    c = combination_costs(sel, ["gd"])
    lam = sel.lam["gd"]["estimate"]
    assert c["purchase_cost"] == pytest.approx(1000 * 6 * 5.0)
    assert c["warranty_cost"] == pytest.approx(1000 * 6 * (1 - math.exp(-lam * 2920)) * 5.0)
    assert c["failures"] == pytest.approx(1000 * (1 - math.exp(-6 * lam * 2920)))
