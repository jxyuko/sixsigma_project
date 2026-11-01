# validation.py
# Evaluating the simulator (ROADMAP Section 11):
#   11b supplier_check(): the simulator's output vs the FIT, MTBF and AF published in the team's
#       parameter table (data/reference/published_fit.csv). Those values are NOT model inputs.
#   11e known-truth coverage and calibration study.
#
# Known-truth study: invent synthetic suppliers whose true failure rate WE set, generate an HTOL
# result for each by Poisson-sampling failures, run the real simulator (evaluate / compare) on that
# result, and check whether its answers contain the truth.

import numpy as np
import pandas as pd

from pathlib import Path

from functions.arrhenius import EA_MODE, accel_factor, draw_ea
from functions.library import load_library
from functions.simulator import N_DRAWS, SEED, compare, draw_library, evaluate

PUBLISHED_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "published_fit.csv"

SLOT = "ECU MCU"   # any slot works; synthetic parts all go in one slot

# Realistic test designs, spanning the library (A6): sample sizes from one 3-lot qualification
# (231) up to pooled programs (~100,000), 1,000 h, at 125 or 150 C
SAMPLE_SIZES = (231, 1000, 1900, 6973, 37101, 101758)
TEST_TEMPS_C = (125, 150)
TEST_HOURS = 1000
# True FIT at the use condition, two "worlds" (11e):
#   "log-uniform": spread evenly over four decades, 0.01-100 FIT. Realistic: true rates of good
#                  parts are tiny and many tests see zero failures. Differs from the model's prior.
#   "uniform":     flat on 0-100 FIT, close to the model's own uniform prior (A5). If the code is
#                  right, intervals and P(B outlasts A) should be close to calibrated here.
TRUE_FIT_RANGE = (0.01, 100)
TRUTHS = ("log-uniform", "uniform")


# synthetic_suppliers(): steps 1-2 of 11e. Each row is one synthetic supplier with a true Ea,
# a true FIT at t_use_c, and an HTOL result with f ~ Poisson(lambda_test * n * t).
# ea_true: optional array of true Ea values (to give a pair the same Ea, as A2 assumes)
def synthetic_suppliers(n_suppliers, rng, t_use_c=55, truth="log-uniform", ea_true=None,
                        fixed_test_temp_c=None):
    n = rng.choice(SAMPLE_SIZES, n_suppliers)
    t_test = (np.full(n_suppliers, fixed_test_temp_c) if fixed_test_temp_c is not None
              else rng.choice(TEST_TEMPS_C, n_suppliers))
    ea_true = draw_ea(n_suppliers, rng) if ea_true is None else np.asarray(ea_true)   # truth follows A2
    if truth == "log-uniform":
        lo, hi = np.log10(TRUE_FIT_RANGE)
        fit_true = 10 ** rng.uniform(lo, hi, n_suppliers)
    elif truth == "uniform":
        fit_true = rng.uniform(0, TRUE_FIT_RANGE[1], n_suppliers)
    else:
        raise ValueError(f"truth must be one of {TRUTHS}")
    lam_test_true = fit_true / 1e9 * accel_factor(t_use_c, t_test, ea_true)
    expected_f = lam_test_true * n * TEST_HOURS
    return pd.DataFrame({
        "sample_size": n, "test_temp_c": t_test, "test_hours": TEST_HOURS,
        "ea_true": ea_true, "fit_true": fit_true, "expected_failures": expected_f,
        "failures": rng.poisson(expected_f),
    })


# as_library(): wrap synthetic test results as library rows so the REAL simulator runs on them
def as_library(suppliers):
    lib = suppliers.reset_index(drop=True).copy()
    lib["part"] = [f"SYN{i}" for i in range(len(lib))]
    lib["family"] = lib["part"]
    lib["slot"] = SLOT
    lib["supplier"] = "synthetic"
    lib["ea_ev"] = 0.7
    lib["usable"] = True
    lib["flag"] = ""
    return lib


# coverage_study(): 11e step 3-4 for intervals. Runs evaluate() on each synthetic supplier at t_use_c
# and records whether the true FIT is inside the central 95% interval and below its upper bound.
def coverage_study(n_suppliers=1000, seed=11, t_use_c=55, n_draws=5000, truth="log-uniform"):
    rng = np.random.default_rng(seed)
    sup = synthetic_suppliers(n_suppliers, rng, t_use_c, truth=truth)
    lib = as_library(sup)
    rows = []
    for i, r in lib.iterrows():
        one = lib.iloc[[i]]
        draws = draw_library(one, n_draws=n_draws, seed=seed * 100_000 + i)
        ev = evaluate({SLOT: r["part"]}, t_use_c, draws=draws, library=one)
        c = ev.components
        f = c[c["metric"] == "fit"].iloc[0]
        rows.append({"fit_median": f["median"], "fit_lower": f["lower"], "fit_upper": f["upper"]})
    out = pd.concat([sup.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    out["in_central_95"] = (out["fit_lower"] <= out["fit_true"]) & (out["fit_true"] <= out["fit_upper"])
    out["below_upper_975"] = out["fit_true"] <= out["fit_upper"]
    return out


# coverage_by_evidence(): summarize coverage by how many failures the test was expected to see
EVIDENCE_BINS = [0, 0.1, 1, 10, np.inf]
EVIDENCE_LABELS = ["< 0.1", "0.1-1", "1-10", "> 10"]


def coverage_by_evidence(cov):
    groups = pd.cut(cov["expected_failures"], EVIDENCE_BINS, labels=EVIDENCE_LABELS)
    table = cov.groupby(groups, observed=False).agg(
        suppliers=("fit_true", "size"),
        share_zero_failures=("failures", lambda f: float(np.mean(f == 0))),
        central_95_coverage=("in_central_95", "mean"),
        upper_975_coverage=("below_upper_975", "mean"),
    )
    total = pd.DataFrame({
        "suppliers": [len(cov)], "share_zero_failures": [float(np.mean(cov["failures"] == 0))],
        "central_95_coverage": [cov["in_central_95"].mean()],
        "upper_975_coverage": [cov["below_upper_975"].mean()],
    }, index=["all"])
    return pd.concat([table, total]).rename_axis("expected_failures")


# calibration_study(): 11e step 4 for P(B outlasts A). Pairs of synthetic suppliers tested at the
# same T_test with the same true Ea (the shared-Ea assumption, A2); records compare()'s
# P(B outlasts A) and whether B truly has the lower rate.
def calibration_study(n_pairs=1000, seed=12, t_use_c=55, n_draws=5000, truth="log-uniform"):
    rng = np.random.default_rng(seed)
    ea = draw_ea(n_pairs, rng)
    a = synthetic_suppliers(n_pairs, rng, t_use_c, truth, ea_true=ea, fixed_test_temp_c=125)
    b = synthetic_suppliers(n_pairs, rng, t_use_c, truth, ea_true=ea, fixed_test_temp_c=125)
    rows = []
    for i in range(n_pairs):
        pair = as_library(pd.concat([a.iloc[[i]], b.iloc[[i]]]))
        pair.loc[1, "slot"] = "BMS AFE"   # B in its own slot so the two parts are separate configs
        draws = draw_library(pair, n_draws=n_draws, seed=seed * 100_000 + i)
        cmp = compare({SLOT: "SYN0"}, {"BMS AFE": "SYN1"}, t_use_c, draws=draws, library=pair)
        rows.append({"p_b_outlasts_a": cmp.p_b_outlasts_a,
                     "b_truly_better": b["fit_true"].iloc[i] < a["fit_true"].iloc[i],
                     "fit_true_a": a["fit_true"].iloc[i], "fit_true_b": b["fit_true"].iloc[i],
                     "failures_a": a["failures"].iloc[i], "failures_b": b["failures"].iloc[i],
                     "both_zero_failures": a["failures"].iloc[i] == 0 and b["failures"].iloc[i] == 0})
    return pd.DataFrame(rows)


# calibration_table(): when the simulator says P, how often is B truly better?
def calibration_table(cal, n_bins=5):
    edges = np.linspace(0, 1, n_bins + 1)
    groups = pd.cut(cal["p_b_outlasts_a"], edges, include_lowest=True)
    return cal.groupby(groups, observed=False).agg(
        pairs=("p_b_outlasts_a", "size"),
        mean_p_b_outlasts_a=("p_b_outlasts_a", "mean"),
        share_b_truly_better=("b_truly_better", "mean"),
    ).rename_axis("p_bin")


# brier_score(): mean squared error of P(B outlasts A) against the truth (0 is perfect, 0.25 is a coin)
def brier_score(cal):
    return float(np.mean((cal["p_b_outlasts_a"] - cal["b_truly_better"].astype(float)) ** 2))


# supplier_check(): 11b. For every usable part, run the simulator at the part's published reference
# temperature and compare with the published FIT, MTBF and AF.
#   sim_fit_at_cl:  CL-percentile of the simulator's FIT draws with Ea fixed at 0.7 eV, the supplier
#                   convention (should equal the chi-square bound, E4)
#   sim_fit_median, sim_fit_lower, sim_fit_upper: the simulator's default output (Ea uncertain, A2)
#   ratio = sim_fit_at_cl / fit_published (1 = reproduced); log10_ratio for plotting
def supplier_check(library=None, published=None, n_draws=N_DRAWS, seed=SEED):
    lib = load_library() if library is None else library
    pub = pd.read_csv(PUBLISHED_PATH) if published is None else published
    pub = pub.set_index("part")
    usable = lib[lib["usable"]]
    fixed = draw_library(usable, n_draws, seed, ea_mode="fixed")
    uncertain = draw_library(usable, n_draws, seed)
    rows = []
    for _, r in usable.iterrows():
        p = pub.loc[r["part"]]
        t_ref, cl = p["ref_temp_c"], p["ref_conf_level"]
        cfg = {r["slot"]: r["part"]}
        ev_fixed = evaluate(cfg, t_ref, draws=fixed, library=usable)
        ev = evaluate(cfg, t_ref, draws=uncertain, library=usable)
        fit_fixed = ev_fixed.lam[r["slot"]] * 1e9
        c = ev.components
        f = c[c["metric"] == "fit"].iloc[0]
        sim_at_cl = float(np.quantile(fit_fixed, cl))
        rows.append({
            "slot": r["slot"], "part": r["part"], "supplier": r["supplier"], "family": r["family"],
            "ref_temp_c": t_ref, "ref_conf_level": cl,
            "fit_published": p["fit_published"], "fit_published_status": p["fit_published_status"],
            "sim_fit_at_cl": sim_at_cl,
            "ratio": sim_at_cl / p["fit_published"],
            "sim_fit_median": f["median"], "sim_fit_lower": f["lower"], "sim_fit_upper": f["upper"],
            "published_inside_sim_95ci": f["lower"] <= p["fit_published"] <= f["upper"],
            "mtbf_published_h": p["mtbf_published_h"],
            "sim_mtbf_at_cl_h": 1e9 / sim_at_cl,
            "mtbf_ratio": (1e9 / sim_at_cl) / p["mtbf_published_h"],
            "mtbf_matches_published_fit": np.isclose(1e9 / p["fit_published"], p["mtbf_published_h"], rtol=0.05),
            "af_published": p["af_published"],
            "sim_af_at_ea_0_7": accel_factor(t_ref, r["test_temp_c"], EA_MODE),
        })
    out = pd.DataFrame(rows)
    out["verdict"] = np.select(
        [out["ratio"].between(0.5, 2), out["ratio"] < 0.5],
        ["reproduced (within 2x)", "simulator lower than published"],
        "simulator higher than published")
    return out
