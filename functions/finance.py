# finance.py
# Financial impact of a supplier choice (ROADMAP Section 10, E12, E22-E23, A14).
# Follows the course's financial-analysis pattern: compute the quantity of interest in every
# simulated draw, multiply by its cost, then report the median, standard error and 95% interval,
# and compare a "before" scenario with an "after" one on the same (paired) draws.

import numpy as np

from functions.reliability import unreliability


# qi_cost(): the course's quantities of interest for a vector of simulated costs
def qi_cost(x, cl=0.95):
    x = np.asarray(x, dtype=float)
    lo, med, hi = np.quantile(x, [(1 - cl) / 2, 0.5, (1 + cl) / 2])
    return {"estimate": float(med), "se": float(x.std(ddof=1)), "lower": float(lo), "upper": float(hi)}


# combination_costs(): E12 per draw for one combination of candidates from a select() result.
# Each part's expected warranty failures N * F_i(t_w) cost that part's cost per failure (A14); the
# system's failures are N * F_sys(t_w). Purchase = N * sum of unit prices (no uncertainty).
# sel: Selection from candidates.select();  parts: candidate names, one per slot
def combination_costs(sel, parts, fleet_size=None, warranty_hours=None):
    info = sel.candidates.set_index("name")
    n = sel.settings["fleet_size"] if fleet_size is None else fleet_size
    t_w = sel.settings["warranty_hours"] if warranty_hours is None else warranty_hours
    lam_sys = sum(sel.lam[p] for p in parts)
    warranty = sum(n * unreliability(sel.lam[p], t_w) * info.loc[p, "cost_per_failure"] for p in parts)
    purchase = float(sum(n * info.loc[p, "unit_price_usd"] for p in parts))
    return {"failures": n * unreliability(lam_sys, t_w), "warranty_cost": warranty,
            "purchase_cost": np.full(len(lam_sys), purchase), "total_cost": purchase + warranty}


# compare_costs(): E22, after minus before for every cost, draw by draw (paired, common random
# numbers), summarized as qi_cost(); savings = before - after (positive = the change saves money)
def compare_costs(before, after, cl=0.95):
    out = {}
    for key in ("failures", "warranty_cost", "purchase_cost", "total_cost"):
        out[f"before_{key}"] = qi_cost(before[key], cl)
        out[f"after_{key}"] = qi_cost(after[key], cl)
        out[f"saving_{key}"] = qi_cost(before[key] - after[key], cl)
    saving = before["total_cost"] - after["total_cost"]
    out["p_after_cheaper"] = float(np.mean(saving > 0))
    out["p_after_fewer_failures"] = float(np.mean(after["failures"] < before["failures"]))
    return out


# break_even_repair_cost(): E23, the cost of one warranty repair at which the warranty saving of
# the change equals its extra purchase cost:  C* = (purchase_after - purchase_before) / failures avoided.
# Computed per draw where the change avoids failures. If the change does not cost more to buy
# (premium <= 0), it pays off at any repair cost and C* = 0.
def break_even_repair_cost(before, after, cl=0.95):
    premium = float(after["purchase_cost"][0] - before["purchase_cost"][0])
    avoided = before["failures"] - after["failures"]
    share_avoids = float(np.mean(avoided > 0))
    if premium <= 0:
        return {"premium": premium, "share_draws_avoiding_failures": share_avoids,
                "estimate": 0.0, "lower": 0.0, "upper": 0.0, "pays_off_at_any_repair_cost": True}
    c = premium / avoided[avoided > 0]
    q = qi_cost(c, cl) if len(c) > 1 else {"estimate": np.inf, "lower": np.inf, "upper": np.inf}
    return {"premium": premium, "share_draws_avoiding_failures": share_avoids,
            "estimate": q["estimate"], "lower": q["lower"], "upper": q["upper"],
            "pays_off_at_any_repair_cost": False}
