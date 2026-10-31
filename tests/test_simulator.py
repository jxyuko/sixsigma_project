# test_simulator.py
# Tests for Mode 1 evaluate(), Mode 2 compare() and the Monte Carlo engine (ROADMAP Sections 2, 8, 11a).

import math

import numpy as np
import pytest

from functions.library import load_library
from functions.simulator import (DEFAULT_WARRANTY_HOURS, compare, draw_library, evaluate,
                                 failure_time_check, p_outlasts, qi, reliability_band)

TI_ALL = {
    "ECU MCU": "F280049CPZQR",
    "BMS AFE": "BQ79656PAPRQ1",
    "Digital isolator": "ISO7741QDWRQ1",
    "Temperature sensor": "TMP4719QDGSRQ1",
    "Gate driver": "UCC21750QDWRQ1",
    "Current sensor": "TMCS1101A4UQDRQ1",
}


@pytest.fixture(scope="module")
def lib():
    return load_library()


@pytest.fixture(scope="module")
def draws(lib):
    return draw_library(lib)


def value(table, metric, col="median", slot=None):
    rows = table[table["metric"] == metric]
    if slot is not None:
        rows = rows[rows["slot"] == slot]
    return rows[col].iloc[0]


# --- Known answers ---------------------------------------------------------------------------

def test_known_answer_fit_60pct_bound(lib, draws):
    ev = evaluate({"ECU MCU": "F280049CPZQR"}, 55, draws=draws, library=lib)
    assert value(ev.components, "fit_60pct_bound") == pytest.approx(6.21, abs=0.01)


def test_degenerate_use_at_test_temperature(lib, draws):
    # At T_op = T_test, AF = 1 for every Ea, so FIT is the Gamma(1, n t) median: ln2 / (n t) * 1e9.
    # MC error of an exponential median from 5,000 draws is 1 / (ln2 * sqrt(5000)) = 2.0%; allow ~3.4 SE.
    ev = evaluate({"ECU MCU": "F280049CPZQR"}, 125, draws=draws, library=lib)
    assert value(ev.components, "af_eff") == 1.0
    assert value(ev.components, "fit") == pytest.approx(math.log(2) / 1.9e6 * 1e9, rel=0.07)


def test_median_fit_close_to_mode_ea(lib, draws):
    # With f = 0 the median FIT at 55 C is near ln2 / (n t AF(0.7)) = 4.70 FIT; Ea spread widens the CI
    ev = evaluate({"ECU MCU": "F280049CPZQR"}, 55, draws=draws, library=lib)
    assert value(ev.components, "fit") == pytest.approx(4.70, rel=0.10)
    assert value(ev.components, "fit", "upper") > 3 * value(ev.components, "fit")


# --- System structure (E8-E10, E14) ------------------------------------------------------------

def test_one_slot_system_equals_component(lib, draws):
    ev = evaluate({"Gate driver": "UCC21750QDWRQ1"}, 55, draws=draws, library=lib)
    assert value(ev.system, "fit") == pytest.approx(value(ev.components, "fit"))
    assert np.array_equal(ev.lam_sys, ev.lam["Gate driver"])


def test_system_rate_is_sum_per_draw(lib, draws):
    ev = evaluate(TI_ALL, 55, draws=draws, library=lib)
    assert np.allclose(ev.lam_sys, sum(ev.lam.values()))
    assert len(ev.components["slot"].unique()) == 6


def test_b01_reliability_band(lib, draws):
    ev = evaluate(TI_ALL, 55, draws=draws, library=lib)
    band = reliability_band(ev, [0, value(ev.system, "b01_hours")])
    assert band["median"].iloc[0] == 1.0
    assert band["median"].iloc[1] == pytest.approx(0.999, abs=1e-6)   # R_sys(median B0.1) = 0.999


def test_p_meets_warranty_extremes(lib, draws):
    tiny = evaluate(TI_ALL, 55, t_w=1.0, draws=draws, library=lib)
    huge = evaluate(TI_ALL, 55, t_w=1e9, draws=draws, library=lib)
    assert value(tiny.system, "p_meets_warranty") == 1.0
    assert value(huge.system, "p_meets_warranty") == 0.0


def test_hotter_is_worse(lib, draws):
    cool = evaluate(TI_ALL, 40, draws=draws, library=lib)
    hot = evaluate(TI_ALL, 105, draws=draws, library=lib)
    assert value(hot.system, "b01_hours") < value(cool.system, "b01_hours")
    assert value(hot.system, "p_meets_warranty") <= value(cool.system, "p_meets_warranty")


def test_profile_one_bin_equals_scalar(lib, draws):
    a = evaluate(TI_ALL, 55, draws=draws, library=lib)
    b = evaluate(TI_ALL, [(55, 1.0)], draws=draws, library=lib)
    assert np.allclose(a.lam_sys, b.lam_sys)


def test_profile_worse_than_mean_temperature(lib, draws):
    # E6 Jensen: a 40/70/105 C profile fails sooner than its 62 C mean temperature
    prof = evaluate(TI_ALL, [(40, 0.5), (70, 0.3), (105, 0.2)], draws=draws, library=lib)
    mean = evaluate(TI_ALL, 62, draws=draws, library=lib)
    assert np.all(prof.lam_sys > mean.lam_sys)


# --- Common random numbers and reproducibility (Section 8a) ---------------------------------------

def test_same_part_same_draws_across_configs(lib, draws):
    a = evaluate({"ECU MCU": "F280049CPZQR"}, 55, draws=draws, library=lib)
    b = evaluate(TI_ALL, 55, draws=draws, library=lib)
    assert np.array_equal(a.lam["ECU MCU"], b.lam["ECU MCU"])


def test_family_parts_share_draws(lib, draws):
    # A9: the four C2000 parts have one dataset, so they give identical results
    a = evaluate({"ECU MCU": "F280049CPZQR"}, 55, draws=draws, library=lib)
    b = evaluate({"ECU MCU": "F280025PNQR"}, 55, draws=draws, library=lib)
    assert np.array_equal(a.lam_sys, b.lam_sys)


def test_same_seed_reproduces(lib):
    a = evaluate(TI_ALL, 55, draws=draw_library(lib, n_draws=500, seed=1), library=lib)
    b = evaluate(TI_ALL, 55, draws=draw_library(lib, n_draws=500, seed=1), library=lib)
    c = evaluate(TI_ALL, 55, draws=draw_library(lib, n_draws=500, seed=2), library=lib)
    assert np.array_equal(a.lam_sys, b.lam_sys)
    assert not np.array_equal(a.lam_sys, c.lam_sys)
    assert a.settings["seed"] == 1 and a.settings["n_draws"] == 500


def test_independent_ea_mode(lib):
    shared = draw_library(lib, n_draws=100, ea_mode="shared")
    indep = draw_library(lib, n_draws=100, ea_mode="independent")
    assert np.array_equal(shared.ea["TI C2000"], shared.ea["UCC21750QDWRQ1"])
    assert not np.array_equal(indep.ea["TI C2000"], indep.ea["UCC21750QDWRQ1"])
    with pytest.raises(ValueError):
        draw_library(lib, n_draws=10, ea_mode="other")


# --- Input checks --------------------------------------------------------------------------------

def test_config_errors(lib, draws):
    with pytest.raises(ValueError):
        evaluate({}, 55, draws=draws, library=lib)
    with pytest.raises(ValueError):
        evaluate({"Wiper motor": "F280049CPZQR"}, 55, draws=draws, library=lib)
    with pytest.raises(ValueError):
        evaluate({"Gate driver": "F280049CPZQR"}, 55, draws=draws, library=lib)   # wrong slot
    with pytest.raises(ValueError):
        evaluate({"Temperature sensor": "MAX31730"}, 55, draws=draws, library=lib)   # unusable
    with pytest.raises(KeyError):
        evaluate({"ECU MCU": "NOT-A-PART"}, 55, draws=draws, library=lib)


def test_default_warranty_is_recorded(lib, draws):
    ev = evaluate(TI_ALL, 55, draws=draws, library=lib)
    assert ev.settings["t_w_hours"] == DEFAULT_WARRANTY_HOURS


# --- qi() and the Section 8c failure-time check -----------------------------------------------------

def test_qi_degenerate_constant():
    assert qi(np.full(100, 3.0)) == {"median": 3.0, "lower": 3.0, "upper": 3.0}


def test_failure_time_check_matches_b01():
    # 8c: empirical 0.1% quantile of min_j Exp(lambda_j) vs closed-form B0.1.
    # With 4e6 systems the 0.1% quantile rests on ~4,000 failures, so its relative MC error is ~1.6%.
    empirical, closed = failure_time_check([6e-9, 1e-9, 2e-10], 4_000_000, np.random.default_rng(8))
    assert empirical == pytest.approx(closed, rel=0.05)


# --- Mode 2: compare() (E11, E13) ------------------------------------------------------------------

def diff(cmp, metric, col="delta_median"):
    return cmp.differences.loc[cmp.differences["metric"] == metric, col].iloc[0]


def test_self_comparison_is_neutral(lib, draws):
    # 11a E11/E13: a configuration against itself gives every difference 0 and P = 0.5
    cmp = compare(TI_ALL, TI_ALL, 55, draws=draws, library=lib)
    assert (cmp.differences["delta_median"] == 0).all()
    assert (cmp.differences.dropna()[["delta_lower", "delta_upper"]] == 0).all().all()
    assert cmp.p_b_outlasts_a == 0.5


def test_p_outlasts_closed_form_two_zero_failure_parts(lib, draws):
    # E13 closed form: two zero-failure parts at the same T_test (shared Ea, so the same AF per draw)
    # give P(lambda_B < lambda_A) = D_B / (D_A + D_B). LTC6811-1 (n 37,101) vs BQ79656 (n 101,758).
    cmp = compare({"BMS AFE": "LTC6811-1"}, {"BMS AFE": "BQ79656PAPRQ1"}, 55, draws=draws, library=lib)
    assert cmp.p_b_outlasts_a == pytest.approx(101758 / (101758 + 37101), abs=0.02)


def test_p_outlasts_ties_and_swap():
    a, b = np.array([1.0, 2.0, 3.0, 4.0]), np.array([2.0, 2.0, 1.0, 1.0])
    assert p_outlasts(a, b) == pytest.approx(0.625)            # 2 wins, 1 tie, 1 loss
    assert p_outlasts(a, b) + p_outlasts(b, a) == pytest.approx(1.0)


def test_differences_are_paired_draws(lib, draws):
    # E11 per draw: delta FIT equals the FIT of the swapped slot's difference, draw by draw
    b_cfg = {**TI_ALL, "BMS AFE": "LTC6811-1"}
    cmp = compare(TI_ALL, b_cfg, 55, draws=draws, library=lib)
    per_draw = (cmp.b.lam["BMS AFE"] - cmp.a.lam["BMS AFE"]) * 1e9
    assert diff(cmp, "fit") == pytest.approx(np.median(per_draw))
    assert diff(cmp, "fit", "a_median") == pytest.approx(value(cmp.a.system, "fit"))
    # Less test evidence for LTC6811-1 -> higher FIT, so B is worse and P(B outlasts A) < 0.5
    assert diff(cmp, "fit") > 0
    assert cmp.p_b_outlasts_a < 0.5


def test_compare_different_slots_allowed(lib, draws):
    cmp = compare({"ECU MCU": "F280049CPZQR"}, TI_ALL, 55, draws=draws, library=lib)
    # Adding parts in series can only raise the rate, on every draw
    assert np.all(cmp.b.lam_sys >= cmp.a.lam_sys)
    assert cmp.p_b_outlasts_a == 0.0
    assert cmp.settings["config_a"] == {"ECU MCU": "F280049CPZQR"}
