# test_new_inputs.py
# Known answers and degenerate cases for the inputs added 2026-11-15 (ROADMAP Section 2):
# several test groups per part, the operating temperature band, and the Ea range (Monte Carlo, A2).

import math

import numpy as np
import pytest

from functions.arrhenius import accel_factor, effective_af, max_temperature, operating_profile
from functions.candidates import select
from functions.interface import describe_condition, parse_condition, read_candidates


def raw(name, n, slot="Gate driver", t_test=125, f=0, **kw):
    return {"slot": slot, "name": name, "test_temp_c": t_test, "test_hours": 1000, "sample_size": n,
            "failures": f, **kw}


def row(sel, name):
    return sel.candidates.set_index("name").loc[name]


# --- Test groups ---------------------------------------------------------------------------------

def test_groups_known_answer():
    # Two groups: 1,000 devices at 125 C (1 failure) and 500 at 150 C (0 failures), 1,000 h each.
    # D = 1e6 AF(125 -> 55) + 5e5 AF(150 -> 55); r = 1; estimate = 1 / D
    groups = [{"test_temp_c": 125, "test_hours": 1000, "sample_size": 1000, "failures": 1},
              {"test_temp_c": 150, "test_hours": 1000, "sample_size": 500, "failures": 0}]
    sel = select([{"slot": "Gate driver", "name": "g", "groups": groups}], 55, 1000)
    d = 1e6 * accel_factor(55, 125, 0.7) + 5e5 * accel_factor(55, 150, 0.7)
    r = row(sel, "g")
    assert r["test_groups"] == 2 and r["failures"] == 1
    assert r["fit_estimate"] == pytest.approx(1 / d * 1e9)
    assert r["test_temp_c"] == "125/150"


def test_one_group_equals_plain_candidate():
    # Degenerate: a single group gives exactly the plain candidate's result
    g = select([{"slot": "Gate driver", "name": "a", "groups": [{"test_temp_c": 125, "test_hours": 1000,
                                                                 "sample_size": 2000, "failures": 0}]}], 55, 1000)
    p = select([raw("a", 2000)], 55, 1000)
    for k in ("fit_estimate", "fit_lower", "fit_upper", "fit_upper_one_sided"):
        assert row(g, "a")[k] == pytest.approx(row(p, "a")[k])


def test_csv_rows_with_same_name_are_groups(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("slot,name,test_temp_c,test_hours,sample_size,failures,unit_price_usd\n"
                 "Gate driver,X,125,1000,1000,1,5\nGate driver,X,150,500,200,0,\nGate driver,Y,125,1000,10,0,\n")
    cands = read_candidates(f)
    assert len(cands) == 2
    x = next(c for c in cands if c["name"] == "X")
    assert len(x["groups"]) == 2 and x["groups"][1]["test_temp_c"] == 150 and x["unit_price_usd"] == 5


# --- Operating temperature band ---------------------------------------------------------------------

def test_parse_condition():
    assert parse_condition("55") == 55.0
    assert parse_condition("40-105") == (40.0, 105.0)
    assert parse_condition("105 to 40") == (40.0, 105.0)
    assert parse_condition("-20-85") == (-20.0, 85.0)
    assert parse_condition("70-70") == 70.0
    with pytest.raises(ValueError):
        parse_condition("hot")
    assert describe_condition((40.0, 105.0)).startswith("40-105 C")


def test_band_af_known_answer():
    # Time spread evenly over the band: 1/AF_eff = mean of 1/AF(T) over the band (E6), checked against
    # numerical integration
    ts = np.linspace(40, 105, 100_001)
    expected = 1 / np.trapezoid(1 / accel_factor(ts, 125, 0.7), ts) * (105 - 40)
    assert effective_af((40, 105), 125, 0.7) == pytest.approx(expected, rel=1e-4)
    # Hot hours dominate: AF_eff lies between AF(105) and AF(40), far nearer the hot end
    assert accel_factor(105, 125, 0.7) < effective_af((40, 105), 125, 0.7) < accel_factor(72.5, 125, 0.7)


def test_band_degenerate_and_worst_case():
    assert effective_af((55, 55), 125, 0.7) == pytest.approx(accel_factor(55, 125, 0.7))
    assert max_temperature((40, 105)) == 105.0 and max_temperature(55) == 55.0
    assert sum(w for _, w in operating_profile((40, 105))) == pytest.approx(1.0)
    band = select([raw("a", 1000)], (40, 105), 1000)
    hot = select([raw("a", 1000)], 105, 1000)
    assert row(band, "a")["fit_at_max_temp"] == pytest.approx(row(hot, "a")["fit_estimate"])
    assert row(band, "a")["fit_estimate"] < row(hot, "a")["fit_estimate"]
    assert band.combinations.iloc[0]["system_fit_at_max_temp"] == pytest.approx(row(hot, "a")["fit_estimate"])


# --- Ea range (Monte Carlo, A2) ----------------------------------------------------------------------

def test_ea_range_middle_matches_07_and_spread_ordered():
    # Ea ~ triangular(0.5, 0.7, 0.9) is symmetric, so the median estimate over the draws is the 0.7 eV one
    sel = select([raw("a", 1000)], 55, 1000, ea_range=True, n_draws=20_000)
    r = row(sel, "a")
    lam_med = np.median(sel.lam_draws["a"]["estimate"]) * 1e9
    assert lam_med == pytest.approx(r["fit_estimate"], rel=0.02)
    assert r["fit_ea_lower"] < r["fit_estimate"] < r["fit_ea_upper"]
    assert r["fit_full_lower"] <= r["fit_lower"] and r["fit_full_upper"] > r["fit_upper"]
    # Below the test temperature a low Ea gives the high rate: the upper end is near the 0.5 eV value
    assert r["fit_ea_upper"] < row(select([raw("a", 1000)], 55, 1000, ea_ev=0.5), "a")["fit_estimate"]


def test_ea_range_degenerate_at_test_temperature_and_stated_ea():
    # At T_op = T_test, AF = 1 for any Ea: no spread. A stated Ea is never drawn.
    sel = select([raw("a", 1000), raw("b", 1000, ea_ev=0.6)], 125, 1000, ea_range=True, n_draws=2000)
    a, b = row(sel, "a"), row(sel, "b")
    assert a["fit_ea_lower"] == pytest.approx(a["fit_ea_upper"])
    hot = select([raw("b", 1000, ea_ev=0.6)], 55, 1000, ea_range=True, n_draws=2000)
    assert row(hot, "b")["fit_ea_lower"] == pytest.approx(row(hot, "b")["fit_ea_upper"])


def test_ea_shared_vs_separate_and_reproducible():
    cands = [raw("a", 1000), raw("b", 2000, slot="Digital isolator")]
    shared = select(cands, 55, 1000, ea_range=True, n_draws=2000)
    sep = select(cands, 55, 1000, ea_range=True, ea_shared=False, n_draws=2000)
    # Shared: both parts' draws move together (correlation 1); separate: nearly independent
    assert np.corrcoef(shared.lam_draws["a"]["estimate"], shared.lam_draws["b"]["estimate"])[0, 1] > 0.999
    assert abs(np.corrcoef(sep.lam_draws["a"]["estimate"], sep.lam_draws["b"]["estimate"])[0, 1]) < 0.1
    # The system spread is wider when the parts share an Ea (no averaging out)
    s, p = shared.combinations.iloc[0], sep.combinations.iloc[0]
    assert s["system_fit_ea_upper"] - s["system_fit_ea_lower"] > p["system_fit_ea_upper"] - p["system_fit_ea_lower"]
    again = select(cands, 55, 1000, ea_range=True, n_draws=2000)
    assert again.combinations.iloc[0]["system_fit_ea_upper"] == s["system_fit_ea_upper"]


def test_ea_range_target_check_at_unfavourable_end():
    # A part that just meets the target at 0.7 eV fails it at the unfavourable (low) Ea end at 55 C.
    # target rate for R(1000 h) >= 0.999: -ln(0.999)/1000; at 0.7 eV with r = 0 the 95% bound is
    # -ln(0.05) / (n 1000 AF), so pick n just large enough to pass at 0.7 eV
    lam_t = -math.log(0.999) / 1000
    n = math.ceil(-math.log(0.05) / (lam_t * 1000 * accel_factor(55, 125, 0.7))) + 1
    r = row(select([raw("a", n)], 55, 1000, ea_range=True, n_draws=4000), "a")
    assert r["meets_target_at_confidence"] and not r["meets_target_at_ea_worst"]
