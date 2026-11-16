# finance.py
# Financial impact of a supplier choice (ROADMAP Section 10, E12, E22-E23, A14).
# One baseline setting (the failure rate's estimate) and the same calculation rerun with every part at
# its 2.5th and at its 97.5th percentile failure rate (professor's feedback, 2026-11-14), comparing a
# "before" combination with an "after" one.

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
# sel: Selection from candidates.select();  parts: candidate names, one per slot
def combination_costs(sel, parts, case="estimate", fleet_size=None, warranty_hours=None):
    if case not in CASES:
        raise ValueError(f"case must be one of {CASES}")
    info = sel.candidates.set_index("name")
    n = sel.settings["fleet_size"] if fleet_size is None else fleet_size
    t_w = sel.settings["warranty_hours"] if warranty_hours is None else warranty_hours
    lam_sys = sum(sel.lam[p][case] for p in parts)
    warranty = float(sum(n * unreliability(sel.lam[p][case], t_w) * info.loc[p, "cost_per_failure"]
                         for p in parts))
    purchase = float(sum(n * info.loc[p, "unit_price_usd"] for p in parts))
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
