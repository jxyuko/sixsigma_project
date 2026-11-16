# validation.py
# Evaluating the simulator (ROADMAP Section 11):
#   11b supplier_check(): our calculated values vs the FIT, MTBF and AF published in the team's
#       parameter table (data/reference/published_fit.csv). Published values are NOT model inputs.
#   11e known-truth coverage study of the course's 95% interval for the failure rate (E4).
#
# Known-truth study: invent synthetic suppliers whose true failure rate WE set, generate an HTOL
# result for each by Poisson-sampling failures (A1), compute the 95% interval exactly as select() does,
# and check how often it contains the truth. Ea is fixed at 0.7 eV in both the truth and the estimate,
# so the study checks the sampling interval alone; Ea is varied in the sensitivity table.

from pathlib import Path

import numpy as np
import pandas as pd

from functions.arrhenius import EA_MODE, accel_factor
from functions.evidence import lambda_bound, lambda_ci
from functions.library import load_library

PUBLISHED_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "published_fit.csv"

# Realistic test designs, spanning the library (A6): sample sizes from one 3-lot qualification
# (231) up to pooled programs (~100,000), 1,000 h, at 125 or 150 C
SAMPLE_SIZES = (231, 1000, 1900, 6973, 37101, 101758)
TEST_TEMPS_C = (125, 150)
TEST_HOURS = 1000
# True FIT at the use condition, spread evenly over four decades (log-uniform, 0.01-100 FIT):
# realistic, since true rates of good parts are tiny and many tests see zero failures
TRUE_FIT_RANGE = (0.01, 100)


# synthetic_suppliers(): steps 1-2 of 11e. Each row is one synthetic supplier with a true FIT at
# t_use_c and an HTOL result with f ~ Poisson(lambda_test * n * t)
def synthetic_suppliers(n_suppliers, rng, t_use_c=55):
    n = rng.choice(SAMPLE_SIZES, n_suppliers)
    t_test = rng.choice(TEST_TEMPS_C, n_suppliers)
    lo, hi = np.log10(TRUE_FIT_RANGE)
    fit_true = 10 ** rng.uniform(lo, hi, n_suppliers)
    af = accel_factor(t_use_c, t_test, EA_MODE)
    expected_f = fit_true / 1e9 * af * n * TEST_HOURS
    return pd.DataFrame({"sample_size": n, "test_temp_c": t_test, "test_hours": TEST_HOURS, "af": af,
                         "fit_true": fit_true, "expected_failures": expected_f,
                         "failures": rng.poisson(expected_f)})


# coverage_study(): 11e steps 3-4. The course 95% interval (E4) for every synthetic supplier, and
# whether the true FIT is inside it and below its upper bound (one-sided 97.5%)
def coverage_study(n_suppliers=1000, seed=11, t_use_c=55, conf=0.95):
    rng = np.random.default_rng(seed)
    sup = synthetic_suppliers(n_suppliers, rng, t_use_c)
    d = sup["sample_size"] * sup["test_hours"] * sup["af"]
    ci = lambda_ci(sup["failures"].to_numpy(), d.to_numpy(), conf)
    sup["fit_estimate"], sup["fit_lower"], sup["fit_upper"] = (ci[k] * 1e9 for k in ("estimate", "lower", "upper"))
    sup["in_central_95"] = (sup["fit_lower"] <= sup["fit_true"]) & (sup["fit_true"] <= sup["fit_upper"])
    sup["below_upper_975"] = sup["fit_true"] <= sup["fit_upper"]
    return sup


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


# supplier_check(): 11b. For every usable part, calculate the FIT the supplier convention gives (the
# chi-square bound at the published reference temperature and confidence level, Ea 0.7 eV, E4) and
# compare it with the published FIT, MTBF and AF; also our estimate and 95% CI at that temperature.
#   fit_calculated:  the calculated value used in place of a missing or mismatched published one
#   ratio = fit_calculated / fit_published (1 = reproduced)
def supplier_check(library=None, published=None):
    lib = load_library() if library is None else library
    pub = pd.read_csv(PUBLISHED_PATH) if published is None else published
    pub = pub.set_index("part")
    rows = []
    for _, r in lib[lib["usable"]].iterrows():
        p = pub.loc[r["part"]]
        t_ref, cl = p["ref_temp_c"], p["ref_conf_level"]
        af = accel_factor(t_ref, r["test_temp_c"], EA_MODE)
        d = r["sample_size"] * r["test_hours"] * af
        fit_calc = float(lambda_bound(int(r["failures"]), d, cl)) * 1e9
        ci = {k: v * 1e9 for k, v in lambda_ci(int(r["failures"]), d).items()}
        rows.append({
            "slot": r["slot"], "part": r["part"], "supplier": r["supplier"], "family": r["family"],
            "ref_temp_c": t_ref, "ref_conf_level": cl,
            "fit_published": p["fit_published"], "fit_published_status": p["fit_published_status"],
            "fit_calculated": fit_calc, "ratio": fit_calc / p["fit_published"],
            "fit_estimate": ci["estimate"], "fit_lower": ci["lower"], "fit_upper": ci["upper"],
            "published_inside_95ci": ci["lower"] <= p["fit_published"] <= ci["upper"],
            "mtbf_published_h": p["mtbf_published_h"], "mtbf_calculated_h": 1e9 / fit_calc,
            "mtbf_ratio": (1e9 / fit_calc) / p["mtbf_published_h"],
            "mtbf_matches_published_fit": np.isclose(1e9 / p["fit_published"], p["mtbf_published_h"], rtol=0.05),
            "af_published": p["af_published"], "af_calculated": af,
        })
    out = pd.DataFrame(rows)
    out["verdict"] = np.select(
        [out["ratio"].between(0.5, 2), out["ratio"] < 0.5],
        ["reproduced (within 2x)", "calculated lower than published"],
        "calculated higher than published")
    return out
