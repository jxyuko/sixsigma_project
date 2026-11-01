# test_analysis.py
# The report analysis (analysis/01_preliminary_results.py) only calls tested simulator functions; its one
# new statistic is the paired failure-rate ratio per slot (Table 2). Known answer and degenerate case.

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from functions.candidates import select

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prelim", ROOT / "analysis" / "01_preliminary_results.py")
prelim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prelim)


def cand(name, supplier, n):
    return {"slot": "Gate driver", "name": name, "supplier": supplier, "test_temp_c": 125,
            "test_hours": 1000, "sample_size": n, "failures": 0}


def test_slot_ratio_degenerate_identical_evidence():
    # Same evidence and shared Ea: the ratio's median is 1 and TI is best half the time
    sel = select([cand("ti", "Texas Instruments", 10_000), cand("alt", "Analog Devices", 10_000)], 55, 1000,
                 n_draws=20_000)
    r = prelim.table_slot_comparison(sel).iloc[0]
    assert r["fit_ratio_alt_over_ti_median"] == pytest.approx(1.0, rel=0.05)
    assert r["p_ti_best"] == pytest.approx(0.5, abs=0.02)


def test_slot_ratio_known_answer():
    # Two zero-failure parts at one T_test: lambda_alt / lambda_ti = (E_alt / D_alt) / (E_ti / D_ti) with
    # E ~ Exp(1), so the median ratio is D_ti / D_alt (the median of E1/E2 is 1). D_ti = 4 D_alt -> 4.
    sel = select([cand("ti", "Texas Instruments", 40_000), cand("alt", "Analog Devices", 10_000)], 55, 1000,
                 n_draws=50_000)
    r = prelim.table_slot_comparison(sel).iloc[0]
    assert r["fit_ratio_alt_over_ti_median"] == pytest.approx(4.0, rel=0.05)
    assert r["p_ti_best"] == pytest.approx(0.8, abs=0.01)          # D_ti / (D_ti + D_alt), E16
    assert r["fit_ratio_lower"] < r["fit_ratio_alt_over_ti_median"] < r["fit_ratio_upper"]
