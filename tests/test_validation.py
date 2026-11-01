# test_validation.py
# Tests for the known-truth study (ROADMAP Section 11e). Small runs so they stay fast.

import numpy as np
import pytest

from functions.validation import (as_library, brier_score, calibration_study, coverage_by_evidence,
                                  coverage_study, synthetic_suppliers)


def test_synthetic_suppliers_follow_their_design():
    sup = synthetic_suppliers(2000, np.random.default_rng(1))
    assert sup["fit_true"].between(0.01, 100).all()
    assert sup["ea_true"].between(0.5, 0.9).all()
    assert set(sup["test_temp_c"]) == {125, 150}
    # Poisson failures: the mean count tracks the expected count
    assert sup["failures"].sum() == pytest.approx(sup["expected_failures"].sum(), rel=0.05)


def test_synthetic_suppliers_degenerate_and_errors():
    rng = np.random.default_rng(2)
    sup = synthetic_suppliers(5, rng, ea_true=np.full(5, 0.7), fixed_test_temp_c=125)
    assert (sup["ea_true"] == 0.7).all() and (sup["test_temp_c"] == 125).all()
    with pytest.raises(ValueError):
        synthetic_suppliers(5, rng, truth="normal")


def test_as_library_rows_are_simulator_ready():
    lib = as_library(synthetic_suppliers(3, np.random.default_rng(3)))
    assert list(lib["part"]) == ["SYN0", "SYN1", "SYN2"]
    assert lib["usable"].all()


def test_coverage_near_95_when_tests_see_failures():
    # Known answer: with informative tests (expected failures > 1) the central 95% interval
    # covers the truth about 95% of the time; the upper bound covers at least 97.5%.
    cov = coverage_study(300, seed=4, truth="uniform", n_draws=2000)
    informative = cov[cov["expected_failures"] > 1]
    assert informative["in_central_95"].mean() == pytest.approx(0.95, abs=0.04)
    assert cov["below_upper_975"].mean() >= 0.96
    table = coverage_by_evidence(cov)
    assert table.loc["all", "suppliers"] == 300


def test_calibration_model_consistent_world():
    # When true rates follow the model's own prior, P(B outlasts A) is informative:
    # Brier well below a coin flip (0.25)
    cal = calibration_study(200, seed=5, truth="uniform", n_draws=2000)
    assert brier_score(cal) < 0.16


def test_brier_score_extremes():
    import pandas as pd
    perfect = pd.DataFrame({"p_b_outlasts_a": [1.0, 0.0], "b_truly_better": [True, False]})
    coin = pd.DataFrame({"p_b_outlasts_a": [0.5, 0.5], "b_truly_better": [True, False]})
    assert brier_score(perfect) == 0.0
    assert brier_score(coin) == 0.25


# --- 11b: simulator vs the published values in the parameter table ------------------------------

@pytest.fixture(scope="module")
def supplier():
    from functions.validation import supplier_check
    return supplier_check(n_draws=20_000).drop_duplicates("family").set_index("family")


def test_simulator_reproduces_ti_published_fit(supplier):
    # Known answer through the whole simulator: TI C2000 at 55 C, 60% -> 6.21 (TI publishes 6.19)
    assert supplier.loc["TI C2000", "sim_fit_at_cl"] == pytest.approx(6.21, rel=0.02)
    ti = supplier[supplier["supplier"] == "Texas Instruments"]
    assert ti["ratio"].between(0.5, 2).all()
    assert ti["published_inside_sim_95ci"].all()


def test_simulator_af_matches_table(supplier):
    given = supplier.dropna(subset=["af_published"])
    assert np.allclose(given["sim_af_at_ea_0_7"], given["af_published"], rtol=1e-4)


def test_non_reproducible_published_values_flagged(supplier):
    # Published values that rest on more data than the table's test rows (Section 14)
    assert supplier.loc["Renesas RH850", "verdict"] == "simulator higher than published"
    assert supplier.loc["LTC6811-1", "verdict"] == "simulator lower than published"
