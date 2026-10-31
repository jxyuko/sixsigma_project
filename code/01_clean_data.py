# 01_clean_data.py
# Build the component library data/components.csv from data/raw/parameter_table.xlsx, plus the
# published-FIT reference table data/reference/published_fit.csv (stored, NOT used by the model).
# ROADMAP Section 4 and Section 14, milestone M1. The raw file is never edited.
# Run from the project root:  .venv/Scripts/python code/01_clean_data.py

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from functions.arrhenius import accel_factor  # noqa: E402
from functions.evidence import device_hours, fit, lambda_bound  # noqa: E402
from functions.library import LIBRARY_PATH, REQUIRED, SLOTS  # noqa: E402

RAW = ROOT / "data" / "raw" / "parameter_table.xlsx"
# Team-maintained record of which published FITs were checked against the supplier reports
VERIFICATION = ROOT / "data" / "reference" / "fit_verification.csv"
PUBLISHED_PATH = ROOT / "data" / "reference" / "published_fit.csv"

CALC_NOTE = ("chi-square bound (E2-E5) at the published reference temperature and confidence level, "
             "from the table's n, t, f, T_test, Ea; assumes these are the supplier's full basis (A6)")

# Every name the raw table uses for a component (row labels and section headers) -> slot
SLOT_NAMES = {
    "ECU C2000 microcontroller": "ECU MCU",
    "ECU RH850 microcontroller": "ECU MCU",
    "ECUs microcontroller": "ECU MCU",
    "Battery BMS AFE": "BMS AFE",
    "Battery Management System": "BMS AFE",
    "Battery digital isolator": "Digital isolator",
    "Digital Isolator": "Digital isolator",
    "Battery temperature sensor": "Temperature sensor",
    "Temperature Sensor": "Temperature sensor",
    "Power gate driver": "Gate driver",
    "Gate Driver": "Gate driver",
    "Power current sensor": "Current sensor",
    "Current Sensor": "Current sensor",
}

SUPPLIER_NAMES = {"Rensas": "Renesas Electronics", "Renesas": "Renesas Electronics"}

# Part numbers corrected from the raw table: raw -> (library part, note)
PART_FIXES = {
    "ASUM4135": ("ADuM4135", "part number typo 'ASUM4135' in raw table, corrected to ADuM4135"),
    "ADUM141E": ("ADuM141E", None),  # capitalisation only
}

# Parts that share one qualification dataset (A9)
FAMILIES = {"F2800": "TI C2000", "R7F70": "Renesas RH850"}

# Library part -> (part number in the price sheet, note). Variants and family proxies are flagged.
PRICE_MATCH = {
    "BQ79656PAPRQ1": ("BQ79656PAPRQ1", None),
    "LTC6811-1": ("LTC6811HG-1#3ZZTRPBF", "price is for orderable variant LTC6811HG-1#3ZZTRPBF"),
    "ISL78714ANZ-T": ("ISL78714ANZ-T", None),
    "ISO7741QDWRQ1": ("ISO7741QDWRQ1", None),
    "ADuM141E": ("ADUM141E0BRQZ-RL7", "price is for orderable variant ADUM141E0BRQZ-RL7"),
    "TMP4719QDGSRQ1": ("TMP4719QDGSRQ1", None),
    "MAX31730": ("MAX31730ATC+T", "price is for orderable variant MAX31730ATC+T"),
    "UCC21750QDWRQ1": ("UCC21750QDWRQ1", None),
    "ADuM4135": ("ADUM4135WBRWZ", "price is for orderable variant ADUM4135WBRWZ"),
    "F2800157QPMQ1": ("F2800157QPMQ1", None),
}
FAMILY_PRICE = {
    "TI C2000": ("F2800157QPMQ1", "price is a family proxy (F2800157QPMQ1)"),
    "Renesas RH850": ("R7F7016843AFP-C#BA1", "price is a family proxy (R7F7016843AFP-C#BA1)"),
}

# Model inputs: what the simulator reads (data/components.csv)
COLUMNS = [
    "slot", "supplier", "part", "raw_part", "family",
    "test_temp_c", "test_hours", "sample_size", "failures", "ea_ev",
    "htol_sample_size", "unit_price_usd", "price_part", "source", "usable", "flag",
]

# Published-FIT reference (data/reference/published_fit.csv): kept in the repo, not used by the model
PUBLISHED_COLUMNS = [
    "slot", "supplier", "part", "family",
    "fit_published", "fit_published_status", "fit_published_source", "fit_published_note",
    "mtbf_published_h", "ref_temp_c", "ref_conf_level", "af_published",
    "fit_calculated", "fit_calc_ratio", "fit_calc_note",
]


# add_fit_columns(): keep the manufacturer's FIT as published, attach the team's verification record,
# and add our own FIT calculated from the test data at the same reference conditions.
def add_fit_columns(lib, verification):
    ver = verification.set_index("family_or_part")
    key = lib["part"].where(lib["part"].isin(ver.index), lib["family"])
    lib["fit_published_status"] = key.map(ver["fit_status"]).fillna("not checked")
    lib["fit_published_source"] = key.map(ver["fit_source"])
    lib["fit_published_note"] = key.map(ver["fit_basis_note"])

    calc = []
    for _, r in lib.iterrows():
        if not r["usable"] or pd.isna(r["ref_temp_c"]) or pd.isna(r["ref_conf_level"]):
            calc.append(np.nan)
            continue
        af = accel_factor(r["ref_temp_c"], r["test_temp_c"], r["ea_ev"])
        d = device_hours(r["sample_size"], r["test_hours"], af)
        calc.append(float(fit(lambda_bound(r["failures"], d, r["ref_conf_level"]))))
    lib["fit_calculated"] = calc
    lib["fit_calc_ratio"] = lib["fit_calculated"] / lib["fit_published"]
    lib["fit_calc_note"] = np.where(lib["fit_calculated"].notna(), CALC_NOTE,
                                    "not calculated: a required test parameter is missing")
    return lib


# read_parts(): walk the raw sheet top to bottom, tracking the current slot, and keep every
# row that has a part number. Section-header rows set the slot; duplicates keep the first row.
def read_parts(raw):
    rows, slot = [], None
    for _, r in raw.iterrows():
        name = r["SubComponent"]
        if isinstance(name, str) and name.strip() in SLOT_NAMES:
            slot = SLOT_NAMES[name.strip()]
        if isinstance(r["Reference"], str) and r["Reference"].strip():
            rows.append({"slot": slot, **r.to_dict()})
    parts = pd.DataFrame(rows)
    return parts.drop_duplicates(subset="Reference", keep="first").reset_index(drop=True)


def family_of(part):
    for prefix, family in FAMILIES.items():
        if part.startswith(prefix):
            return family
    return part


def build_library(raw, prices, verification):
    parts = read_parts(raw)
    price_of = prices.set_index("Product / part number")["Unit price (USD)"]

    out = []
    for _, r in parts.iterrows():
        flags = []
        raw_part = r["Reference"].strip()
        part, note = PART_FIXES.get(raw_part, (raw_part, None))
        if note:
            flags.append(note)
        family = family_of(part)
        if family != part:
            flags.append(f"shares qualification data with the {family} family (A9)")

        supplier = r["Manufacturer"].strip()
        supplier = SUPPLIER_NAMES.get(supplier, supplier)

        price_part, price_note = PRICE_MATCH.get(part, FAMILY_PRICE.get(family, (None, None)))
        price = float(price_of[price_part]) if price_part in price_of.index else np.nan
        if price_note:
            flags.append(price_note)
        if np.isnan(price):
            flags.append("no unit price in the price sheet")

        bib = r["Bibliography"]
        source = ("parameter_table.xlsx, bibliography #%d" % bib if pd.notna(bib)
                  else "parameter_table.xlsx, no bibliography entry") + " [TODO: report URL]"

        out.append({
            "slot": r["slot"],
            "supplier": supplier,
            "part": part,
            "raw_part": raw_part,
            "family": family,
            "test_temp_c": r["Test temp (C)"],
            "test_hours": r["Test duration (hours)"],
            "sample_size": r["Sample size"],
            "failures": r["Fails"],
            "ea_ev": r["Activation energy (eV)"],
            "fit_published": r["FIT"],
            "mtbf_published_h": pd.to_numeric(r["MTBF"], errors="coerce"),
            "ref_temp_c": r["Usage temp (C)"],
            "ref_conf_level": r["Conf level (%)"] / 100,
            "af_published": r["Thermal acceleration factor AF"],
            "htol_sample_size": r["HTOL sample size"],
            "unit_price_usd": price,
            "price_part": price_part,
            "source": source,
            "flags": flags,
        })

    lib = pd.DataFrame(out)

    # Completeness: a part missing any required test parameter can't be simulated
    missing = lib[list(REQUIRED)].isna()
    lib["usable"] = ~missing.any(axis=1)
    for i in lib.index:
        gaps = [c for c in REQUIRED if missing.loc[i, c]]
        if gaps:
            lib.at[i, "flags"].insert(0, f"MISSING {', '.join(gaps)} in raw table: excluded from simulation")
        if lib.at[i, "failures"] > 0:
            lib.at[i, "flags"].append(f"{int(lib.at[i, 'failures'])} failure(s) in HTOL")
    lib["flag"] = lib.pop("flags").apply("; ".join)
    lib = add_fit_columns(lib, verification)

    lib["slot"] = pd.Categorical(lib["slot"], categories=SLOTS, ordered=True)
    lib = lib.sort_values(["slot", "supplier", "part"]).reset_index(drop=True)
    # Returns (model library, published-FIT reference)
    return lib[COLUMNS], lib[PUBLISHED_COLUMNS]


if __name__ == "__main__":
    raw = pd.read_excel(RAW, sheet_name="parameter_table")
    prices = pd.read_excel(RAW, sheet_name="Sheet2", header=3).dropna(subset=["Product / part number"])
    verification = pd.read_csv(VERIFICATION)
    lib, published = build_library(raw, prices, verification)
    lib.to_csv(LIBRARY_PATH, index=False)
    published.to_csv(PUBLISHED_PATH, index=False)

    print(f"Wrote {LIBRARY_PATH.relative_to(ROOT)}: {len(lib)} parts, {lib['usable'].sum()} usable")
    print(lib.groupby("slot", observed=True)["part"].count().to_string())
    for _, r in lib[lib["flag"] != ""].iterrows():
        print(f"  {r['part']:20s} {r['flag']}")
    print(f"\nWrote {PUBLISHED_PATH.relative_to(ROOT)} (reference only, not used by the model):")
    fits = published.drop_duplicates("family")[["family", "fit_published", "fit_published_status",
                                                "fit_calculated", "fit_calc_ratio"]]
    print(fits.to_string(index=False, float_format=lambda v: f"{v:.4g}"))
