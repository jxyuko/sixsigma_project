# 03_financial_impacts.py
# Financial impact of the supplier change the simulator recommends (ROADMAP Section 10).
# Kept apart from the simulator: it only CALLS functions/ and writes to reports/financial_impacts/.
#
# Change evaluated: BEFORE = the least reliable combination of our library candidates,
#                   AFTER  = the simulator's recommended (most reliable) combination.
# Cost per 1,000 vehicles (A14): purchase at Sheet2 distributor prices, plus expected warranty
# failures over the mission x the part's unit price (parts-only, a lower bound on repair cost).
# Conditions: 55 C (as in the Preliminary Results) and the hotter 40/70/105 C profile, 2,920 h (A7).
# Price cases (A15): the library's Sheet2 prices, where both MCUs are FAMILY PROXIES (C2000 priced as
# F2800157, RH850 as R7F7016843), and a sensitivity with both MCUs at the Sheet2 ECU average, which
# removes the proxy price difference and leaves the other slots' real price differences.
# Uncertainty: the simulator's 5,000 paired draws (common random numbers), summarized like the
# course's financial-analysis example: median, standard error and 95% interval.
#
# Run from the project root:  .venv/Scripts/python analysis/03_financial_impacts.py   (~10 seconds)

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
sys.path.append(str(Path(__file__).resolve().parent))
import plots  # noqa: E402  (plotnine figures, analysis/plots.py)
from caveats import DATA_CAVEAT  # noqa: E402
from functions.candidates import library_candidate, load_prices, select  # noqa: E402
from functions.finance import break_even_repair_cost, combination_costs, compare_costs  # noqa: E402
from functions.library import SLOTS, load_library  # noqa: E402
from functions.simulator import DEFAULT_WARRANTY_HOURS, N_DRAWS, SEED  # noqa: E402

OUT = ROOT / "reports" / "financial_impacts"
TABLES, FIGURES = OUT / "tables", OUT / "figures"
MISSION, TARGET, FLEET = DEFAULT_WARRANTY_HOURS, 0.999, 1000
CONDITIONS = {"55 C": 55.0, "40/70/105 C profile": [(40, 0.5), (70, 0.3), (105, 0.2)]}
CANDIDATES = ["F280049CPZQR", "R7F7016903AFP-C", "BQ79656PAPRQ1", "LTC6811-1", "ISO7741QDWRQ1",
              "ADuM141E", "TMP4719QDGSRQ1", "UCC21750QDWRQ1", "ADuM4135", "TMCS1101A4UQDRQ1"]
BEFORE, AFTER = "before: least reliable suppliers", "after: recommended suppliers"
MAIN, EQUAL_MCU = "Sheet2 prices (MCU family proxies)", "equal MCU prices (Sheet2 ECU average)"


def candidates(lib, price_case=MAIN):
    """Library parts as candidates, priced from the library's Sheet2 match (family proxy where flagged,
    A15); parts with no library price fall back to the Sheet2 slot average inside select() (A14).
    EQUAL_MCU sets both MCUs to the Sheet2 ECU average."""
    prices = load_prices().query("kind == 'slot average'").set_index("slot")["unit_price_usd"]
    out = []
    for part in CANDIDATES:
        c = library_candidate(part, lib)
        price = lib.set_index("part").loc[part, "unit_price_usd"]
        if price_case == EQUAL_MCU and c["slot"] == "ECU MCU":
            c["unit_price_usd"] = float(prices["ECU MCU"])
        elif pd.notna(price):
            c["unit_price_usd"] = float(price)
        out.append(c)
    return out


def price_source(lib, part, slot, price_case):
    """Where each price came from, for the tables (replaces select()'s generic 'entered by user')."""
    r = lib.set_index("part").loc[part]
    if price_case == EQUAL_MCU and slot == "ECU MCU":
        return "Sheet2 average for ECU MCU (sensitivity)"
    if pd.isna(r["unit_price_usd"]):
        return f"Sheet2 average for {slot}"
    proxy = " (family proxy)" if "proxy" in str(r["flag"]) else (" (orderable variant)" if "variant" in str(r["flag"]) else "")
    return f"Sheet2 price of {r['price_part']}{proxy}"


def parts_of(row):
    return [row[s] for s in SLOTS if s in row.index and isinstance(row[s], str)]


def run_condition(label, profile, lib, price_case=MAIN):
    sel = select(candidates(lib, price_case), profile, MISSION, TARGET, fleet_size=FLEET, top=100)
    after_row, before_row = sel.combinations.iloc[0], sel.combinations.iloc[-1]
    before = combination_costs(sel, parts_of(before_row))
    after = combination_costs(sel, parts_of(after_row))
    cmp = compare_costs(before, after)
    be = break_even_repair_cost(before, after)
    return sel, before_row, after_row, cmp, be


def long_table(label, price_case, cmp):
    rows = []
    for key in ("failures", "warranty_cost", "purchase_cost", "total_cost"):
        for scen, prefix in ((BEFORE, "before"), (AFTER, "after"), ("saving (before - after)", "saving")):
            rows.append({"condition": label, "price_case": price_case, "scenario": scen, "quantity": key,
                         **cmp[f"{prefix}_{key}"]})
    return rows


def price_table(sel, lib, price_case):
    t = sel.candidates.copy()
    t["price_source"] = [price_source(lib, n, s, price_case) for n, s in zip(t["name"], t["slot"])]
    return t[["slot", "name", "supplier", "unit_price_usd", "price_source", "fit_median", "fit_lower", "fit_upper",
              "warranty_failures_median", "warranty_failures_lower", "warranty_failures_upper",
              "warranty_cost_median", "purchase_cost", "total_cost_median"]].rename(columns={"name": "part"})


def key_numbers(summary, ba, be_rows, prices55):
    def q(cond, scen, qty, fmt="{:,.2f}"):
        r = ba[(ba["condition"] == cond) & (ba["price_case"] == case) & (ba["scenario"] == scen)
               & (ba["quantity"] == qty)].iloc[0]
        return f"{fmt.format(r['estimate'])} (95% CI {fmt.format(r['lower'])}-{fmt.format(r['upper'])}; SE {fmt.format(r['se'])})"

    lines = ["# Financial Impacts: key numbers (generated by analysis/03_financial_impacts.py)", "",
             DATA_CAVEAT,
             "For the financial result this means: the BEFORE combination is the least reliable by the evidence in",
             "our table, which under-rates the RH850; the purchase difference also depends on MCU proxy prices (A15).",
             "",
             f"Change: BEFORE = least reliable supplier combination, AFTER = recommended (most reliable) combination.",
             f"Per {FLEET:,} vehicles, mission {MISSION:,.0f} h (A7); {N_DRAWS:,} paired Monte Carlo draws, seed {SEED}.",
             "Purchase cost: Sheet2 distributor unit prices (Mouser, DigiKey; links in data/prices.csv).",
             "Warranty cost: expected warranty failures x the part's unit price (parts-only, a LOWER bound;",
             "labour and module replacement are not included).", ""]
    for _, s in summary.iterrows():
        c, case = s["condition"], s["price_case"]
        lines += [f"## {c}, {case}",
                  f"- Before: {s['before_combination']}",
                  f"- After:  {s['after_combination']}",
                  f"- Purchase cost: before {q(c, BEFORE, 'purchase_cost')}; after {q(c, AFTER, 'purchase_cost')}",
                  f"- Expected warranty failures: before {q(c, BEFORE, 'failures', '{:,.3f}')}; "
                  f"after {q(c, AFTER, 'failures', '{:,.3f}')}; failures avoided {q(c, 'saving (before - after)', 'failures', '{:,.3f}')}",
                  f"- Warranty cost (parts-only): before {q(c, BEFORE, 'warranty_cost')}; after {q(c, AFTER, 'warranty_cost')}",
                  f"- Total cost: before {q(c, BEFORE, 'total_cost')}; after {q(c, AFTER, 'total_cost')}",
                  f"- Saving from the change: {q(c, 'saving (before - after)', 'total_cost')} per {FLEET:,} vehicles; "
                  f"P(after costs less) = {s['p_after_cheaper']:.3f}; P(after has fewer failures) = "
                  f"{s['p_after_fewer_failures']:.3f}"]
        b = be_rows[(be_rows["condition"] == c) & (be_rows["price_case"] == case)].iloc[0]
        if b["pays_off_at_any_repair_cost"]:
            lines.append(f"- Break-even repair cost: the recommended parts cost ${-b['premium']:,.0f} LESS to buy per "
                         f"{FLEET:,} vehicles, so the change pays off at any repair cost")
        else:
            lines.append(f"- Break-even repair cost: the recommended parts cost ${b['premium']:,.0f} MORE to buy per "
                         f"{FLEET:,} vehicles; the reliability gain pays this back only if one warranty repair costs "
                         f"more than {b['estimate']:,.0f} USD (median; 95% CI {b['lower']:,.0f}-{b['upper']:,.0f}; over "
                         f"the {b['share_draws_avoiding_failures']:.0%} of draws in which the change avoids failures)")
        lines.append("")
    lines += ["## Prices used (USD per unit, main case)"]
    for _, r in prices55.iterrows():
        lines.append(f"- {r['slot']}: {r['part']} {r['unit_price_usd']:.2f} ({r['price_source']})")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    lib = load_library()

    ba, summary, be_rows, prices = [], [], [], {}
    for case in (MAIN, EQUAL_MCU):
        for label, profile in CONDITIONS.items():
            sel, before_row, after_row, cmp, be = run_condition(label, profile, lib, case)
            ba += long_table(label, case, cmp)
            summary.append({"condition": label, "price_case": case, "before_combination": before_row["combination"],
                            "after_combination": after_row["combination"],
                            "p_after_cheaper": cmp["p_after_cheaper"],
                            "p_after_fewer_failures": cmp["p_after_fewer_failures"]})
            be_rows.append({"condition": label, "price_case": case, **be})
            prices[(label, case)] = price_table(sel, lib, case)
    ba, summary, be_rows = pd.DataFrame(ba), pd.DataFrame(summary), pd.DataFrame(be_rows)

    ba.to_csv(TABLES / "fin_1_before_after.csv", index=False)
    summary.to_csv(TABLES / "fin_2_scenarios.csv", index=False)
    be_rows.to_csv(TABLES / "fin_3_break_even_repair_cost.csv", index=False)
    pd.concat(prices, names=["condition", "price_case"]).reset_index(level=[0, 1]).to_csv(
        TABLES / "fin_4_candidates_cost.csv", index=False)
    main = ba[(ba["price_case"] == MAIN) & (ba["scenario"] != "saving (before - after)")]
    plots.fin_1_failures(main, FIGURES / "fin_1_warranty_failures.png", FLEET)
    plots.fin_2_saving(ba[ba["scenario"] == "saving (before - after)"], FIGURES / "fin_2_saving.png", FLEET)
    plots.fin_3_break_even(be_rows[be_rows["price_case"] == EQUAL_MCU], FIGURES / "fin_3_break_even_repair_cost.png")
    (OUT / "key_numbers_financial.md").write_text(key_numbers(summary, ba, be_rows, prices[("55 C", MAIN)]),
                                                  encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: 4 tables, 3 figures (plotnine), key_numbers_financial.md")
