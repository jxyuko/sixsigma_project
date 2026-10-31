# test_library.py
# Checks the component library and the published-FIT reference built by code/01_clean_data.py
# (ROADMAP Sections 4 and 14, milestone M1).
# Run code/01_clean_data.py first, then: .venv/Scripts/python -m pytest

import math
from pathlib import Path

import pandas as pd
import pytest

from functions.library import REQUIRED, SLOTS, get_part, load_library

PUBLISHED_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "published_fit.csv"


@pytest.fixture(scope="module")
def lib():
    return load_library()


@pytest.fixture(scope="module")
def published():
    return pd.read_csv(PUBLISHED_PATH).set_index("part")


# --- Model library: data/components.csv ---------------------------------------------------------

def test_every_slot_has_a_part(lib):
    assert set(lib["slot"]) == set(SLOTS)


def test_one_row_per_part(lib):
    # 4 TI C2000 + 5 RH850 + 3 AFE + 2 isolator + 2 temp sensor + 2 gate driver + 1 current sensor
    assert lib["part"].is_unique
    assert len(lib) == 19


def test_model_library_has_no_published_fit(lib):
    # The simulator runs on test data only; published FITs live in data/reference/
    assert not [c for c in lib.columns if "fit" in c or c.startswith("ref_") or c.endswith("_published")]


def test_known_answer_ti_c2000_row(lib):
    # Test parameters typed in the raw table for TI F280049 (the CLAUDE.md known-answer part)
    row = get_part("F280049CPZQR", lib)
    assert row["slot"] == "ECU MCU"
    assert row["sample_size"] == 1900
    assert row["test_hours"] == 1000
    assert row["test_temp_c"] == 125
    assert row["failures"] == 0
    assert row["ea_ev"] == 0.7


def test_typo_corrected_and_traceable(lib):
    row = get_part("ADuM4135", lib)
    assert row["raw_part"] == "ASUM4135"
    assert "typo" in row["flag"]


def test_one_failure_part_kept(lib):
    assert get_part("ADuM141E", lib)["failures"] == 1


def test_supplier_names_normalized(lib):
    assert set(lib["supplier"]) == {"Texas Instruments", "Analog Devices", "Renesas Electronics"}


def test_incomplete_parts_are_not_usable(lib):
    # Degenerate rows: a required field is blank in the raw table, so the part can't be simulated
    assert not get_part_row(lib, "MAX31730")["usable"]        # sample size blank
    assert not get_part_row(lib, "ISL78714ANZ-T")["usable"]   # failures blank
    usable = lib[lib["usable"]]
    assert usable[list(REQUIRED)].notna().all().all()
    assert len(usable) == 17


def test_load_usable_only(lib):
    usable = load_library(usable_only=True)
    assert set(usable["part"]) == set(lib.loc[lib["usable"], "part"])


def test_get_part_errors(lib):
    with pytest.raises(KeyError):
        get_part("NOT-A-PART", lib)
    with pytest.raises(ValueError):
        get_part("MAX31730", lib)   # unusable parts can't be handed to the simulator


# --- Published-FIT reference: data/reference/published_fit.csv (not used by the model) ---------

def test_reference_covers_every_part(lib, published):
    assert set(published.index) == set(lib["part"])


def test_published_fit_kept_as_reported(published):
    assert published.loc["F280049CPZQR", "fit_published"] == pytest.approx(6.19)
    assert published.loc["LTC6811-1", "fit_published"] == pytest.approx(33.95)
    assert published.loc["ADuM4135", "fit_published"] == pytest.approx(11.28)
    assert published.loc["R7F7010183AFP-C", "fit_published"] == pytest.approx(0.0011)
    assert published.loc["F280049CPZQR", "ref_temp_c"] == 55
    assert published.loc["F280049CPZQR", "ref_conf_level"] == pytest.approx(0.60)


def test_verification_status_joined(published):
    assert published.loc["LTC6811-1", "fit_published_status"] == "verified"
    assert published.loc["ISL78714ANZ-T", "fit_published_status"] == "verified"
    assert published.loc["R7F7016903AFP-C", "fit_published_status"] == "verified"   # via RH850 family
    assert published.loc["ADuM4135", "fit_published_status"] == "not verified"
    assert published.loc["UCC21750QDWRQ1", "fit_published_status"] == "not checked"
    assert published.loc["LTC6811-1", "fit_published_source"].startswith("ADI reliability report r582")


def test_calculated_fit_known_answer(published):
    assert published.loc["F280049CPZQR", "fit_calculated"] == pytest.approx(6.21, abs=0.01)
    assert published.loc["F280049CPZQR", "fit_calc_ratio"] == pytest.approx(6.211 / 6.19, rel=1e-3)


def test_calculated_fit_missing_for_unusable_parts(lib, published):
    usable = lib.set_index("part")["usable"]
    assert published.loc[~usable, "fit_calculated"].isna().all()
    assert published.loc[usable, "fit_calculated"].notna().all()


def test_af_published_matches_arrhenius_where_given(published):
    # The raw AF column was computed by the team; spot-check the 125 C -> 55 C value (E2)
    k = 8.617333e-5
    af = math.exp(0.7 / k * (1 / 328.15 - 1 / 398.15))
    assert published.loc["F280049CPZQR", "af_published"] == pytest.approx(af, rel=1e-4)


def get_part_row(lib, part):
    # Row lookup that doesn't raise for unusable parts
    return lib.set_index("part").loc[part]
