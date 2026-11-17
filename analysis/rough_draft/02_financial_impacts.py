# 02_financial_impacts.py
# Rough draft: financial impacts of choosing suppliers with the simulator (ROADMAP Section 10b, E12, E22,
# E30-E31, A14, A17-A19). Writes reports/rough_draft/financial/{tables,figures}/ and
# key_numbers_financial.md. The Financial Impacts report (reports/financial_impacts/) is not touched.
#
# Cost of poor quality (COPQ) of a combination for a fleet of N vehicles over the warranty (2,920 h):
#   warranty replacements = sum_i N q_i (1 - exp(-lambda_i t_w)) x unit price_i                  (E12)
#   expected recall cost  = sum_s P(Poisson(mu_s) >= k) x N x cost per recalled vehicle          (E30-E31)
#   COPQ = warranty replacements + expected recall cost;  total = purchase + COPQ
# Before = the least reliable combination (a choice made without the simulator); after = the simulator's
# most reliable combination. Every number at the failure-rate estimate and with every part at its 2.5th and
# 97.5th percentile (professor's feedback, 2026-11-14).
#   .venv/Scripts/python analysis/rough_draft/02_financial_impacts.py

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.extend([str(HERE), str(HERE.parent)])
import case_study as cs  # noqa: E402
import plots  # noqa: E402
from functions.candidates import CASES  # noqa: E402
from functions.finance import combination_costs, recall_risk  # noqa: E402

OUT = cs.OUT / "financial"
TABLES, FIGURES = OUT / "tables", OUT / "figures"
QTYS = ("field_failures", "p_any_recall", "warranty_cost", "expected_recall_cost", "copq", "purchase_cost",
        "total_cost")


def costs(sel, parts, case, k=cs.K_BASE, recall_cost=cs.RECALL_COST["base"], fleet=cs.FLEET):
    c = combination_costs(sel, parts, case, fleet_size=fleet)
    r = recall_risk(sel, parts, k, recall_cost, fleet, case)
    out = {"field_failures": r["expected_field_failures"], "p_any_recall": r["p_any_recall"],
           "warranty_cost": c["warranty_cost"], "expected_recall_cost": r["expected_recall_cost"],
           "purchase_cost": c["purchase_cost"]}
    out["copq"] = out["warranty_cost"] + out["expected_recall_cost"]
    out["total_cost"] = out["purchase_cost"] + out["copq"]
    return out, r["parts"]


def before_after(sel, before, after, label, **kw):
    rows = []
    for case in CASES:
        b, _ = costs(sel, cs.parts_of(before), case, **kw)
        a, _ = costs(sel, cs.parts_of(after), case, **kw)
        for q in QTYS:
            rows.append({"condition": label, "case": case, "quantity": q, "before": b[q], "after": a[q],
                         "saving": b[q] - a[q]})
    return pd.DataFrame(rows)


def recall_by_slot(sel, before, after):
    rows = []
    for role, combo in (("before", before), ("after", after)):
        for case in CASES:
            _, parts = costs(sel, cs.parts_of(combo), case)
            for p in parts:
                rows.append({"role": role, "case": case, **p})
    return pd.DataFrame(rows)


def all_combinations(sel):
    rows = []
    for _, c in sel.combinations.iterrows():
        parts = cs.parts_of(c)
        row = {"combination": c["combination"], "system_fit_estimate": c["system_fit_estimate"],
               "meets_target": c["meets_target_at_confidence"],
               "short": " + ".join(p.split("-")[0][:8] for p in parts)}
        for case in CASES:
            r, _ = costs(sel, parts, case)
            row.update({f"copq_{case}": r["copq"], f"p_any_recall_{case}": r["p_any_recall"],
                        f"total_cost_{case}": r["total_cost"]})
        row["purchase_cost"] = r["purchase_cost"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values("system_fit_estimate").reset_index(drop=True)


def recall_vs_temperature(before, after, temps=range(25, 126, 5)):
    """P(at least one recall) and COPQ of the baseline before/after combinations across temperature."""
    rows = []
    for temp in temps:
        sel = cs.run(temp)
        combos = sel.combinations.set_index("combination", drop=False)
        for label, name in (("after: most reliable", after), ("before: least reliable", before)):
            row = {"temperature_c": temp, "system": label, "combination": name}
            for case in ("estimate", "upper"):
                r, _ = costs(sel, cs.parts_of(combos.loc[name].to_dict()), case)
                row[f"p_any_recall_{case}"], row[f"copq_{case}"] = r["p_any_recall"], r["copq"]
            rows.append(row)
    return pd.DataFrame(rows)


def scenarios(sels, before_after_names):
    """COPQ saving (before - after) over the recall trigger, cost per recalled vehicle and fleet size, at the
    estimate and at the 97.5th percentile, for the baseline condition and the 40-105 C band."""
    rows = []
    for label, sel in sels.items():
        combos = sel.combinations.set_index("combination", drop=False)
        before, after = (combos.loc[n].to_dict() for n in before_after_names[label])
        for k in cs.TRIGGERS:
            for cost_label, rc in cs.RECALL_COST.items():
                for fleet in cs.FLEETS:
                    r = {"condition": label, "recall_trigger_k": k, "recall_cost_level": cost_label,
                         "recall_cost_per_vehicle": rc, "fleet": fleet}
                    for case in ("estimate", "upper"):
                        b, _ = costs(sel, cs.parts_of(before), case, k, rc, fleet)
                        a, _ = costs(sel, cs.parts_of(after), case, k, rc, fleet)
                        r[f"copq_saving_{case}"] = b["copq"] - a["copq"]
                        r[f"p_recall_before_{case}"], r[f"p_recall_after_{case}"] = b["p_any_recall"], a["p_any_recall"]
                    rows.append(r)
    return pd.DataFrame(rows)


def premium_check(sel):
    """Most reliable vs the cheapest combination that meets the target: the extra purchase cost of the most
    reliable choice, the COPQ it avoids, and the recall cost per vehicle at which they break even (E23 with
    the recall term): C* = (premium - warranty saving) / (N x sum of the drop in P(recall) over the slots)."""
    rel, cheap = sel.picks["most_reliable"], sel.picks["cheapest"]
    rows = []
    for case in CASES:
        a, pa = costs(sel, cs.parts_of(rel), case)
        b, pb = costs(sel, cs.parts_of(cheap), case)
        premium = a["purchase_cost"] - b["purchase_cost"]
        dp = sum(x["p_recall"] for x in pb) - sum(x["p_recall"] for x in pa)
        dw = b["warranty_cost"] - a["warranty_cost"]
        rows.append({"case": case, "most_reliable": rel["combination"], "cheapest_meeting": cheap["combination"],
                     "purchase_premium": premium, "copq_avoided": b["copq"] - a["copq"],
                     "net_saving": b["total_cost"] - a["total_cost"],
                     "break_even_recall_cost_per_vehicle": (premium - dw) / (cs.FLEET * dp) if dp > 0 else float("inf")})
    return pd.DataFrame(rows)


def money(x):
    return f"${x:,.0f}"


def key_numbers(ba, by_slot, scen, prem, sel, before, after):
    s = sel.settings
    lines = [
        "# Rough draft: financial impacts key numbers (generated by analysis/rough_draft/02_financial_impacts.py)", "",
        f"Fleet N = {cs.FLEET:,} vehicles (one model year, A18), warranty 2,920 h (A7), 55 C, Ea 0.7 eV. Purchase at "
        "Sheet2 distributor prices (A15; TMCS1101 at the current-sensor average), realistic quantities per vehicle "
        f"(A17). Recall assumed at k = {cs.K_BASE} field failures of one part type (A18), costing "
        f"${cs.RECALL_COST['base']:.0f} per recalled vehicle (A19: NADA average recall repair; low $205, high $850).",
        "Every number: estimate (2.5th - 97.5th percentile case). The 2.5th percentile case is 0 for zero-failure "
        "parts.", "",
        f"- Before (least reliable, chosen without the simulator): {before}",
        f"- After (simulator's most reliable pick): {after}", "",
        "## Before vs after, baseline (55 C)"]
    t = ba[ba["condition"] == "55 C"].pivot_table(index="quantity", columns="case", values=["before", "after", "saving"])
    labels = {"field_failures": "Expected field failures in the fleet", "p_any_recall": "P(at least one recall)",
              "warranty_cost": "Warranty replacements (part price)", "expected_recall_cost": "Expected recall cost",
              "copq": "Cost of poor quality (warranty + recall)", "purchase_cost": "Purchase",
              "total_cost": "Total (purchase + COPQ)"}
    for q in QTYS:
        f = (lambda x: f"{x:.3g}") if q in ("field_failures", "p_any_recall") else money
        parts = []
        for col in ("before", "after", "saving"):
            parts.append(f"{col} {f(t.loc[q, (col, 'estimate')])} ({f(t.loc[q, (col, 'lower')])} - "
                         f"{f(t.loc[q, (col, 'upper')])})")
        lines.append(f"- {labels[q]}: " + "; ".join(parts))
    lines += ["", "## Which part types carry the recall risk (estimate)"]
    est = by_slot[by_slot["case"] == "estimate"]
    for _, r in est.iterrows():
        lines.append(f"- {r['role']}: {r['slot']} {r['part']}: {r['expected_failures']:.2f} expected field failures, "
                     f"P(recall) {r['p_recall']:.2g}")
    hot = ba[(ba["condition"] != "55 C") & (ba["quantity"] == "copq")].set_index("case")
    lines += ["", f"## Hotter condition ({ba['condition'].iloc[-1]})",
              f"- COPQ before {money(hot.loc['estimate', 'before'])}, after {money(hot.loc['estimate', 'after'])}, "
              f"saving {money(hot.loc['estimate', 'saving'])} ({money(hot.loc['lower', 'saving'])} - "
              f"{money(hot.loc['upper', 'saving'])})"]
    lines += ["", "## Scenarios (COPQ saving before - after; estimate / 97.5th percentile)"]
    base_fleet = scen[scen["fleet"] == cs.FLEET]
    for _, r in base_fleet.iterrows():
        lines.append(f"- {r['condition']}, k = {r['recall_trigger_k']}, {money(r['recall_cost_per_vehicle'])}/vehicle: "
                     f"{money(r['copq_saving_estimate'])} / {money(r['copq_saving_upper'])}")
    lines += ["", "## What the fix takes",
              f"- Purchase: the after combination is {money(ba[(ba['condition'] == '55 C') & (ba['quantity'] == 'purchase_cost')]['saving'].iloc[0])} "
              "cheaper to buy than the before combination per fleet, so the change needs no extra purchase money.",
              "- Most reliable vs cheapest combination that meets the target:"]
    for _, r in prem.iterrows():
        lines.append(f"  - {r['case']}: purchase premium {money(r['purchase_premium'])}, COPQ avoided "
                     f"{money(r['copq_avoided'])}, net {money(r['net_saving'])}; break-even recall cost "
                     + ("n/a (no recall risk avoided)" if r["break_even_recall_cost_per_vehicle"] == float("inf")
                        else "not reached at any realistic cost" if r["break_even_recall_cost_per_vehicle"] > 1e5
                        else f"{money(r['break_even_recall_cost_per_vehicle'])} per vehicle"))
    lines += ["- Not costed (gaps to name in the report): engineering time to qualify a new supplier, labour and "
              "logistics beyond the recall repair figure, brand damage."]
    return "\n".join(lines) + "\n"


def main():
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    sel, hot = cs.run(), cs.run(cs.BAND)
    names = {}
    for label, s in (("55 C", sel), ("40-105 C band", hot)):
        names[label] = (cs.least_reliable(s)["combination"], s.picks["most_reliable"]["combination"])
    before, after = names["55 C"]
    ba = pd.concat([before_after(sel, cs.least_reliable(sel), sel.picks["most_reliable"], "55 C"),
                    before_after(hot, cs.least_reliable(hot), hot.picks["most_reliable"], "40-105 C band")])
    by_slot = recall_by_slot(sel, cs.least_reliable(sel), sel.picks["most_reliable"])
    combos = all_combinations(sel)
    scen = scenarios({"55 C": sel, "40-105 C band": hot}, names)
    prem = premium_check(sel)
    curve = recall_vs_temperature(before, after)
    for name, t in (("fin_1_before_after", ba), ("fin_2_recall_by_slot", by_slot), ("fin_3_all_combinations", combos),
                    ("fin_4_scenarios", scen), ("fin_5_most_reliable_vs_cheapest", prem),
                    ("fin_6_recall_vs_temperature", curve)):
        t.to_csv(TABLES / f"{name}.csv", index=False)
    plots.rd_fin1_recall(curve, FIGURES / "figure_f1_recall_risk.png", cs.K_BASE, cs.FLEET)
    (OUT / "key_numbers_financial.md").write_text(key_numbers(ba, by_slot, scen, prem, sel, before, after),
                                                  encoding="utf-8")
    print(f"Wrote {OUT.relative_to(cs.ROOT)}")


if __name__ == "__main__":
    main()
