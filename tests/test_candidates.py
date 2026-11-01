# test_candidates.py
# Mode 3 supplier selection (ROADMAP Section 2 Mode 3, E15-E17, A11-A12): known answers and
# degenerate cases.

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from functions.arrhenius import accel_factor
from functions.candidates import (clean_candidates, default_ea, library_candidate, p_best, select,
                                  evidence_device_hours)
from functions.interface import read_candidates

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "data" / "examples" / "candidates_example.csv"


def raw(name, n, slot="Gate driver", t_test=125, f=0, **kw):
    return {"slot": slot, "name": name, "test_temp_c": t_test, "test_hours": 1000, "sample_size": n,
            "failures": f, **kw}


def row(sel, name):
    return sel.candidates.set_index("name").loc[name]


# --- E15: report summary -> test evidence ---------------------------------------------------------

def test_summary_fit_recovers_device_hours():
    # Known answer: TI C2000 publishes ~6.21 FIT at 55 C, 60%, f = 0, from n t = 1.9e6 at 125 C
    c = {"name": "C2000", "test_temp_c": 125, "fit": 6.211035, "ref_temp_c": 55, "conf_level": 0.6}
    nt, source = evidence_device_hours(c, 0.7)
    assert nt == pytest.approx(1.9e6, rel=1e-5)
    assert source == "report FIT"


def test_summary_mttf_equals_fit():
    by_fit = evidence_device_hours({"name": "a", "test_temp_c": 125, "fit": 2.0, "ref_temp_c": 55}, 0.7)[0]
    by_mttf = evidence_device_hours({"name": "b", "test_temp_c": 125, "mttf_hours": 5e8, "ref_temp_c": 55}, 0.7)[0]
    assert by_fit == pytest.approx(by_mttf)


def test_summary_at_test_temperature_degenerate():
    # FIT stated at the test temperature itself: AF = 1, f = 0, CL 0.6 -> n t = -ln(0.4) / lambda
    nt = evidence_device_hours({"name": "a", "test_temp_c": 125, "fit": 1000}, 0.7)[0]
    assert nt == pytest.approx(-math.log(0.4) / 1e-6, rel=1e-9)


# --- E16: P(best) ---------------------------------------------------------------------------------

def test_p_best_degenerate():
    x = np.array([[1.0, 1.0], [2.0, 2.0]])
    assert p_best(x) == pytest.approx([0.5, 0.5])           # identical candidates split evenly
    assert p_best(np.array([[3.0], [1.0]])) == pytest.approx([1.0])
    assert p_best(np.random.default_rng(1).random((100, 4))).sum() == pytest.approx(1.0)


def test_p_best_closed_form_three_zero_failure_candidates():
    # Zero-failure candidates at the same test temperature share an AF per draw, so
    # lambda_i ~ Exp(D_i) / AF and P(i is lowest) = D_i / sum D. n = 1,000 / 2,000 / 7,000 -> 0.1 / 0.2 / 0.7
    cands = [raw("a", 1000), raw("b", 2000), raw("c", 7000)]
    sel = select(cands, 55, 1000, n_draws=20_000)
    assert [row(sel, n)["p_best_in_slot"] for n in "abc"] == pytest.approx([0.1, 0.2, 0.7], abs=0.015)


# --- E17: reliability requirement ------------------------------------------------------------------

def test_r_lower_bound_known_answer():
    # At T_op = T_test, AF = 1 for any Ea. lambda ~ Exp(D), so the 95% lower bound on R(t) is
    # exp(-t * -ln(0.05) / D). D = 1e6, t = 1000 -> 0.997009
    sel = select([raw("a", 1000)], 125, 1000, n_draws=50_000)
    assert sel.settings["confidence"] == 0.95
    expected = math.exp(-1000 * -math.log(0.05) / 1e6)
    assert 1 - row(sel, "a")["r_mission_lower_bound"] == pytest.approx(1 - expected, rel=0.03)


def test_meets_target_consistent_with_probability():
    sel = select([raw("a", 87285), raw("b", 231)], 55, 1000, target_r=0.999)
    for _, r in sel.candidates.iterrows():
        # Meeting the target with 95% confidence <=> P(R >= target) >= 0.95 (up to MC ties)
        assert r["meets_target_at_confidence"] == (r["p_meets_target"] >= 0.95)


# --- E12: warranty exposure --------------------------------------------------------------------

def test_warranty_exposure_scales_with_fleet_and_cost():
    a = select([raw("a", 1000)], 55, 1000, fleet_size=1000, cost_per_failure=1.0)
    b = select([raw("a", 1000)], 55, 1000, fleet_size=2000, cost_per_failure=500.0)
    ra, rb = row(a, "a"), row(b, "a")
    assert rb["warranty_failures_median"] == pytest.approx(2 * ra["warranty_failures_median"])
    assert rb["warranty_cost_median"] == pytest.approx(500 * rb["warranty_failures_median"])


def test_no_exposure_without_fleet():
    sel = select([raw("a", 1000)], 55, 1000)
    assert "warranty_cost_median" not in sel.candidates.columns


# --- Combinations (E8, empty slots left out) -------------------------------------------------------

def test_empty_slots_left_out_and_single_slot_system():
    sel = select([raw("a", 1000), raw("b", 5000)], 55, 1000)
    assert set(sel.combinations["combination"]) == {"a", "b"}
    best = sel.combinations.iloc[0]
    assert best["combination"] == "b"
    assert best["system_fit_median"] == pytest.approx(row(sel, "b")["fit_median"])


def test_best_combination_is_best_per_slot_when_dominant():
    cands = [raw("gd_good", 100_000), raw("gd_poor", 300),
             raw("iso_good", 100_000, slot="Digital isolator"), raw("iso_poor", 300, slot="Digital isolator")]
    sel = select(cands, 55, 1000)
    assert sel.combinations.iloc[0]["combination"] == "iso_good + gd_good"
    assert len(sel.combinations) == 4
    assert sel.combinations["p_best_combination"].sum() == pytest.approx(1.0)


# --- Ea (A12) and warnings -------------------------------------------------------------------------

def test_default_ea_from_library():
    assert default_ea() == 0.7


def test_stated_ea_is_used_exactly():
    sel = select([raw("a", 1000, ea_ev=0.9)], 55, 1000)
    r = row(sel, "a")
    assert r["ea_source"] == "report"
    assert r["af_eff_lower"] == r["af_eff_upper"] == pytest.approx(accel_factor(55, 125, 0.9))


def test_above_and_below_test_temperature_both_reported():
    # AF works in both directions: below T_test AF > 1 (more reliable), above it AF < 1 (less reliable).
    # Both give a normal reliability result; only a note above 150 C remains.
    cold = select([raw("a", 1000)], 55, 1000)
    hot = select([raw("a", 1000)], 200, 1000)
    assert row(cold, "a")["af_eff_median"] > 1 > row(hot, "a")["af_eff_median"]
    assert row(cold, "a")["r_mission_median"] > row(hot, "a")["r_mission_median"]
    assert 0 < row(hot, "a")["r_mission_median"] < 1
    assert cold.warnings == []
    assert len(hot.warnings) == 1 and "above 150 C" in hot.warnings[0]


def test_input_errors():
    with pytest.raises(ValueError):
        select([], 55, 1000)
    with pytest.raises(ValueError):
        clean_candidates([{"slot": "Wiper", "name": "a", "test_temp_c": 125, "fit": 1}])
    with pytest.raises(ValueError):
        clean_candidates([{"slot": "Gate driver", "name": "a", "test_temp_c": 125}])      # no evidence
    with pytest.raises(ValueError):
        clean_candidates([raw("a", 10), raw("a", 20)])                                    # duplicate
    with pytest.raises(ValueError):
        clean_candidates([{"slot": "Gate driver", "name": "a", "test_temp_c": 125, "fit": 1, "conf_level": 1.5}])
    with pytest.raises(ValueError):
        select([raw("a", 1000)], 55, 1000, target_r=1.0)


# --- Library candidates, CSV input and the run script ---------------------------------------------

def test_library_candidate_matches_raw_data():
    c = library_candidate("UCC21750QDWRQ1")
    assert c["sample_size"] == 87285 and c["test_temp_c"] == 125 and c["slot"] == "Gate driver"


def test_example_file_reads_and_runs():
    cands = read_candidates(EXAMPLE)
    assert len(cands) == 7
    sel = select(cands, 55, 1000, n_draws=1000)
    assert set(sel.candidates["slot"]) == {"ECU MCU", "Digital isolator", "Gate driver"}


def test_script_mode3_from_file():
    out = subprocess.run([sys.executable, str(ROOT / "code" / "02_run_simulator.py"), "--temp", "200",
                          "--candidates", str(EXAMPLE), "--fleet", "100000", "--cost", "1000", "--draws", "500"],
                         capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "Best combination:" in out.stdout and "System R(1,000 h)" in out.stdout
    assert "1. Reliability of each candidate at 200 C" in out.stdout


def test_script_mode3_interactive():
    # 150 C, Mode 3, mission 1000, default target, skip fleet (confidence is fixed at 95%); then 2 gate-driver
    # candidates: one from the library (part 1) and one typed in as raw data; all other slots 0
    answers = ["150", "3", "1000", "", "",
               "0", "0", "0", "0",                       # ECU MCU, BMS AFE, isolator, temp sensor
               "2",                                      # gate driver: 2 candidates
               "1", "1",                                 # candidate 1: library part 1
               "2", "Supplier X", "150", "1000", "500", "0", "",   # candidate 2: raw data, no Ea
               "0"]                                      # current sensor
    out = subprocess.run([sys.executable, str(ROOT / "code" / "02_run_simulator.py"), "--draws", "500"],
                         input="\n".join(answers) + "\n", capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "Supplier X" in out.stdout and "Best combination:" in out.stdout


def test_printed_tables_show_every_output():
    # Every Mode 3 output appears in the printed tables, with its 95% CI where it has one
    from functions.interface import candidate_table, combination_table, reliability_table
    sel = select([raw("a", 1000), raw("b", 5000)], 55, 1000, fleet_size=1000, cost_per_failure=100.0)
    rel = reliability_table(sel)
    for col in ("FIT", "MTTF (h)", "B0.1 (h)", "95% CI"):
        assert col in rel.columns
    assert "(" in rel.loc[0, "MTTF (h)"] and "(" in rel.loc[0, "B0.1 (h)"]          # CI shown
    cand = candidate_table(sel)
    for col in ("R lower bound (95%)", "P(R >= target)", "Meets target", "P(best in slot)",
                "Warranty failures", "Warranty cost"):
        assert col in cand.columns
    combo = combination_table(sel)
    for col in ("System FIT", "System R(mission)", "System B0.1 (h)", "Warranty failures", "Warranty cost",
                "Extra cost vs #1", "P(best)"):
        assert col in combo.columns
