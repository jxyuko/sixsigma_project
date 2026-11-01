# candidates.py
# Mode 3: supplier selection (ROADMAP Section 2, Mode 3).
# The user (a vehicle maker) enters, for any of the six slots, as many candidate suppliers as they
# like, each with data from that supplier's reliability report. The simulator puts every candidate
# on the user's own operating condition, checks it against the user's reliability requirement,
# estimates the user's warranty exposure, and ranks the candidates and slot combinations.
#
# A candidate is a dict with:
#   slot, name                                  (required)
#   test_temp_c                                 (required) HTOL stress temperature, C
#   raw test data:  test_hours, sample_size, failures                       (E3, E4)
#   OR report summary: fit or mttf_hours, plus ref_temp_c (default test_temp_c),
#                      conf_level (default 0.60) and failures (default 0)   (A11, E15)
#   ea_ev (optional): activation energy stated in the report; else the library default (A12)
#   unit_price_usd (optional): purchase price; else Sheet2's price for that part, else the Sheet2
#                  average for the slot (A14)

import re
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

from functions.arrhenius import EA_MAX, EA_MIN, accel_factor, effective_af
from functions.evidence import PRIORS
from functions.library import SLOTS, load_library
from functions.reliability import b_life, reliability, unreliability
from functions.simulator import N_DRAWS, SEED, qi

DEFAULT_CONF_LEVEL = 0.60       # A11: the supplier convention when a report gives no confidence level
DEFAULT_TARGET_R = 0.999        # requirement: at most 0.1% failures over the mission (B0.1, E9)
CONFIDENCE = 0.95               # A13: required confidence that the target is met, fixed by team decision
MAX_JUNCTION_C = 150            # AEC-Q100 Grade 0 upper ambient limit; above it, warn
MAX_COMBINATIONS = 20_000
DEFAULT_FLEET = 1000            # A14: warranty exposure is reported per 1,000 vehicles unless a fleet is given
PRICES_PATH = Path(__file__).resolve().parents[1] / "data" / "prices.csv"   # Sheet2, cleaned


# load_prices(): Sheet2 unit prices (data/prices.csv, built by code/01_clean_data.py)
def load_prices(path=PRICES_PATH):
    return pd.read_csv(path)


def _key(text):
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


# price_for(): A14. The candidate's own price if given; else the Sheet2 price of a matching part
# number (same part, or one part number is the start of the other, e.g. ADuM4135 / ADUM4135WBRWZ);
# else the Sheet2 average for the slot.
def price_for(slot, name, unit_price=None, prices=None):
    if unit_price is not None and pd.notna(unit_price):
        if float(unit_price) < 0:
            raise ValueError(f"{name}: unit price can't be negative")
        return float(unit_price), "entered by user"
    prices = load_prices() if prices is None else prices
    in_slot = prices[prices["slot"] == slot]
    key = _key(name)
    for _, r in in_slot[in_slot["kind"] == "part"].iterrows():
        pk = _key(r["part"])
        if len(key) >= 6 and len(pk) >= 6 and (key == pk or key.startswith(pk) or pk.startswith(key)):
            return float(r["unit_price_usd"]), f"Sheet2 price of {r['part']}"
    avg = in_slot[in_slot["kind"] == "slot average"]
    if avg.empty:
        raise ValueError(f"{name}: no price given and no Sheet2 average for {slot}")
    return float(avg["unit_price_usd"].iloc[0]), f"Sheet2 average for {slot}"


# default_ea(): A12, the "training data" activation energy: the median Ea assumed in the library
# reports. Every report in parameter_table.xlsx assumes 0.7 eV, so this returns 0.7.
def default_ea(library=None):
    lib = load_library(usable_only=True) if library is None else library
    return float(lib["ea_ev"].median())


# evidence_device_hours(): the evidence n * t at the test temperature, from raw data or a report summary.
# Summary (E15): a supplier FIT is the chi-square bound lambda = chi2(CL; 2f+2) / (2 D_ref) with
# D_ref = n t AF(T_ref), so n t = chi2(CL; 2f+2) / (2 lambda AF(T_ref)), using the supplier's Ea.
def evidence_device_hours(c, ea_supplier):
    if all(k in c and pd.notna(c[k]) for k in ("test_hours", "sample_size")):
        nt = float(c["test_hours"]) * float(c["sample_size"])
        source = "raw test data"
    else:
        if c.get("fit") is not None and pd.notna(c.get("fit")):
            lam = float(c["fit"]) / 1e9
            source = "report FIT"
        elif c.get("mttf_hours") is not None and pd.notna(c.get("mttf_hours")):
            lam = 1 / float(c["mttf_hours"])
            source = "report MTTF/MTBF"
        else:
            raise ValueError(f"{c.get('name')}: give test_hours + sample_size, or fit, or mttf_hours")
        if lam <= 0:
            raise ValueError(f"{c.get('name')}: FIT / MTTF must be positive")
        cl = float(c.get("conf_level") or DEFAULT_CONF_LEVEL)
        if not 0 < cl < 1:
            raise ValueError(f"{c.get('name')}: conf_level must be between 0 and 1")
        f = int(c.get("failures") or 0)
        t_ref = float(c.get("ref_temp_c") if pd.notna(c.get("ref_temp_c", np.nan)) else c["test_temp_c"])
        af_ref = accel_factor(t_ref, float(c["test_temp_c"]), ea_supplier)
        nt = chi2.ppf(cl, 2 * f + 2) / (2 * lam * af_ref)
    if nt <= 0:
        raise ValueError(f"{c.get('name')}: device-hours must be positive")
    return nt, source


# clean_candidates(): validate the user's candidates and resolve evidence and Ea for each
def clean_candidates(candidates, library=None, prices=None):
    if not candidates:
        raise ValueError("enter at least one candidate")
    ea0 = default_ea(library)
    prices = load_prices() if prices is None else prices
    rows, names = [], set()
    for c in candidates:
        c = dict(c)
        if c.get("slot") not in SLOTS:
            raise ValueError(f"{c.get('name')}: slot must be one of {', '.join(SLOTS)}")
        if not c.get("name"):
            raise ValueError("every candidate needs a name")
        if (c["slot"], c["name"]) in names:
            raise ValueError(f"duplicate candidate {c['name']!r} in {c['slot']}")
        names.add((c["slot"], c["name"]))
        if c.get("test_temp_c") is None or pd.isna(c.get("test_temp_c")):
            raise ValueError(f"{c['name']}: test_temp_c is required")
        stated = c.get("ea_ev") is not None and pd.notna(c.get("ea_ev"))
        ea = float(c["ea_ev"]) if stated else ea0
        nt, source = evidence_device_hours(c, ea)
        f = int(c.get("failures") or 0)
        if f < 0:
            raise ValueError(f"{c['name']}: failures can't be negative")
        price, price_source = price_for(c["slot"], c["name"], c.get("unit_price_usd"), prices)
        rows.append({"slot": c["slot"], "name": c["name"], "supplier": c.get("supplier") or "",
                     "test_temp_c": float(c["test_temp_c"]), "device_hours_test": nt, "failures": f,
                     "ea_ev": ea, "ea_source": "report" if stated else "library default (A12)",
                     "evidence_source": source, "unit_price_usd": price, "price_source": price_source})
    out = pd.DataFrame(rows)
    out["slot"] = pd.Categorical(out["slot"], categories=SLOTS, ordered=True)
    return out.sort_values(["slot", "name"]).reset_index(drop=True)


@dataclass
class Selection:
    """Mode 3 result."""
    candidates: pd.DataFrame        # one row per candidate, at the user's condition
    combinations: pd.DataFrame      # slot combinations ranked best first
    warnings: list
    settings: dict
    lam: dict = field(repr=False)   # candidate name -> failure-rate draws at the use condition
    cheapest: dict = field(default_factory=dict)   # combination with the lowest median total cost


# p_best(): E16, share of draws where each column (candidate) has the lowest rate; ties split
def p_best(lam_matrix):
    lam_matrix = np.asarray(lam_matrix)
    low = lam_matrix.min(axis=1, keepdims=True)
    is_min = lam_matrix == low
    return (is_min / is_min.sum(axis=1, keepdims=True)).mean(axis=0)


# select(): Mode 3. Every candidate is put on the user's condition by the same equations as Mode 1
# (E2-E7, E6 for profiles), with a shared Ea draw for candidates without a stated Ea (A2, A12) and
# common random numbers. Requirement: R(mission_hours) >= target_r with 95% confidence (A13).
# Warranty exposure (E12, A14) for fleet_size vehicles (default 1,000) over warranty_hours (default
# the mission). Cost per warranty failure = repair_cost if given, else each part's unit price
# (a parts-only lower bound). Total cost = purchase + expected warranty cost.
def select(candidates, profile, mission_hours, target_r=DEFAULT_TARGET_R,
           warranty_hours=None, fleet_size=DEFAULT_FLEET, repair_cost=None,
           n_draws=N_DRAWS, seed=SEED, prior="uniform", cl=0.95, library=None, prices=None, top=10,
           ea_mode="shared"):
    # ea_mode (8d sensitivity) for candidates without a stated Ea: "shared" = one draw per run for
    # all (A2, default); "independent" = a separate draw per candidate; "fixed" = the library Ea (0.7)
    if ea_mode not in ("shared", "independent", "fixed"):
        raise ValueError("ea_mode must be 'shared', 'independent' or 'fixed'")
    if mission_hours <= 0:
        raise ValueError("mission hours must be positive")
    if not 0 < target_r < 1:
        raise ValueError("target reliability must be between 0 and 1")
    if fleet_size is None or fleet_size <= 0:
        raise ValueError("fleet size must be positive")
    if repair_cost is not None and repair_cost < 0:
        raise ValueError("repair cost can't be negative")
    confidence = CONFIDENCE
    cand = clean_candidates(candidates, library, prices)
    t_w = mission_hours if warranty_hours is None else warranty_hours
    rng = np.random.default_rng(seed)

    # Shared Ea draw (A2), centred on the library default (A12)
    ea0 = default_ea(library)
    ea_shared = rng.triangular(EA_MIN, min(max(ea0, EA_MIN), EA_MAX), EA_MAX, n_draws)

    # The AF (E2, E6) moves every candidate from its own test temperature to the user's condition in
    # either direction: AF > 1 below the test temperature, AF < 1 above it. Both are reported normally.
    # Only one informational note is kept, for conditions beyond the usual automotive rating.
    warnings = []
    temps = [profile] if np.isscalar(profile) else [t for t, _ in profile]
    if max(temps) > MAX_JUNCTION_C:
        warnings.append(f"{max(temps):g} C is above {MAX_JUNCTION_C} C, the usual maximum for automotive ICs "
                        "(AEC-Q100 Grade 0); check the parts are rated for it.")

    rows, lam = [], {}
    for _, c in cand.iterrows():
        if not c["ea_source"].startswith("library"):
            ea = np.full(n_draws, c["ea_ev"])
        elif ea_mode == "independent":
            ea = rng.triangular(EA_MIN, min(max(ea0, EA_MIN), EA_MAX), EA_MAX, n_draws)
        elif ea_mode == "fixed":
            ea = np.full(n_draws, ea0)
        else:
            ea = ea_shared
        af = effective_af(profile, c["test_temp_c"], ea)                         # E6
        lam_test = rng.gamma(c["failures"] + PRIORS[prior], 1 / c["device_hours_test"], n_draws)   # E4
        lam[c["name"]] = lam_test / af
        r_mission = reliability(lam[c["name"]], mission_hours)                  # E7
        row = {"slot": c["slot"], "name": c["name"], "supplier": c["supplier"],
               "test_temp_c": c["test_temp_c"], "evidence": c["evidence_source"],
               "device_hours_test": c["device_hours_test"], "failures": c["failures"],
               "ea_ev": c["ea_ev"], "ea_source": c["ea_source"],
               "unit_price_usd": c["unit_price_usd"], "price_source": c["price_source"]}
        for metric, x in {"af_eff": af, "fit": lam[c["name"]] * 1e9,
                          "mttf_hours": 1 / lam[c["name"]], "r_mission": r_mission,
                          "b01_hours": b_life(lam[c["name"]])}.items():
            q = qi(x, cl)
            row.update({f"{metric}_median": q["median"], f"{metric}_lower": q["lower"], f"{metric}_upper": q["upper"]})
        # E17: the user's one-sided lower confidence bound on R(mission)
        row["r_mission_lower_bound"] = float(np.quantile(r_mission, 1 - confidence))
        row["p_meets_target"] = float(np.mean(r_mission >= target_r))
        row["meets_target_at_confidence"] = row["r_mission_lower_bound"] >= target_r
        cost = c["unit_price_usd"] if repair_cost is None else repair_cost
        row["cost_per_failure"] = cost
        row["cost_basis"] = "parts-only (unit price)" if repair_cost is None else "user repair cost"
        fails = fleet_size * unreliability(lam[c["name"]], t_w)                  # E12
        row.update(cost_columns(fails, fails * cost, fleet_size * c["unit_price_usd"], cl))
        rows.append(row)
    table = pd.DataFrame(rows)

    # E16: P(best in slot)
    table["p_best_in_slot"] = np.nan
    for slot, idx in table.groupby("slot", observed=True).groups.items():
        names = table.loc[idx, "name"]
        table.loc[idx, "p_best_in_slot"] = p_best(np.column_stack([lam[n] for n in names]))
    table["rank_in_slot"] = table.groupby("slot", observed=True)["fit_median"].rank(method="min").astype(int)
    table = table.sort_values(["slot", "rank_in_slot"]).reset_index(drop=True)

    combos, cheapest = rank_combinations(table, lam, mission_hours, target_r, confidence, t_w,
                                         fleet_size, cl, top)
    settings = {"profile": profile, "mission_hours": mission_hours, "target_r": target_r,
                "confidence": confidence, "warranty_hours": t_w, "fleet_size": fleet_size,
                "repair_cost": repair_cost,
                "cost_basis": "parts-only (unit price)" if repair_cost is None else "user repair cost",
                "n_draws": n_draws, "seed": seed, "prior": prior, "cl": cl, "default_ea": ea0,
                "ea_mode": ea_mode}
    return Selection(table, combos, list(dict.fromkeys(warnings)), settings, lam, cheapest)


# cost_columns(): E12 / A14 warranty exposure for a fleet: expected failures, warranty cost,
# purchase cost and total cost (purchase + warranty), with 95% CIs from the draws
def cost_columns(fails, warranty_cost, purchase_cost, cl):
    out = {"purchase_cost": float(purchase_cost)}
    for name, x in {"warranty_failures": fails, "warranty_cost": warranty_cost,
                    "total_cost": purchase_cost + warranty_cost}.items():
        q = qi(x, cl)
        out.update({f"{name}_median": q["median"], f"{name}_lower": q["lower"], f"{name}_upper": q["upper"]})
    return out


# rank_combinations(): every way of picking one candidate per entered slot (empty slots are left
# out of the system). Series system (E8): lambda_sys = sum of the chosen candidates' rates, per draw.
# Ranked by median system FIT; P(best combination) is E16 over combinations.
def rank_combinations(table, lam, mission_hours, target_r, confidence, t_w, fleet_size, cl, top):
    slots = [s for s in SLOTS if s in set(table["slot"])]
    choices = [list(table.loc[table["slot"] == s, "name"]) for s in slots]
    n_combos = int(np.prod([len(c) for c in choices]))
    if n_combos > MAX_COMBINATIONS:
        # Too many to list: keep the top 3 candidates per slot by median FIT
        choices = [list(table[table["slot"] == s].nsmallest(3, "fit_median")["name"]) for s in slots]
    combos = list(product(*choices))
    info = table.set_index("name")
    lam_sys = np.column_stack([sum(lam[n] for n in combo) for combo in combos])
    best = p_best(lam_sys)
    rows = []
    for k, combo in enumerate(combos):
        ls = lam_sys[:, k]
        r = reliability(ls, mission_hours)
        row = {"combination": " + ".join(combo), **{s: n for s, n in zip(slots, combo)}}
        for metric, x in {"system_fit": ls * 1e9, "system_r_mission": r, "system_b01_hours": b_life(ls)}.items():
            q = qi(x, cl)
            row.update({f"{metric}_median": q["median"], f"{metric}_lower": q["lower"], f"{metric}_upper": q["upper"]})
        row["system_r_lower_bound"] = float(np.quantile(r, 1 - confidence))
        row["p_meets_target"] = float(np.mean(r >= target_r))
        row["meets_target_at_confidence"] = row["system_r_lower_bound"] >= target_r
        row["p_best_combination"] = best[k]
        # Warranty exposure: each part's failures cost that part's cost per failure (E12, A14)
        warranty = sum(fleet_size * unreliability(lam[n], t_w) * info.loc[n, "cost_per_failure"] for n in combo)
        purchase = sum(fleet_size * info.loc[n, "unit_price_usd"] for n in combo)
        row.update(cost_columns(fleet_size * unreliability(ls, t_w), warranty, purchase, cl))
        rows.append((purchase + warranty, row))
    order = np.argsort([row["system_fit_median"] for _, row in rows])
    best_total = rows[order[0]][0]
    out = []
    for rank, k in enumerate(order[:top], start=1):
        total, row = rows[k]
        row = {"rank": rank, **row}
        # Extra total cost vs the most reliable combination, paired draws (E11 applied to E12)
        q = qi(total - best_total, cl)
        row.update({"extra_cost_vs_best_median": q["median"], "extra_cost_vs_best_lower": q["lower"],
                    "extra_cost_vs_best_upper": q["upper"]})
        out.append(row)
    cheapest = min((row for _, row in rows), key=lambda r: r["total_cost_median"])
    return pd.DataFrame(out), dict(cheapest)


# library_candidate(): turn a library part into a candidate (raw test data, Ea from its report)
def library_candidate(part, library=None):
    lib = load_library() if library is None else library
    r = lib[lib["part"] == part]
    if r.empty:
        raise KeyError(f"{part!r} is not in the library")
    r = r.iloc[0]
    if not r["usable"]:
        raise ValueError(f"{part!r} can't be simulated: {r['flag']}")
    return {"slot": r["slot"], "name": r["part"], "supplier": r["supplier"], "test_temp_c": r["test_temp_c"],
            "test_hours": r["test_hours"], "sample_size": r["sample_size"], "failures": int(r["failures"])}
