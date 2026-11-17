# candidates.py
# The simulator: supplier selection (ROADMAP Section 2). This is what users run.
# The user (a vehicle maker) enters, for any of the six slots, as many candidate suppliers as they
# like, each with data from that supplier's reliability report. The simulator puts every candidate
# on the user's own operating condition, checks it against the user's reliability requirement,
# estimates the user's warranty exposure, and ranks the candidates and slot combinations.
#
# A candidate is a dict with:
#   slot, name                                  (required)
#   test_temp_c                                 (required) HTOL stress temperature, C
#   raw test data:  test_hours, sample_size, failures                       (E3, E4)
#   OR several test groups: groups = [{test_temp_c, test_hours, sample_size, failures}, ...]
#   OR report summary: fit or mttf_hours, plus ref_temp_c (default test_temp_c),
#                      conf_level (default 0.60) and failures (default 0)   (A11, E15)
#   ea_ev (optional): activation energy stated in the report; else the library default, 0.7 eV (A12)
#   unit_price_usd (optional): purchase price; else the Sheet2 average price for the candidate's slot
#                  (component type), whoever makes it (A14)
#   qty_per_vehicle (optional): how many of this part one vehicle uses (A10, default 1). It may differ
#                  between candidates of a slot

import re
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

from functions.arrhenius import EA_MAX, EA_MIN, accel_factor, effective_af, max_temperature
from functions.evidence import lambda_ci, lambda_percentile, mttf_hours
from functions.life_models import MODELS, mission_afr
from functions.library import SLOTS, load_library
from functions.reliability import DEFAULT_WARRANTY_HOURS, b_life, reliability, unreliability

DEFAULT_CONF_LEVEL = 0.60       # A11: the supplier convention when a report gives no confidence level
DEFAULT_TARGET_R = 0.999        # requirement: at most 0.1% failures over the mission (B0.1, E9)
CONFIDENCE = 0.95               # A13: required confidence that the target is met, fixed by team decision
MAX_JUNCTION_C = 150            # AEC-Q100 Grade 0 upper ambient limit; above it, warn
MAX_COMBINATIONS = 20_000
N_DRAWS, SEED = 5000, 5300        # A2 Ea Monte Carlo (only when the user chooses an Ea range)
SUMMARY_TEST_HOURS = 1000.0      # AEC-Q100 HTOL duration, assumed for report summaries (life models only)
DEFAULT_MISSION_HOURS = DEFAULT_WARRANTY_HOURS   # A7: 8 years x 1 powered-on h/day = 2,920 h
AEC_LOT_DEVICE_HOURS = 77 * 1000.0   # one AEC-Q100 HTOL lot: 77 devices x 1,000 h; smaller tests are flagged
DEFAULT_FLEET = 1000            # A14: warranty exposure is reported per 1,000 vehicles unless a fleet is given
PRICES_PATH = Path(__file__).resolve().parents[1] / "data" / "prices.csv"   # Sheet2, cleaned


# load_prices(): Sheet2 unit prices (data/prices.csv, built by code/01_clean_data.py)
def load_prices(path=PRICES_PATH):
    return pd.read_csv(path)


def _key(text):
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


# slot_of(): the slot name as SLOTS spells it, ignoring case, spaces and punctuation
# ("gate driver", "Gate-Driver" -> "Gate driver"), so a typed slot always finds its average price
def slot_of(text):
    for slot in SLOTS:
        if _key(slot) == _key(text):
            return slot
    return None


# price_for(): A14. The candidate's own price if given; else the Sheet2 average price for its slot
# (component type). Every unpriced candidate of a slot gets the same price, whether or not its maker is
# in our library, so cost differences come only from reliability and from prices the user enters.
def price_for(slot, name, unit_price=None, prices=None):
    if unit_price is not None and pd.notna(unit_price):
        if float(unit_price) < 0:
            raise ValueError(f"{name}: unit price can't be negative")
        return float(unit_price), "entered by user"
    prices = load_prices() if prices is None else prices
    avg = prices[(prices["slot"] == slot) & (prices["kind"] == "slot average")]
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


# groups_of(): a candidate's HTOL test groups as [(test_temp_c, n * t device-hours, failures, t hours), ...].
# t matters only for the lognormal / Weibull models; a report summary (FIT / MTTF) gives n * t alone, so
# t is taken as the standard 1,000 h HTOL (AEC-Q100), SUMMARY_TEST_HOURS.
# A report may pool several test groups at different temperatures and sizes (e.g. Renesas ISL78714's
# seven HTOL groups). Given as c["groups"] = [{test_temp_c, test_hours, sample_size, failures}, ...];
# otherwise the candidate's own fields are one group. A report summary (FIT / MTTF, E15) is one group.
def groups_of(c, ea_supplier):
    if c.get("groups"):
        out = []
        for g in c["groups"]:
            if g.get("test_temp_c") is None or pd.isna(g.get("test_temp_c")):
                raise ValueError(f"{c.get('name')}: every test group needs test_temp_c")
            nt, _ = evidence_device_hours({**g, "name": c.get("name")}, ea_supplier)
            f = int(g.get("failures") or 0)
            if f < 0:
                raise ValueError(f"{c.get('name')}: failures can't be negative")
            hours = float(g["test_hours"]) if g.get("test_hours") is not None and pd.notna(g.get("test_hours")) \
                else SUMMARY_TEST_HOURS
            out.append((float(g["test_temp_c"]), nt, f, hours))
        return out, "raw test data" if len(out) == 1 else f"raw test data, {len(out)} groups"
    if c.get("test_temp_c") is None or pd.isna(c.get("test_temp_c")):
        raise ValueError(f"{c.get('name')}: test_temp_c is required")
    nt, source = evidence_device_hours(c, ea_supplier)
    f = int(c.get("failures") or 0)
    if f < 0:
        raise ValueError(f"{c.get('name')}: failures can't be negative")
    hours = float(c["test_hours"]) if source == "raw test data" else SUMMARY_TEST_HOURS
    return [(float(c["test_temp_c"]), nt, f, hours)], source


# clean_candidates(): validate the user's candidates and resolve evidence and Ea for each
def clean_candidates(candidates, library=None, prices=None):
    if not candidates:
        raise ValueError("enter at least one candidate")
    ea0 = default_ea(library)
    prices = load_prices() if prices is None else prices
    rows, names = [], set()
    for c in candidates:
        c = dict(c)
        c["slot"] = slot_of(c.get("slot")) or c.get("slot")
        if c.get("slot") not in SLOTS:
            raise ValueError(f"{c.get('name')}: slot must be one of {', '.join(SLOTS)}")
        if not c.get("name"):
            raise ValueError("every candidate needs a name")
        if (c["slot"], c["name"]) in names:
            raise ValueError(f"duplicate candidate {c['name']!r} in {c['slot']}")
        names.add((c["slot"], c["name"]))
        stated = c.get("ea_ev") is not None and pd.notna(c.get("ea_ev"))
        ea = float(c["ea_ev"]) if stated else ea0
        groups, source = groups_of(c, ea)
        price, price_source = price_for(c["slot"], c["name"], c.get("unit_price_usd"), prices)
        temps = sorted({g[0] for g in groups})
        summary = not source.startswith("raw")
        conf_assumed = summary and (c.get("conf_level") is None or pd.isna(c.get("conf_level")))
        qty = c.get("qty_per_vehicle")
        qty = None if qty is None or pd.isna(qty) else qty
        rows.append({"slot": c["slot"], "name": c["name"], "supplier": c.get("supplier") or "",
                     "test_temp_c": temps[0] if len(temps) == 1 else "/".join(f"{t:g}" for t in temps),
                     "groups": groups, "test_groups": len(groups),
                     "device_hours_test": sum(g[1] for g in groups), "failures": sum(g[2] for g in groups),
                     "ea_ev": ea, "ea_source": "report" if stated else "library default (A12)",
                     "evidence_source": source, "unit_price_usd": price, "price_source": price_source,
                     "conf_level_assumed": conf_assumed, "qty_given": qty})
    out = pd.DataFrame(rows)
    out["slot"] = pd.Categorical(out["slot"], categories=SLOTS, ordered=True)
    return out.sort_values(["slot", "name"]).reset_index(drop=True)


# candidate_quantities(): A10, parts per vehicle for each candidate (team decision 2026-11-17). Each
# candidate's own qty_per_vehicle, else the slot value in `quantities` ({slot: n}, slot spelled in any case),
# else 1. Candidates of one slot may differ: each is its own case.
# Must be a whole number >= 1.
def candidate_quantities(cand, quantities=None):
    by_slot = {}
    for slot, n in (quantities or {}).items():
        s = slot_of(slot)
        if s is None:
            raise ValueError(f"quantity given for unknown slot {slot!r}")
        by_slot[s] = n
    out = {}
    for _, c in cand.iterrows():
        n = by_slot.get(c["slot"], 1) if c["qty_given"] is None or pd.isna(c["qty_given"]) else c["qty_given"]
        if float(n) != int(float(n)) or int(float(n)) < 1:
            raise ValueError(f"{c['name']}: quantity per vehicle must be a whole number of at least 1")
        out[c["name"]] = int(float(n))
    return out


CASES = ("estimate", "lower", "upper")     # the failure rate's estimate and 95% bounds (E4)
# Quantities that fall as the failure rate rises (MTTF, R, B0.1) take their LOWER bound from the
# rate's UPPER bound, so each output column's lower/upper is its own interval
FLIP = {"estimate": "estimate", "lower": "upper", "upper": "lower"}
RATES = CASES + ("upper_one_sided",)


@dataclass
class Selection:
    """Result of select(): candidate table, ranked combinations, warnings, settings."""
    candidates: pd.DataFrame        # one row per candidate, at the user's condition
    combinations: pd.DataFrame      # slot combinations ranked best first
    warnings: list
    settings: dict
    lam: dict = field(repr=False)   # candidate name -> failure rates at the use condition (baseline Ea):
                                    # estimate, lower, upper (two-sided 95%), upper_one_sided (95%, E18),
                                    # and at_max_temp (the estimate at the band's maximum temperature)
    lam_draws: dict = field(default_factory=dict, repr=False)   # Ea range only: name -> the same rates
                                                                # for every Ea draw
    picks: dict = field(default_factory=dict)      # the three best combinations (pick_combinations())


# rates(): E3-E4, E18 for one candidate: D = sum over its test groups of n t AF(group temperature ->
# the operating band, Ea), then the estimate, 95% bounds and one-sided 95% bound from the summed failures.
# ea may be one value or an array of Ea draws (the rates are then arrays).
# life_model (internal, E24-E26): "exponential" (the model users see) returns the rates themselves; for
# "lognormal" / "weibull" each rate becomes that model's average failure rate over the mission (AFR), fitted
# to the same expected test failures mu = lambda * D, with each group's n devices run t AF equivalent hours.
def rates(groups, condition, ea, life_model="exponential", shape=None, mission_hours=None):
    afs = [effective_af(condition, t_test, ea) for t_test, *_ in groups]
    d = sum(nt * af for (_, nt, _, _), af in zip(groups, afs))
    r = sum(g[2] for g in groups)
    out = lambda_ci(r, d)
    out["upper_one_sided"] = lambda_percentile(CONFIDENCE, r, d)
    if life_model != "exponential":
        units = [(nt / hours, hours * af) for (_, nt, _, hours), af in zip(groups, afs)]
        out = {k: mission_afr(life_model, units, v * d, mission_hours, shape) for k, v in out.items()}
    return out, d


# draw_ea(): A2, Ea draws from triangular(0.5, 0.7, 0.9) eV (most likely the 0.7 eV every report uses)
def draw_ea(size, rng, mode=0.7):
    return rng.triangular(EA_MIN, min(max(mode, EA_MIN), EA_MAX), EA_MAX, size=size)


def _q(x, p):
    return float(np.quantile(x, p))


# select(): the simulator. Every candidate is put on the user's condition with the course's
# exponential method: AF (E2; over a band, E6), device-hours D = sum of n t AF over its test groups (E3),
# and the failure rate's estimate and 95% bounds from the test's failures r (E4: lambda_hat = r / D, or
# -ln(0.5) / D when r = 0; chi-square bounds). The baseline is the estimate; the lower and upper columns
# rerun every output at the failure rate's 2.5th and 97.5th percentile (professor's feedback, 2026-11-14).
# condition: one temperature (C), or a band (t_min, t_max) the part runs across with time spread evenly
#   (team decision 2026-11-15); the estimate at t_max is reported as a worst case.
# Requirement (A13, E18-E19): R(mission_hours) >= target_r with 95% confidence, i.e. the one-sided 95%
# upper bound on the rate is at most -ln(target_r) / mission_hours (for a candidate: q times its bound).
# mission_hours defaults to 2,920 h (A7: the 8-year EV battery warranty x 1 powered-on hour per day).
# Quantity per vehicle (A10, E8): each candidate's qty_per_vehicle, else quantities = {slot: q}, else 1.
# FIT, MTTF, R and B0.1 of a candidate are for ONE part; its FIT per vehicle (q * FIT), failures, costs and
# target check are for the q parts a vehicle uses; a combination's rate is lambda_sys = sum of q_i * lambda_i.
# Candidates of a slot are ranked by FIT per vehicle, so the ranking agrees with the combinations.
# Warranty exposure (E12, A14) for fleet_size vehicles N (default 1,000) over warranty_hours t_w (default
# the mission), at the estimate and at each bound:
#   expected warranty failures of part i   = N * q_i * (1 - exp(-lambda_i * t_w))  (replacements)
#   warranty cost of part i                = expected failures of part i * cost per failure
#   cost per failure                       = replacement_cost if given, else the part's unit price
#                                            (each warranty failure replaces the failed part)
#   total cost                             = N * q_i * unit price + warranty cost
# Ea (A2, A12) for candidates whose report states none: ea_ev (default 0.7 eV), or, with ea_range=True,
# a Monte Carlo over Ea ~ triangular(0.5, 0.7, 0.9) eV (n_draws, seed); ea_shared=True gives every part
# the same draw (similar silicon), False a separate draw per part. The Ea columns then give the
# 2.5th-97.5th percentile of the estimate over the draws, and the full range combines them with the
# rate's own 95% bounds. A stated Ea is always used as given.
# life_model (internal comparison only, E24-E26, A16): "exponential" (default, the final model), or
# "lognormal" / "weibull" with shape sigma / beta (default: SEMATECH defect shapes). For those, every rate
# column is the average failure rate over the mission (AFR, Lesson 12), so R(mission), the target check and
# warranty failures over the mission are exact; B0.1 and MTTF then assume that average rate.
def select(candidates, condition, mission_hours=DEFAULT_MISSION_HOURS, target_r=DEFAULT_TARGET_R,
           warranty_hours=None, fleet_size=DEFAULT_FLEET, replacement_cost=None, ea_ev=None,
           ea_range=False, ea_shared=True, n_draws=N_DRAWS, seed=SEED, life_model="exponential", shape=None,
           conf=0.95, library=None, prices=None, top=None, quantities=None):
    if mission_hours <= 0:
        raise ValueError("mission hours must be positive")
    if not 0 < target_r < 1:
        raise ValueError("target reliability must be between 0 and 1")
    if fleet_size is None or fleet_size <= 0:
        raise ValueError("fleet size must be positive")
    if replacement_cost is not None and replacement_cost < 0:
        raise ValueError("replacement cost can't be negative")
    if life_model not in MODELS:
        raise ValueError(f"life model must be one of {MODELS}")
    if conf != 0.95:
        raise ValueError("the confidence interval is fixed at 95% (A13)")
    cand = clean_candidates(candidates, library, prices)
    qty = candidate_quantities(cand, quantities)
    t_w = mission_hours if warranty_hours is None else warranty_hours
    ea0 = default_ea(library) if ea_ev is None else float(ea_ev)
    target_rate = -np.log(target_r) / mission_hours
    t_max = max_temperature(condition)
    rng = np.random.default_rng(seed)
    shared = draw_ea(n_draws, rng, ea0) if ea_range else None

    # The AF (E2, E6) moves every candidate from its own test temperature to the user's condition in
    # either direction: AF > 1 below the test temperature, AF < 1 above it. Both are computed, but notes
    # flag inputs that weaken the answer (team decision 2026-11-17):
    #   - the condition goes above the 150 C automotive limit;
    #   - the condition goes above a part's test temperature (the test never reached it; AF < 1);
    #   - a test smaller than one AEC-Q100 HTOL lot (77 devices x 1,000 h);
    #   - a report FIT / MTTF without a confidence level (60% assumed, A11).
    warnings = []
    if t_max > MAX_JUNCTION_C:
        warnings.append(f"{t_max:g} C is above {MAX_JUNCTION_C} C, the usual maximum for automotive ICs "
                        "(AEC-Q100 Grade 0); check the parts are rated for it.")
    for _, c in cand.iterrows():
        top_test = max(g[0] for g in c["groups"])
        if t_max > top_test:
            warnings.append(f"{c['name']}: your temperature ({t_max:g} C) is above its test temperature "
                            f"({top_test:g} C), so the result is extrapolated beyond the test (AF < 1).")
        if c["evidence_source"].startswith("raw") and c["device_hours_test"] < AEC_LOT_DEVICE_HOURS:
            warnings.append(f"{c['name']}: small test ({c['device_hours_test']:,.0f} device-hours, less than one "
                            "AEC-Q100 lot of 77 devices x 1,000 h); its bounds are wide.")
        if c["conf_level_assumed"]:
            warnings.append(f"{c['name']}: the report value has no confidence level; 60% assumed (the "
                            "supplier convention, A11).")

    rows, lam, lam_draws = [], {}, {}
    for _, c in cand.iterrows():
        ea = c["ea_ev"] if c["ea_source"] == "report" else ea0
        lm = {"life_model": life_model, "shape": shape, "mission_hours": mission_hours}
        base, d = rates(c["groups"], condition, ea, **lm)
        base["at_max_temp"] = rates(c["groups"], t_max, ea, **lm)[0]["estimate"]
        lam[c["name"]] = base
        cost = c["unit_price_usd"] if replacement_cost is None else replacement_cost
        q = qty[c["name"]]
        purchase = fleet_size * q * c["unit_price_usd"]
        row = {"slot": c["slot"], "name": c["name"], "supplier": c["supplier"],
               "test_temp_c": c["test_temp_c"], "test_groups": c["test_groups"], "evidence": c["evidence_source"],
               "device_hours_test": c["device_hours_test"], "failures": c["failures"],
               "ea_ev": ea, "ea_source": c["ea_source"], "af_eff": d / c["device_hours_test"],
               "device_hours_use": d, "qty_per_vehicle": q,
               "unit_price_usd": c["unit_price_usd"], "price_source": c["price_source"],
               "cost_per_failure": cost,
               "cost_basis": "replacement at unit price" if replacement_cost is None else "user replacement cost",
               "purchase_cost": purchase}
        for case in CASES:
            lc, other = base[case], FLIP[case]
            fails = fleet_size * q * unreliability(lc, t_w)                     # E12, q parts per vehicle
            row.update({f"fit_{case}": lc * 1e9,                                # E5
                        f"mttf_hours_{other}": mttf_hours(lc),
                        f"r_mission_{other}": float(reliability(lc, mission_hours)),   # E7
                        f"b01_hours_{other}": float(b_life(lc)),                # E9
                        f"warranty_failures_{case}": float(fails),
                        f"warranty_cost_{case}": float(fails * cost),
                        f"total_cost_{case}": float(purchase + fails * cost)})
        # E17-E19: one-sided 95% lower confidence bound on R(mission) and the requirement check
        row["fit_upper_one_sided"] = base["upper_one_sided"] * 1e9
        for k in RATES:                                                 # A10: the q parts of one vehicle
            row[f"fit_per_vehicle_{k}"] = q * base[k] * 1e9
        # The supplier convention (A11, E4): the 60% upper bound, chi2(0.60; 2r + 2) / 2D. Shown in the details
        # so a user can set it next to a datasheet FIT; not used in any decision.
        row["fit_upper_60"] = lambda_percentile(0.60, c["failures"], d) * 1e9
        # for the q parts of this slot in one vehicle
        row["r_mission_lower_bound"] = float(reliability(q * base["upper_one_sided"], mission_hours))
        row["meets_target_at_confidence"] = bool(q * base["upper_one_sided"] <= target_rate)
        row["fit_at_max_temp"] = base["at_max_temp"] * 1e9
        if ea_range and c["ea_source"] != "report":
            ea_draws = shared if ea_shared else draw_ea(n_draws, rng, ea0)
            lam_draws[c["name"]] = rates(c["groups"], condition, ea_draws, **lm)[0]
        elif ea_range:
            lam_draws[c["name"]] = {k: np.full(n_draws, v) for k, v in base.items() if k in RATES}
        if ea_range:
            row.update(ea_columns(lam_draws[c["name"]], target_rate, qty=q))
        rows.append(row)
    table = pd.DataFrame(rows)
    # Rank in slot by FIT per vehicle (q * FIT; equals the FIT when q = 1), ties by its 97.5th percentile
    table["rank_in_slot"] = (table.groupby("slot", observed=True)["fit_per_vehicle_estimate"]
                             .rank(method="min").astype(int))
    table = table.sort_values(["slot", "rank_in_slot", "fit_per_vehicle_upper"]).reset_index(drop=True)

    combos, picks = rank_combinations(table, lam, lam_draws, mission_hours, target_rate, t_w, fleet_size, top)
    settings = {"condition": condition, "max_temperature": t_max, "mission_hours": mission_hours,
                "target_r": target_r, "confidence": CONFIDENCE, "warranty_hours": t_w, "fleet_size": fleet_size,
                "replacement_cost": replacement_cost,
                "cost_basis": "replacement at unit price" if replacement_cost is None else "user replacement cost",
                "target_fit": target_rate * 1e9, "default_ea": ea0, "life_model": life_model, "shape": shape, "ea_range": ea_range, "ea_shared": ea_shared,
                "n_draws": n_draws if ea_range else None, "seed": seed if ea_range else None,
                "quantities": qty, "default_mission": mission_hours == DEFAULT_MISSION_HOURS}
    return Selection(table, combos, list(dict.fromkeys(warnings)), settings, lam, lam_draws, picks)


# ea_columns(): A2 Monte Carlo summaries for one part or system (rates per Ea draw):
#   fit_ea_lower / fit_ea_upper:    2.5th-97.5th percentile of the estimate over the Ea draws
#   fit_full_lower / fit_full_upper: 2.5th percentile of the lower bound, 97.5th of the upper bound
#   meets_target_at_ea_worst:       the one-sided 95% bound (times qty, the parts per vehicle) still meets
#                                   the target at the 97.5th percentile Ea draw (the unfavourable end)
def ea_columns(draws, target_rate, prefix="", qty=1):
    return {f"{prefix}fit_ea_lower": _q(draws["estimate"], 0.025) * 1e9,
            f"{prefix}fit_ea_upper": _q(draws["estimate"], 0.975) * 1e9,
            f"{prefix}fit_full_lower": _q(draws["lower"], 0.025) * 1e9,
            f"{prefix}fit_full_upper": _q(draws["upper"], 0.975) * 1e9,
            f"{prefix}meets_target_at_ea_worst": bool(qty * _q(draws["upper_one_sided"], 0.975) <= target_rate)}


# rank_combinations(): every way of picking one candidate per entered slot (empty slots are left
# out of the system). Series system (E8): lambda_sys = sum of q_i times the chosen candidates' rates,
# q_i the parts per vehicle of each slot (A10). The
# estimate sums the estimates; the lower and upper columns put EVERY part at its 2.5th or 97.5th
# percentile at once, a deliberately wide scenario range rather than a 95% CI of the sum.
# Requirement (A13): the sum of the parts' one-sided 95% upper bounds (conservative) is at most the
# target rate. With an Ea range, the system's rates are summed draw by draw (shared Ea moves every part
# together). Ranked by estimated system FIT.
def rank_combinations(table, lam, lam_draws, mission_hours, target_rate, t_w, fleet_size, top):
    slots = [s for s in SLOTS if s in set(table["slot"])]
    choices = [list(table.loc[table["slot"] == s, "name"]) for s in slots]
    n_combos = int(np.prod([len(c) for c in choices]))
    if n_combos > MAX_COMBINATIONS:
        # Too many to list: keep the top 3 candidates per slot by estimated FIT
        choices = [list(table[table["slot"] == s].nsmallest(3, "fit_per_vehicle_estimate")["name"]) for s in slots]
    info = table.set_index("name")
    q = info["qty_per_vehicle"].to_dict()
    rows = []
    for combo in product(*choices):
        row = {"combination": " + ".join(combo), **{s: n for s, n in zip(slots, combo)}}
        purchase = float(sum(info.loc[n, "purchase_cost"] for n in combo))
        for case in CASES:
            ls, other = sum(q[n] * lam[n][case] for n in combo), FLIP[case]
            # Warranty exposure: each part's failures cost that part's cost per failure (E12, A14)
            warranty = float(sum(fleet_size * q[n] * unreliability(lam[n][case], t_w) * info.loc[n, "cost_per_failure"]
                                 for n in combo))
            row.update({f"system_fit_{case}": ls * 1e9,
                        f"system_r_mission_{other}": float(reliability(ls, mission_hours)),
                        f"system_b01_hours_{other}": float(b_life(ls)),
                        f"warranty_failures_{case}": float(fleet_size * unreliability(ls, t_w)),
                        f"warranty_cost_{case}": warranty,
                        f"total_cost_{case}": purchase + warranty})
        l95 = sum(q[n] * lam[n]["upper_one_sided"] for n in combo)
        row.update({"purchase_cost": purchase, "system_fit_upper_one_sided": l95 * 1e9,
                    "system_r_lower_bound": float(reliability(l95, mission_hours)),
                    "meets_target_at_confidence": bool(l95 <= target_rate),
                    "system_fit_at_max_temp": sum(q[n] * lam[n]["at_max_temp"] for n in combo) * 1e9})
        if lam_draws:
            sys_draws = {k: sum(q[n] * lam_draws[n][k] for n in combo) for k in RATES}
            row.update(ea_columns(sys_draws, target_rate, "system_"))
        rows.append(row)
    rows.sort(key=lambda r: (r["system_fit_estimate"], r["system_fit_upper"]))
    best_total = rows[0]["total_cost_estimate"]
    out = [{"rank": k, **r, "extra_cost_vs_best": r["total_cost_estimate"] - best_total}
           for k, r in enumerate(rows if top is None else rows[:top], start=1)]
    return pd.DataFrame(out), pick_combinations(out)


# pick_combinations(): the three best combinations shown to the user (team decision 2026-11-16):
#   most_reliable: the lowest estimated system failure rate (rank 1)
#   safest:        the lowest one-sided 95% maximum system failure rate (rewards larger tests)
#   cheapest:      the lowest estimated total cost AMONG combinations that meet the target; None if
#                  none does (a cheap combination that fails the target is never suggested)
def pick_combinations(rows):
    meeting = [r for r in rows if r["meets_target_at_confidence"]]
    return {"most_reliable": dict(rows[0]),
            "safest": dict(min(rows, key=lambda r: (r["system_fit_upper_one_sided"], r["system_fit_estimate"]))),
            "cheapest": dict(min(meeting, key=lambda r: r["total_cost_estimate"])) if meeting else None,
            "n_combinations": len(rows), "n_meeting_target": len(meeting)}


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
