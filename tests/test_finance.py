# test_finance.py
# Known answers and degenerate cases for functions/finance.py (ROADMAP Section 10, E12, E22-E23).

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from functions.finance import break_even_repair_cost, combination_costs, compare_costs, qi_cost


def fake_selection(lams, prices, costs=None, fleet=1000, t_w=1000.0):
    """A minimal select() result: per-draw rates and a candidate table."""
    names = list(lams)
    table = pd.DataFrame({"name": names, "unit_price_usd": [prices[n] for n in names],
                          "cost_per_failure": [(costs or prices)[n] for n in names]})
    return SimpleNamespace(candidates=table, lam={n: np.asarray(v, float) for n, v in lams.items()},
                           settings={"fleet_size": fleet, "warranty_hours": t_w})


def test_qi_cost_known_and_degenerate():
    q = qi_cost(np.arange(1, 1002))
    assert q["estimate"] == 501 and q["lower"] == pytest.approx(26) and q["upper"] == pytest.approx(976)
    const = qi_cost(np.full(10, 5.0))
    assert const == {"estimate": 5.0, "se": 0.0, "lower": 5.0, "upper": 5.0}


def test_combination_costs_known_answer():
    # Two parts, constant rates: failures = N (1 - exp(-lambda t)); warranty = sum N F_i C_i
    sel = fake_selection({"a": [1e-6, 1e-6], "b": [2e-6, 2e-6]}, {"a": 10.0, "b": 5.0})
    c = combination_costs(sel, ["a", "b"])
    f_a, f_b, f_sys = (-np.expm1(-x * 1000) for x in (1e-6, 2e-6, 3e-6))
    assert c["failures"][0] == pytest.approx(1000 * f_sys)
    assert c["warranty_cost"][0] == pytest.approx(1000 * (f_a * 10 + f_b * 5))
    assert c["purchase_cost"][0] == 15_000
    assert c["total_cost"][0] == pytest.approx(15_000 + c["warranty_cost"][0])


def test_compare_costs_degenerate_same_choice():
    sel = fake_selection({"a": np.linspace(1e-7, 1e-6, 100)}, {"a": 3.0})
    c = combination_costs(sel, ["a"])
    out = compare_costs(c, c)
    assert out["saving_total_cost"] == {"estimate": 0.0, "se": 0.0, "lower": 0.0, "upper": 0.0}
    assert out["p_after_cheaper"] == 0.0


def test_compare_costs_paired_saving():
    # 'after' has half the rate in every draw and the same price: it always saves
    lam = np.linspace(1e-7, 1e-6, 200)
    sel = fake_selection({"old": lam, "new": lam / 2}, {"old": 4.0, "new": 4.0}, costs={"old": 100.0, "new": 100.0})
    out = compare_costs(combination_costs(sel, ["old"]), combination_costs(sel, ["new"]))
    assert out["p_after_cheaper"] == 1.0 and out["p_after_fewer_failures"] == 1.0
    assert out["saving_purchase_cost"]["estimate"] == 0.0
    assert out["saving_total_cost"]["lower"] > 0


def test_break_even_known_answer():
    # Premium 10 per 1,000 vehicles, 0.5 failures avoided per draw -> C* = 20
    before = {"purchase_cost": np.full(4, 100.0), "failures": np.full(4, 1.0)}
    after = {"purchase_cost": np.full(4, 110.0), "failures": np.full(4, 0.5)}
    be = break_even_repair_cost(before, after)
    assert be["estimate"] == pytest.approx(20.0) and be["share_draws_avoiding_failures"] == 1.0


def test_break_even_when_change_is_cheaper():
    before = {"purchase_cost": np.full(3, 100.0), "failures": np.full(3, 1.0)}
    after = {"purchase_cost": np.full(3, 90.0), "failures": np.full(3, 0.5)}
    be = break_even_repair_cost(before, after)
    assert be["pays_off_at_any_repair_cost"] and be["estimate"] == 0.0 and be["premium"] == -10.0
