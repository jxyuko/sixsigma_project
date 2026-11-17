# finance.py
# Financial impact of a supplier choice (ROADMAP Section 10, E12, E22-E23, A14).
# One baseline setting (the failure rate's estimate) and the same calculation rerun with every part at
# its 2.5th and at its 97.5th percentile failure rate (professor's feedback, 2026-11-14), comparing a
# "before" combination with an "after" one.

from scipy.stats import poisson

from functions.candidates import CASES
from functions.reliability import unreliability

QUANTITIES = ("failures", "warranty_cost", "purchase_cost", "total_cost")


# combination_costs(): E12 for one combination of candidates from a select() result, at one case
# ("estimate", "lower" or "upper" failure rates). Warranty exposure for N vehicles over the warranty t_w:
#   warranty cost = sum_i N * (1 - exp(-lambda_i * t_w)) * cost per failure_i
# with cost per failure_i = the part's unit price (the failed part is replaced) unless a replacement
# cost is given. 'failures' is the system's N * F_sys(t_w) = N * (1 - exp(-lambda_sys * t_w)), which
# equals the sum of the parts' expected failures to first order when F is small.
# Purchase = N * sum of unit prices (fixed prices: the same in every case).
# Quantities per vehicle q_i (A10) come from the select() result: lambda_sys = sum q_i lambda_i, part i's
# replacements N q_i (1 - exp(-lambda_i t_w)), purchase N sum q_i price_i.
# sel: Selection from candidates.select();  parts: candidate names, one per slot
def combination_costs(sel, parts, case="estimate", fleet_size=None, warranty_hours=None):
    if case not in CASES:
        raise ValueError(f"case must be one of {CASES}")
    info = sel.candidates.set_index("name")
    n = sel.settings["fleet_size"] if fleet_size is None else fleet_size
    t_w = sel.settings["warranty_hours"] if warranty_hours is None else warranty_hours
    q = info["qty_per_vehicle"] if "qty_per_vehicle" in info else {p: 1 for p in parts}
    lam_sys = sum(q[p] * sel.lam[p][case] for p in parts)
    warranty = float(sum(n * q[p] * unreliability(sel.lam[p][case], t_w) * info.loc[p, "cost_per_failure"]
                         for p in parts))
    purchase = float(sum(n * q[p] * info.loc[p, "unit_price_usd"] for p in parts))
    return {"failures": float(n * unreliability(lam_sys, t_w)), "warranty_cost": warranty,
            "purchase_cost": purchase, "total_cost": purchase + warranty}


# compare_costs(): E22, before, after and saving = before - after (positive = the change saves money)
def compare_costs(before, after):
    out = {}
    for key in QUANTITIES:
        out[f"before_{key}"], out[f"after_{key}"] = before[key], after[key]
        out[f"saving_{key}"] = before[key] - after[key]
    return out


# break_even_replacement_cost(): E23, the cost of one warranty replacement at which the warranty saving
# of the change equals its extra purchase cost:  C* = (purchase_after - purchase_before) / failures avoided.
# If the change does not cost more to buy (premium <= 0), it pays off at any replacement cost (C* = 0);
# if it avoids no failures, no replacement cost repays it (C* = inf).
def break_even_replacement_cost(before, after):
    premium = after["purchase_cost"] - before["purchase_cost"]
    avoided = before["failures"] - after["failures"]
    if premium <= 0:
        return {"premium": premium, "failures_avoided": avoided, "break_even": 0.0,
                "pays_off_at_any_replacement_cost": True}
    return {"premium": premium, "failures_avoided": avoided,
            "break_even": premium / avoided if avoided > 0 else float("inf"),
            "pays_off_at_any_replacement_cost": False}


# recall_probability(): E30, the chance that a part type is recalled (A18). Field failures of one part type
# in a fleet are Poisson with mean mu = N * (1 - exp(-q * lambda * t_w)) (expected vehicles with that part
# failed); a recall is assumed once the count reaches the trigger k:  P(recall) = P(X >= k) = 1 - P(X <= k-1).
# mu: expected field failures (number or array);  k: recall trigger, a whole number >= 1
def recall_probability(mu, k):
    if int(k) != k or k < 1:
        raise ValueError("the recall trigger k must be a whole number of at least 1")
    if (mu < 0).any() if hasattr(mu, "any") else mu < 0:
        raise ValueError("expected failures can't be negative")
    return poisson.sf(k - 1, mu)


# recall_risk(): E30-E31 for one combination at one case. Recalls are per part type (one campaign per
# defective component), so each slot s of the combination gets its own expected field failures
#   mu_s = N * (1 - exp(-q_s * lambda_s * t_w)),   P_s = P(Poisson(mu_s) >= k)
# and the expected recall cost is  sum_s P_s * N * C_recall  (every vehicle of the fleet is recalled).
# P(at least one recall) = 1 - prod_s (1 - P_s) (independent part types, A4).
# Returns the per-slot mu and P plus the combination totals.
def recall_risk(sel, parts, k, cost_per_vehicle, fleet_size, case="estimate", warranty_hours=None):
    if case not in CASES:
        raise ValueError(f"case must be one of {CASES}")
    if fleet_size <= 0 or cost_per_vehicle < 0:
        raise ValueError("need a positive fleet and a non-negative recall cost")
    info = sel.candidates.set_index("name")
    t_w = sel.settings["warranty_hours"] if warranty_hours is None else warranty_hours
    rows, p_none, cost = [], 1.0, 0.0
    for p in parts:
        q = int(info.loc[p, "qty_per_vehicle"]) if "qty_per_vehicle" in info else 1
        mu = float(fleet_size * unreliability(q * sel.lam[p][case], t_w))
        pr = float(recall_probability(mu, k))
        rows.append({"part": p, "slot": str(info.loc[p, "slot"]), "expected_failures": mu, "p_recall": pr})
        p_none *= 1 - pr
        cost += pr * fleet_size * cost_per_vehicle
    return {"parts": rows, "p_any_recall": 1 - p_none, "expected_recall_cost": cost,
            "expected_field_failures": sum(r["expected_failures"] for r in rows)}
