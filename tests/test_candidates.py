# test_candidates.py
# The simulator: supplier selection with select() (ROADMAP Section 2, E4, E15-E19, A11-A14): known answers
# and degenerate cases.

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from functions.arrhenius import accel_factor
from functions.candidates import clean_candidates, default_ea, evidence_device_hours, library_candidate, select
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


# --- E4 in select(): estimate and 95% interval at the use condition -------------------------------

def test_select_known_answer_at_test_temperature():
    # At T_op = T_test, AF = 1. n = 1,000, 1,000 h, r = 0: D = 1e6.
    # estimate = ln 2 / D; 95% CI = [0, -ln 0.025 / D]; one-sided 95% bound = -ln 0.05 / D
    r = row(select([raw("a", 1000)], 125, 1000), "a")
    assert r["fit_estimate"] == pytest.approx(math.log(2) / 1e6 * 1e9)
    assert r["fit_lower"] == 0.0 and r["warranty_failures_lower"] == 0.0 and r["r_mission_upper"] == 1.0
    assert r["fit_upper"] == pytest.approx(-math.log(0.025) / 1e6 * 1e9)
    assert r["fit_upper_one_sided"] == pytest.approx(-math.log(0.05) / 1e6 * 1e9)


def test_bounds_flip_for_reliability_and_life():
    # R, MTTF and B0.1 fall as the rate rises, so their lower bound comes from the rate's upper bound
    r = row(select([raw("a", 1000, f=2)], 55, 1000), "a")
    for m in ("r_mission", "mttf_hours", "b01_hours", "fit", "warranty_failures"):
        assert r[f"{m}_lower"] < r[f"{m}_estimate"] < r[f"{m}_upper"]
    assert r["mttf_hours_lower"] == pytest.approx(1e9 / r["fit_upper"])


def test_ranking_by_estimate():
    sel = select([raw("a", 1000), raw("b", 2000), raw("c", 7000)], 55, 1000)
    assert list(sel.candidates["name"]) == ["c", "b", "a"]
    assert list(sel.candidates["rank_in_slot"]) == [1, 2, 3]


# --- E17-E19: reliability requirement ---------------------------------------------------------------

def test_r_lower_bound_known_answer():
    # At T_op = T_test, AF = 1: the 95% lower bound on R(t) is exp(-t * -ln(0.05) / D). D = 1e6, t = 1000
    sel = select([raw("a", 1000)], 125, 1000)
    assert sel.settings["confidence"] == 0.95
    assert row(sel, "a")["r_mission_lower_bound"] == pytest.approx(math.exp(-1000 * -math.log(0.05) / 1e6))


def test_meets_target_matches_course_test():
    # Meets the target <=> the 95% maximum failure rate is at most -ln(target) / mission (E19)
    sel = select([raw("a", 87285), raw("b", 231)], 55, 10_000, target_r=0.999)
    for _, r in sel.candidates.iterrows():
        assert r["meets_target_at_confidence"] == (r["fit_upper_one_sided"] / 1e9 <= -math.log(0.999) / 10_000)
    assert row(sel, "a")["meets_target_at_confidence"] and not row(sel, "b")["meets_target_at_confidence"]


# --- E12 / A14: warranty exposure and cost ---------------------------------------------------------

def test_warranty_exposure_scales_with_fleet_and_cost():
    a = select([raw("a", 1000)], 55, 1000, fleet_size=1000, replacement_cost=1.0)
    b = select([raw("a", 1000)], 55, 1000, fleet_size=2000, replacement_cost=500.0)
    ra, rb = row(a, "a"), row(b, "a")
    for case in ("estimate", "lower", "upper"):
        assert rb[f"warranty_failures_{case}"] == pytest.approx(2 * ra[f"warranty_failures_{case}"])
        assert rb[f"warranty_cost_{case}"] == pytest.approx(500 * rb[f"warranty_failures_{case}"])


def test_default_exposure_is_per_1000_vehicles_parts_only():
    # A14: no fleet or replacement cost given -> 1,000 vehicles, cost per failure = the unit price
    sel = select([raw("UCC21750QDWRQ1", 1000)], 55, 1000)
    r = row(sel, "UCC21750QDWRQ1")
    assert sel.settings["fleet_size"] == 1000
    assert r["unit_price_usd"] == 8.03 and r["price_source"] == "Sheet2 price of UCC21750QDWRQ1"
    assert r["cost_per_failure"] == 8.03 and r["cost_basis"] == "replacement at unit price"
    assert r["purchase_cost"] == pytest.approx(8030)
    assert r["warranty_cost_estimate"] == pytest.approx(8.03 * r["warranty_failures_estimate"])


def test_total_cost_is_purchase_plus_warranty_in_every_case():
    sel = select([raw("a", 1000, unit_price_usd=10.0)], 55, 1000, fleet_size=100, replacement_cost=1000.0)
    r = row(sel, "a")
    for case in ("estimate", "lower", "upper"):
        assert r[f"total_cost_{case}"] == pytest.approx(r["purchase_cost"] + r[f"warranty_cost_{case}"])
    assert r["purchase_cost"] == 1000.0


def test_prices_from_sheet2():
    from functions.candidates import price_for
    assert price_for("Gate driver", "ADuM4135") == (9.33, "Sheet2 price of ADUM4135WBRWZ")     # prefix match
    price, source = price_for("ECU MCU", "My MCU")                       # not in Sheet2 -> slot average
    assert price == pytest.approx(15.853333, rel=1e-6) and source == "Sheet2 average for ECU MCU"
    assert price_for("Current sensor", "Any sensor")[0] == 17.35          # stated average, no rows listed
    assert price_for("Gate driver", "x", unit_price=4.5) == (4.5, "entered by user")
    with pytest.raises(ValueError):
        price_for("Gate driver", "x", unit_price=-1)


def test_cheapest_combination_found():
    # a is more reliable but much more expensive than b; both meet the target, so the cheapest is b
    sel = select([raw("a", 100_000, unit_price_usd=50.0), raw("b", 50_000, unit_price_usd=1.0)], 55, 1000)
    assert sel.picks["most_reliable"]["combination"] == "a"
    assert sel.picks["cheapest"]["combination"] == "b"


def test_cheapest_only_among_combinations_meeting_the_target():
    # c is the cheapest but fails the target (tiny test, long mission); it must never be picked
    cands = [raw("a", 100_000, unit_price_usd=50.0), raw("c", 10, unit_price_usd=1.0)]
    sel = select(cands, 55, 10_000)
    assert not row(sel, "c")["meets_target_at_confidence"]
    assert sel.picks["cheapest"]["combination"] == "a"
    assert sel.picks["n_combinations"] == 2 and sel.picks["n_meeting_target"] == 1


def test_no_combination_meets_the_target():
    # Degenerate: nothing meets the target -> no cheapest pick, and the summary says so
    from functions.interface import summary_text
    sel = select([raw("c", 10), raw("d", 20)], 55, 10_000)
    assert sel.picks["cheapest"] is None and sel.picks["n_meeting_target"] == 0
    assert "No combination meets the target" in summary_text(sel)


def test_safest_differs_from_most_reliable():
    # x: 1 failure in a huge test (estimate 1/D, 95% maximum 4.74/D); y: zero failures in a test 1/1.5 the
    # size (estimate 0.693 * 1.5 / D = 1.04/D, maximum 2.996 * 1.5 / D = 4.49/D). x has the lower estimate,
    # y the lower 95% maximum.
    sel = select([raw("x", 150_000, f=1), raw("y", 100_000)], 55, 1000)
    assert sel.picks["most_reliable"]["combination"] == "x"
    assert sel.picks["safest"]["combination"] == "y"


# --- Combinations (E8, empty slots left out) -------------------------------------------------------

def test_empty_slots_left_out_and_single_slot_system():
    sel = select([raw("a", 1000), raw("b", 5000)], 55, 1000)
    assert set(sel.combinations["combination"]) == {"a", "b"}
    best = sel.combinations.iloc[0]
    assert best["combination"] == "b"
    for case in ("estimate", "lower", "upper"):
        assert best[f"system_fit_{case}"] == pytest.approx(row(sel, "b")[f"fit_{case}"])


def test_best_combination_is_best_per_slot_when_dominant():
    cands = [raw("gd_good", 100_000), raw("gd_poor", 300),
             raw("iso_good", 100_000, slot="Digital isolator"), raw("iso_poor", 300, slot="Digital isolator")]
    sel = select(cands, 55, 1000)
    assert sel.combinations.iloc[0]["combination"] == "iso_good + gd_good"
    assert len(sel.combinations) == 4
    best = sel.combinations.iloc[0]
    # E8: the system estimate sums the parts' estimates; its bounds put every part at its bound
    for case in ("estimate", "lower", "upper"):
        assert best[f"system_fit_{case}"] == pytest.approx(row(sel, "iso_good")[f"fit_{case}"]
                                                           + row(sel, "gd_good")[f"fit_{case}"])
    assert best["system_fit_upper_one_sided"] == pytest.approx(row(sel, "iso_good")["fit_upper_one_sided"]
                                                               + row(sel, "gd_good")["fit_upper_one_sided"])


# --- Ea (A12) and warnings -------------------------------------------------------------------------

def test_default_ea_from_library():
    assert default_ea() == 0.7


def test_stated_ea_is_used_exactly():
    sel = select([raw("a", 1000, ea_ev=0.9)], 55, 1000)
    r = row(sel, "a")
    assert r["ea_source"] == "report"
    assert r["af_eff"] == pytest.approx(accel_factor(55, 125, 0.9))


def test_above_and_below_test_temperature_both_reported():
    # AF works in both directions: below T_test AF > 1 (more reliable), above it AF < 1 (less reliable).
    # Both give a normal reliability result; only a note above 150 C remains.
    cold = select([raw("a", 1000)], 55, 1000)
    hot = select([raw("a", 1000)], 200, 1000)
    assert row(cold, "a")["af_eff"] > 1 > row(hot, "a")["af_eff"]
    assert row(cold, "a")["r_mission_estimate"] > row(hot, "a")["r_mission_estimate"]
    assert 0 < row(hot, "a")["r_mission_estimate"] < 1
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
    sel = select(cands, 55, 1000)
    assert set(sel.candidates["slot"]) == {"ECU MCU", "Digital isolator", "Gate driver"}


SCRIPT = ROOT / "code" / "02_run_simulator.py"


def test_script_from_file_summary_first():
    out = subprocess.run([sys.executable, str(SCRIPT), "--temp", "200", "--hours", "1000",
                          "--candidates", str(EXAMPLE)],
                         capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.index("SUMMARY") < out.stdout.index("BEST COMBINATIONS") < out.stdout.index("ALL CANDIDATES")
    for block in ("Most reliable (lowest estimated failure rate)", "Safest (lowest 95% maximum failure rate)",
                  "Cheapest that meets the target", "BEST PART IN EACH SLOT"):
        assert block in out.stdout
    assert "DETAILS" not in out.stdout                           # details only on request
    assert "R(1,000 h) =" not in out.stdout                      # R is in the details and CSVs, not the summary


def test_script_details_flag():
    out = subprocess.run([sys.executable, str(SCRIPT), "--temp", "55", "--hours", "1000",
                          "--candidates", str(EXAMPLE), "--details"],
                         capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "DETAILS: reliability of the best combinations" in out.stdout and "B0.1 (h)" in out.stdout


def test_script_requires_temperature_hours_and_file_together():
    out = subprocess.run([sys.executable, str(SCRIPT), "--temp", "55", "--candidates", str(EXAMPLE)],
                         capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert out.returncode != 0 and "--hours" in out.stderr


def test_script_interactive():
    # Required: temperature, hours. Optional settings: Enter. Then 2 gate-driver candidates:
    # one with test results, one with a FIT value; all other slots 0; no details.
    answers = ["40-105", "1000",
               "", "", "", "",                                   # target, fleet, replacement cost, warranty
               "2", "",                                          # Ea: range 0.5-0.9 eV, shared
               "0", "0", "0", "0",                               # ECU MCU, BMS AFE, isolator, temp sensor
               "2",                                              # gate driver: 2 candidates
               "Supplier X", "1", "2",                           # test results, 2 test groups
               "150", "1000", "500", "0",                        #   group 1
               "125", "1000", "300", "1", "", "",                #   group 2; Ea, price: Enter
               "Supplier Y", "2", "125", "0.5", "0", "55", "0.6", "", "6",    # FIT 0.5 at 55 C, $6
               "0",                                              # current sensor
               ""]                                               # details: no
    out = subprocess.run([sys.executable, str(SCRIPT)], input="\n".join(answers) + "\n",
                         capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "Supplier X" in out.stdout and "Supplier Y" in out.stdout and "Most reliable (lowest" in out.stdout
    assert "0.5-0.9 eV range" in out.stdout and "Worst case, all the time at 105 C" in out.stdout


def test_printed_tables_show_every_output():
    # The summary leads with FIT (2.5th-97.5th percentile) and failures; R, MTTF and B0.1 are in the details
    from functions.interface import best_reliability_table, key_table, reliability_table, summary_text
    sel = select([raw("a", 1000), raw("b", 5000)], 55, 1000)
    rel = reliability_table(sel)
    for col in ("FIT", "MTTF (h)", "B0.1 (h)", "R(1,000 h)", "AF to your condition"):
        assert col in rel.columns
    assert "(" in rel.loc[0, "MTTF (h)"] and "(" in rel.loc[0, "B0.1 (h)"]          # range shown
    key = key_table(sel)
    for col in ("FIT (2.5th-97.5th %)", "Failures/1,000", "Meets target", "Unit price"):
        assert col in key.columns
    assert key.loc[0, "FIT (2.5th-97.5th %)"].split("(")[1].startswith("0*")        # zero lower bound marked
    assert list(best_reliability_table(sel)["Combination"]) == ["b"]                 # three picks, one combination
    text = summary_text(sel)
    assert "Most reliable (lowest estimated failure rate)\n  b" in text and "lower bound 0" in text


def test_ea_override_for_sensitivity():
    # Candidates without a stated Ea use the library 0.7 eV, or the ea_ev given (A2 sensitivity);
    # a stated Ea is never overridden
    cands = [raw("a", 1000), raw("b", 1000, ea_ev=0.6)]
    base, hi = select(cands, 55, 1000), select(cands, 55, 1000, ea_ev=0.9)
    assert row(base, "a")["af_eff"] == pytest.approx(accel_factor(55, 125, 0.7))
    assert row(hi, "a")["af_eff"] == pytest.approx(accel_factor(55, 125, 0.9))
    assert row(hi, "b")["af_eff"] == row(base, "b")["af_eff"] == pytest.approx(accel_factor(55, 125, 0.6))
