# test_validation.py
# Tests for the validation functions (ROADMAP Sections 11b, 11e). Small runs so they stay fast.

import numpy as np
import pytest

from functions.validation import coverage_by_evidence, coverage_study, supplier_check, synthetic_suppliers


def test_synthetic_suppliers_follow_their_design():
    sup = synthetic_suppliers(2000, np.random.default_rng(1))
    assert sup["fit_true"].between(0.01, 100).all()
    assert set(sup["test_temp_c"]) == {125, 150}
    # Poisson failures: the mean count tracks the expected count
    assert sup["failures"].sum() == pytest.approx(sup["expected_failures"].sum(), rel=0.05)


def test_coverage_of_the_course_interval():
    # Known answer: the chi-square interval is exact-or-conservative, so the central 95% interval covers
    # the truth at least ~95% of the time and the upper bound at least 97.5%
    cov = coverage_study(2000, seed=4)
    assert cov["in_central_95"].mean() >= 0.94
    assert cov["below_upper_975"].mean() >= 0.97
    table = coverage_by_evidence(cov)
    assert table.loc["all", "suppliers"] == 2000


def test_coverage_degenerate_seed_reproducible():
    a, b = coverage_study(50, seed=7), coverage_study(50, seed=7)
    assert a.equals(b)


# --- 11b: calculated vs the published values in the parameter table ------------------------------

@pytest.fixture(scope="module")
def supplier():
    return supplier_check().drop_duplicates("family").set_index("family")


def test_calculated_reproduces_ti_published_fit(supplier):
    # Known answer: TI C2000 at 55 C, 60% -> 6.21 (TI publishes 6.19)
    assert supplier.loc["TI C2000", "fit_calculated"] == pytest.approx(6.21, abs=0.01)
    ti = supplier[supplier["supplier"] == "Texas Instruments"]
    assert ti["ratio"].between(0.5, 2).all()
    assert ti["published_inside_95ci"].all()


def test_calculated_af_matches_table(supplier):
    given = supplier.dropna(subset=["af_published"])
    assert np.allclose(given["af_calculated"], given["af_published"], rtol=1e-4)


def test_non_reproducible_published_values_flagged(supplier):
    # Published values that rest on more data than the table's test rows (Section 14)
    assert supplier.loc["Renesas RH850", "verdict"] == "calculated higher than published"
    assert supplier.loc["LTC6811-1", "verdict"] == "calculated lower than published"
