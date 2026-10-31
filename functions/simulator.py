# simulator.py
# TASER-EV Monte Carlo simulator (ROADMAP Sections 2, 3 and 8).
# Mode 1: evaluate(config, profile) -> component and system results with 95% CIs.
# Mode 2: compare() comes in M4 and reuses draw_library() for common random numbers.

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from functions.arrhenius import EA_MODE, draw_ea, effective_af
from functions.evidence import device_hours, draw_lambda, fit, lambda_bound
from functions.library import SLOTS, load_library
from functions.reliability import (HOURS_PER_YEAR, b_life, p_meets_warranty, reliability,
                                   series_lambda, warranty_ratio)

N_DRAWS = 5000   # Section 8a
SEED = 5300      # Section 8: fixed seed, recorded with every result

# A7 [ASSUMPTION, placeholder]: warranty of 8 years at 1 powered-on hour per day = 2,920 h.
# The 8 years is the common EV battery-warranty term; the hours per day is NOT yet sourced
# [TODO: cite a driving-time / powered-on-time source and decide the conversion with the team].
WARRANTY_YEARS = 8
POWERED_HOURS_PER_DAY = 1.0
DEFAULT_WARRANTY_HOURS = WARRANTY_YEARS * 365 * POWERED_HOURS_PER_DAY


@dataclass
class Draws:
    """Monte Carlo draws shared by every configuration run with the same seed (Section 8a)."""
    ea: dict              # family -> Ea draws (one shared array under A2, or one per family)
    lambda_test: dict     # family -> failure-rate draws at T_test, Gamma(f + 1, n t) (E4, A5)
    seed: int
    n_draws: int
    prior: str
    ea_mode: str


@dataclass
class Evaluation:
    """Mode 1 result. Tables hold the median and 95% CI; `lam` keeps the per-draw rates."""
    components: pd.DataFrame
    system: pd.DataFrame
    lam: dict = field(repr=False)        # slot -> failure-rate draws at the use condition
    lam_sys: np.ndarray = field(repr=False)
    settings: dict = field(default_factory=dict)


# qi(): median and central interval of a vector of draws (the course's quantile-interval idea)
def qi(x, cl=0.95):
    lo, med, hi = np.quantile(x, [(1 - cl) / 2, 0.5, (1 + cl) / 2])
    return {"median": med, "lower": lo, "upper": hi}


# draw_library(): Section 8a steps 1-2, for every usable family in the library.
# Drawing per family (A9) in a fixed order means any two configurations run with the same seed
# get the same draws for the same part: common random numbers for Mode 2.
# ea_mode: "shared" = one Ea per run for all parts (A2); "independent" = one per family (8d)
def draw_library(library=None, n_draws=N_DRAWS, seed=SEED, prior="uniform", ea_mode="shared"):
    lib = load_library(usable_only=True) if library is None else library[library["usable"]]
    rng = np.random.default_rng(seed)
    families = lib.drop_duplicates("family").sort_values("family")
    shared = draw_ea(n_draws, rng)
    ea, lam = {}, {}
    for _, r in families.iterrows():
        lam[r["family"]] = draw_lambda(int(r["failures"]), r["sample_size"], r["test_hours"],
                                       n_draws, rng, prior=prior)
    for _, r in families.iterrows():
        if ea_mode == "shared":
            ea[r["family"]] = shared
        elif ea_mode == "independent":
            ea[r["family"]] = draw_ea(n_draws, rng)
        else:
            raise ValueError("ea_mode must be 'shared' or 'independent'")
    return Draws(ea, lam, seed, n_draws, prior, ea_mode)


# check_config(): a configuration maps 1-6 slots to one usable library part each (Section 2)
def check_config(config, library):
    if not 1 <= len(config) <= len(SLOTS):
        raise ValueError(f"a configuration fills 1 to {len(SLOTS)} slots")
    rows = {}
    for slot, part in config.items():
        if slot not in SLOTS:
            raise ValueError(f"unknown slot {slot!r}; slots are {', '.join(SLOTS)}")
        match = library[library["part"] == part]
        if match.empty:
            raise KeyError(f"{part!r} is not in the library")
        row = match.iloc[0]
        if row["slot"] != slot:
            raise ValueError(f"{part!r} is a {row['slot']} part, not a {slot} part")
        if not row["usable"]:
            raise ValueError(f"{part!r} can't be simulated: {row['flag']}")
        rows[slot] = row
    # Keep the library's slot order so tables read the same way every time
    return {s: rows[s] for s in SLOTS if s in rows}


# evaluate(): Mode 1 (ROADMAP Section 2), the full Monte Carlo for one configuration.
# config: {slot: part}, 1-6 slots;  profile: operating temperature in C, or [(T_C, fraction), ...]
# t_w: warranty in operating hours (A7);  draws: a Draws from draw_library() (made if not given)
def evaluate(config, profile=55, t_w=DEFAULT_WARRANTY_HOURS, draws=None, library=None, cl=0.95):
    lib = load_library() if library is None else library
    parts = check_config(config, lib)
    draws = draw_library(lib) if draws is None else draws

    comp_rows, lam = [], {}
    for slot, r in parts.items():
        ea = draws.ea[r["family"]]
        af = effective_af(profile, r["test_temp_c"], ea)                    # E6, one per Ea draw
        lam[slot] = draws.lambda_test[r["family"]] / af                     # 8a step 3
        d = device_hours(r["sample_size"], r["test_hours"], af)             # E3
        # Datasheet-style single number: chi-square 60% bound at Ea = 0.7 eV (E4)
        af_mode = effective_af(profile, r["test_temp_c"], EA_MODE)
        fit60 = float(fit(lambda_bound(int(r["failures"]), device_hours(r["sample_size"], r["test_hours"], af_mode), 0.60)))
        metrics = {
            "af_eff": af,
            "device_hours": d,
            "fit": fit(lam[slot]),                                          # E5
            "mttf_years_continuous": 1 / lam[slot] / HOURS_PER_YEAR,                   # E5
            "r_warranty": reliability(lam[slot], t_w),                      # E7
        }
        for name, x in metrics.items():
            comp_rows.append({"slot": slot, "part": r["part"], "supplier": r["supplier"],
                              "metric": name, **qi(x, cl)})
        comp_rows.append({"slot": slot, "part": r["part"], "supplier": r["supplier"],
                          "metric": "fit_60pct_bound", "median": fit60, "lower": np.nan, "upper": np.nan})

    lam_sys = series_lambda(list(lam.values()))                             # E8 (A4, A10: qty 1)
    b01 = b_life(lam_sys)                                                   # E9
    wr = warranty_ratio(b01, t_w)                                           # E10
    system = {
        "fit": fit(lam_sys),
        "mttf_years_continuous": 1 / lam_sys / HOURS_PER_YEAR,
        "r_warranty": reliability(lam_sys, t_w),
        "b01_hours": b01,
        "b01_years_continuous": b01 / HOURS_PER_YEAR,   # years of 24/7 operation, not calendar years
        "warranty_ratio": wr,
    }
    sys_rows = [{"metric": k, **qi(v, cl)} for k, v in system.items()]
    sys_rows.append({"metric": "p_meets_warranty", "median": p_meets_warranty(wr),   # E14
                     "lower": np.nan, "upper": np.nan})

    settings = {"profile": profile, "t_w_hours": t_w, "cl": cl, "seed": draws.seed,
                "n_draws": draws.n_draws, "prior": draws.prior, "ea_mode": draws.ea_mode,
                "config": {s: r["part"] for s, r in parts.items()}}
    return Evaluation(pd.DataFrame(comp_rows), pd.DataFrame(sys_rows), lam, lam_sys, settings)


# reliability_band(): R_sys(t) median and CI over a grid of operating hours (E8)
def reliability_band(evaluation, hours, cl=0.95):
    rows = [{"hours": t, **qi(reliability(evaluation.lam_sys, t), cl)} for t in np.asarray(hours, dtype=float)]
    return pd.DataFrame(rows)


# failure_time_check(): Section 8c, aleatory check of E9 for one set of rates.
# Simulates n_systems series systems, T_j ~ Exp(lambda_j), T_sys = min_j T_j, and returns the
# empirical p-quantile of T_sys next to the closed-form B_p.
def failure_time_check(lams, n_systems, rng, p=0.001):
    times = np.min([rng.exponential(1 / lam, size=n_systems) for lam in lams], axis=0)
    return float(np.quantile(times, p)), float(b_life(series_lambda(lams), p))
