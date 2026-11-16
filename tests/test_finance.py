# test_finance.py
# Known answers and degenerate cases for functions/finance.py (ROADMAP Section 10, E12, E22-E23).

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from functions.finance import break_even_replacement_cost, combination_costs, compare_costs


def fake_selection(lams, prices, costs=None, fleet=1000, t_w=1000.0):
    """A minimal select() result: rates per case and a candidate table."""
    names = list(lams)
    table = pd.DataFrame({"name": names, "unit_price_usd": [prices[n] for n in names],
                          "cost_per_failure": [(costs or prices)[n] for n in names]})
    lam = {n: {"estimate": v, "lower": v / 10, "upper": v * 5} for n, v in lams.items()}
    return SimpleNamespace(candidates=table, lam=lam, settings={"fleet_size": fleet, "warranty_hours": t_w})


def test_combination_costs_known_answer():
    # Two parts: failures = N (1 - exp(-lambda t)); warranty = sum N F_i C_i
    sel = fake_selection({"a": 1e-6, "b": 2e-6}, {"a": 10.0, "b": 5.0})
    c = combination_costs(sel, ["a", "b"])
    f_a, f_b, f_sys = (-np.expm1(-x * 1000) for x in (1e-6, 2e-6, 3e-6))
    assert c["failures"] == pytest.approx(1000 * f_sys)
    assert c["warranty_cost"] == pytest.approx(1000 * (f_a * 10 + f_b * 5))
    assert c["purchase_cost"] == 15_000
    assert c["total_cost"] == pytest.approx(15_000 + c["warranty_cost"])


def test_combination_costs_cases_use_the_bounds():
    sel = fake_selection({"a": 1e-6}, {"a": 10.0})
    est, lo, hi = (combination_costs(sel, ["a"], case) for case in ("estimate", "lower", "upper"))
    assert lo["failures"] < est["failures"] < hi["failures"]
    assert lo["purchase_cost"] == est["purchase_cost"] == hi["purchase_cost"]      # fixed prices
    assert hi["failures"] == pytest.approx(1000 * -np.expm1(-5e-6 * 1000))
    with pytest.raises(ValueError):
        combination_costs(sel, ["a"], "median")


def test_compare_costs_degenerate_same_choice():
    sel = fake_selection({"a": 1e-6}, {"a": 3.0})
    c = combination_costs(sel, ["a"])
    out = compare_costs(c, c)
    assert all(out[f"saving_{k}"] == 0 for k in ("failures", "warranty_cost", "purchase_cost", "total_cost"))


def test_compare_costs_saving_known_answer():
    # 'after' has half the rate and the same price: saving = warranty difference only
    sel = fake_selection({"old": 2e-6, "new": 1e-6}, {"old": 4.0, "new": 4.0}, costs={"old": 100.0, "new": 100.0})
    out = compare_costs(combination_costs(sel, ["old"]), combination_costs(sel, ["new"]))
    assert out["saving_purchase_cost"] == 0.0
    assert out["saving_total_cost"] == pytest.approx(100 * 1000 * (-np.expm1(-2e-3) + np.expm1(-1e-3)))


def test_break_even_known_answer():
    # Premium 10 per 1,000 vehicles, 0.5 failures avoided -> C* = 20
    be = break_even_replacement_cost({"purchase_cost": 100.0, "failures": 1.0},
                                     {"purchase_cost": 110.0, "failures": 0.5})
    assert be["break_even"] == pytest.approx(20.0) and not be["pays_off_at_any_replacement_cost"]


def test_break_even_degenerate():
    cheaper = break_even_replacement_cost({"purchase_cost": 100.0, "failures": 1.0},
                                          {"purchase_cost": 90.0, "failures": 0.5})
    assert cheaper["pays_off_at_any_replacement_cost"] and cheaper["break_even"] == 0.0
    none_avoided = break_even_replacement_cost({"purchase_cost": 100.0, "failures": 1.0},
                                               {"purchase_cost": 110.0, "failures": 1.0})
    assert none_avoided["break_even"] == float("inf")
