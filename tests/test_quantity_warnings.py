# test_quantity_warnings.py
# Quantity per slot (A10, E8, E12), input warnings, and the default mission hours (A7).

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from functions.candidates import DEFAULT_MISSION_HOURS, select
from functions.interface import key_table, parse_quantities, summary_text

ROOT = Path(__file__).resolve().parents[1]


def raw(name, n, slot="Gate driver", t_test=125, f=0, hours=1000, **kw):
    return {"slot": slot, "name": name, "test_temp_c": t_test, "test_hours": hours, "sample_size": n,
            "failures": f, **kw}


def row(sel, name):
    return sel.candidates.set_index("name").loc[name]


# --- Quantity per slot ----------------------------------------------------------------------------

def test_quantity_scales_system_rate_failures_and_costs():
    # Known answer: 6 gate drivers + 1 isolator -> lambda_sys = 6 lambda_gd + lambda_iso (E8);
    # purchase = N * q * price; part failures = N * q * (1 - exp(-lambda t)) (E12)
    cands = [raw("gd", 1000, unit_price_usd=5.0), raw("iso", 2000, slot="Digital isolator", unit_price_usd=2.0)]
    one = select(cands, 55, 2920)
    six = select(cands, 55, 2920, quantities={"gate driver": 6})
    gd1, gd6 = row(one, "gd"), row(six, "gd")
    assert gd6["fit_estimate"] == pytest.approx(gd1["fit_estimate"])          # FIT stays per part
    assert gd6["qty_per_vehicle"] == 6 and row(six, "iso")["qty_per_vehicle"] == 1
    lam = gd1["fit_estimate"] / 1e9
    assert gd6["warranty_failures_estimate"] == pytest.approx(1000 * 6 * (1 - math.exp(-lam * 2920)))
    assert gd6["purchase_cost"] == pytest.approx(1000 * 6 * 5.0)
    c1, c6 = one.combinations.iloc[0], six.combinations.iloc[0]
    for case in ("estimate", "lower", "upper", "upper_one_sided"):
        expected = 6 * gd1[f"fit_{case}"] + row(one, "iso")[f"fit_{case}"]
        assert c6[f"system_fit_{case}"] == pytest.approx(expected)
    assert c6["purchase_cost"] == pytest.approx(1000 * (6 * 5.0 + 2.0))
    assert c6["system_fit_estimate"] > c1["system_fit_estimate"]


def test_quantity_one_is_unchanged_and_target_uses_quantity():
    # Degenerate: quantity 1 reproduces the default exactly
    a = select([raw("gd", 1000)], 55, 2920)
    b = select([raw("gd", 1000)], 55, 2920, quantities={"Gate driver": 1})
    assert a.combinations.iloc[0]["system_fit_upper_one_sided"] == b.combinations.iloc[0]["system_fit_upper_one_sided"]
    # 95% maximum ~38.6 FIT per part: one part meets 343 FIT, ten parts (386 FIT) do not
    u = row(a, "gd")["fit_upper_one_sided"]
    target_fit = a.settings["target_fit"]
    assert u <= target_fit < 10 * u
    ten = select([raw("gd", 1000)], 55, 2920, quantities={"Gate driver": 10})
    assert row(a, "gd")["meets_target_at_confidence"] and not row(ten, "gd")["meets_target_at_confidence"]
    assert not ten.combinations.iloc[0]["meets_target_at_confidence"]
    assert row(ten, "gd")["r_mission_lower_bound"] == pytest.approx(math.exp(-10 * u / 1e9 * 2920))


def test_each_candidate_keeps_its_own_quantity():
    # Candidates of one slot may need different counts; each is its own case.
    # A row's own qty_per_vehicle wins over the slot value; a blank row takes the slot value, else 1.
    sel = select([raw("a", 1000, qty_per_vehicle=6), raw("b", 2000, qty_per_vehicle=3), raw("c", 3000)],
                 55, 2920, quantities={"Gate driver": 4})
    assert sel.settings["quantities"] == {"a": 6, "b": 3, "c": 4}
    assert row(sel, "a")["purchase_cost"] == pytest.approx(1000 * 6 * row(sel, "a")["unit_price_usd"])
    assert select([raw("c", 3000)], 55, 2920).settings["quantities"] == {"c": 1}


def test_rank_in_slot_is_by_fit_per_vehicle():
    # Known answer: zero failures, lambda_hat = 0.693 / D with D proportional to n. A (n = 1,500) has the
    # lower FIT per part, B (n = 1,000) is 1.5x higher; with 6 x A and 3 x B, B is 6/1.5 vs 3: B is lower
    # per vehicle (3 vs 4 units), so B ranks first, and the most reliable combination agrees
    sel = select([raw("A", 1500, qty_per_vehicle=6), raw("B", 1000, qty_per_vehicle=3)], 55, 2920)
    a, b = row(sel, "A"), row(sel, "B")
    assert b["fit_estimate"] == pytest.approx(1.5 * a["fit_estimate"])
    assert b["fit_per_vehicle_estimate"] == pytest.approx(3 * b["fit_estimate"])
    assert b["fit_per_vehicle_estimate"] < a["fit_per_vehicle_estimate"]
    assert b["rank_in_slot"] == 1 and a["rank_in_slot"] == 2
    assert sel.picks["most_reliable"]["combination"] == "B"
    t = key_table(sel)
    assert list(t.columns[:6]) == ["Slot", "Rank", "Part", "FIT per part (2.5th-97.5th %)", "Per vehicle",
                                   "FIT per vehicle"]
    # Degenerate: all quantities 1 -> ranked by FIT per part as before, columns unchanged
    one = select([raw("A", 1500), raw("B", 1000)], 55, 2920)
    assert row(one, "A")["rank_in_slot"] == 1
    assert "FIT (2.5th-97.5th %)" in key_table(one).columns and "FIT per vehicle" not in key_table(one).columns


@pytest.mark.parametrize("q", [0, -1, 2.5])
def test_bad_quantities(q):
    with pytest.raises(ValueError):
        select([raw("a", 1000)], 55, 2920, quantities={"Gate driver": q})


def test_unknown_slot_quantity_and_parsing():
    with pytest.raises(ValueError):
        select([raw("a", 1000)], 55, 2920, quantities={"Capacitor": 2})
    assert parse_quantities("Gate driver=6, BMS AFE=12") == {"Gate driver": 6, "BMS AFE": 12}
    with pytest.raises(ValueError):
        parse_quantities("Gate driver 6")


def test_quantity_shows_in_the_output():
    sel = select([raw("a", 1000)], 55, 2920, quantities={"Gate driver": 6})
    assert "Parts per vehicle: Gate driver 6" in summary_text(sel)
    assert key_table(sel)["Per vehicle"].tolist() == [6]
    assert "Per vehicle" not in key_table(select([raw("a", 1000)], 55, 2920)).columns


def test_quantity_with_ea_range():
    sel = select([raw("a", 1000)], 55, 2920, quantities={"Gate driver": 10}, ea_range=True, n_draws=500)
    one = select([raw("a", 1000)], 55, 2920, ea_range=True, n_draws=500)
    c, c1 = sel.combinations.iloc[0], one.combinations.iloc[0]
    assert c["system_fit_ea_upper"] == pytest.approx(10 * c1["system_fit_ea_upper"])


# --- Warnings ------------------------------------------------------------------------------------

def test_warning_above_test_temperature():
    sel = select([raw("hot", 1000, t_test=125)], 140, 2920)
    assert any("hot" in w and "above its test temperature" in w for w in sel.warnings)
    assert not any("above its test temperature" in w for w in select([raw("hot", 1000)], 125, 2920).warnings)
    band = select([raw("hot", 1000)], (40, 130), 2920)                     # band reaching above the test
    assert any("above its test temperature" in w for w in band.warnings)


def test_warning_small_test():
    # 50 devices x 1,000 h = 50,000 < 77,000 device-hours (one AEC-Q100 lot); 77 x 1,000 is not flagged
    assert any("small test" in w for w in select([raw("s", 50)], 55, 2920).warnings)
    assert not any("small test" in w for w in select([raw("s", 77)], 55, 2920).warnings)


def test_warning_assumed_confidence_level():
    fit = {"slot": "Gate driver", "name": "f", "test_temp_c": 125, "fit": 1.0, "ref_temp_c": 55}
    assert any("60% assumed" in w for w in select([fit], 55, 2920).warnings)
    assert not any("60% assumed" in w for w in select([{**fit, "conf_level": 0.6}], 55, 2920).warnings)
    assert not any("60% assumed" in w for w in select([raw("r", 1000)], 55, 2920).warnings)


# --- Default mission hours (A7) ------------------------------------------------------------------

def test_default_mission_is_2920_hours():
    assert DEFAULT_MISSION_HOURS == 8 * 365 * 1.0
    sel = select([raw("a", 1000)], 55)
    assert sel.settings["mission_hours"] == 2920 and sel.settings["default_mission"]
    assert "8-year EV battery warranty" in summary_text(sel)
    other = select([raw("a", 1000)], 55, 1000)
    assert not other.settings["default_mission"] and "8-year EV battery warranty" not in summary_text(other)


def test_runner_uses_default_hours_and_qty(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("slot,name,test_temp_c,test_hours,sample_size,failures\n"
                 "Gate driver,a,125,1000,1000,0\nGate driver,b,125,1000,2000,0\n")
    out = subprocess.run([sys.executable, str(ROOT / "code" / "02_run_simulator.py"), "--temp", "55",
                          "--candidates", str(f), "--qty", "Gate driver=6"],
                         capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert out.returncode == 0, out.stderr
    assert "for 2,920 h" in out.stdout and "Parts per vehicle: Gate driver 6" in out.stdout
