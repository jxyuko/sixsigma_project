# case_study.py
# Inputs of the rough-draft case study (ROADMAP Sections 9d and 10b, A17-A19), shared by 01_results.py and
# 02_financial_impacts.py. Every assumed value is labelled with its source or as a team assumption.
# Only calls functions/ (the simulator, select()).

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
from functions.candidates import library_candidate, select  # noqa: E402
from functions.library import SLOTS, load_library  # noqa: E402
from functions.reliability import DEFAULT_WARRANTY_HOURS  # noqa: E402

OUT = ROOT / "reports" / "rough_draft"

# Baseline setting (method item 6): 55 C, mission 2,920 h (A7), Ea 0.7 eV (A2), exponential life (A1),
# the failure-rate estimate (E4), target R >= 0.999 with 95% confidence (A13)
T_REF = 55
MISSION = DEFAULT_WARRANTY_HOURS
TARGET = 0.999
BAND = (40, 105)               # sensitivity: a band the parts run across (time spread evenly)
TI_DESIGN_LIFE_H = 15 * 8760 * 0.12   # TI SPRABX4C: AEC-Q100 profile, 15 years on with ~12% duty cycle

# One part per qualification family (A9); ISL78714 and MAX31730 are excluded (Section 14)
PARTS = ["F280049CPZQR", "R7F7016903AFP-C", "BQ79656PAPRQ1", "LTC6811-1", "ISO7741QDWRQ1", "ADuM141E",
         "TMP4719QDGSRQ1", "UCC21750QDWRQ1", "ADuM4135", "TMCS1101A4UQDRQ1"]

# A17 [ASSUMPTION, team decision 2026-11-17]: parts per vehicle for a 400 V pack (96 cells in series) and
# one three-phase traction inverter.
#   ECU MCU 1: one controller for the inverter (assumption)
#   BMS AFE: 96 cells / cells per chip: BQ79656 monitors 16 cells -> 6; LTC6811-1 monitors 12 -> 8
#   Digital isolator 2: MCU-to-gate-driver and BMS communication links (assumption)
#   Temperature sensor 2: inverter board and BMS board (assumption)
#   Gate driver 6: one per switch of a three-phase inverter (TI TIDA-010025; NXP RDGD31603PHSEVM)
#   Current sensor 3: one per motor phase (TI TIDA-00366)
QTY = {"F280049CPZQR": 1, "R7F7016903AFP-C": 1, "BQ79656PAPRQ1": 6, "LTC6811-1": 8, "ISO7741QDWRQ1": 2,
       "ADuM141E": 2, "TMP4719QDGSRQ1": 2, "UCC21750QDWRQ1": 6, "ADuM4135": 6, "TMCS1101A4UQDRQ1": 3}
QTY_SOURCE = {
    "ECU MCU": "one inverter controller (assumption)",
    "BMS AFE": "96 cells / cells per chip (16 for BQ79656, 12 for LTC6811-1)",
    "Digital isolator": "two isolated links (assumption)",
    "Temperature sensor": "inverter and BMS boards (assumption)",
    "Gate driver": "one per switch, three-phase inverter (TI TIDA-010025, NXP RDGD31603PHSEVM)",
    "Current sensor": "one per motor phase (TI TIDA-00366)"}

# A18 [ASSUMPTION]: recall model. One model year's fleet, and recall triggers (field failures of one part
# type at which the carmaker recalls); no regulation sets a number, so three values are shown.
FLEET = 100_000
TRIGGERS = (5, 10, 20)
K_BASE = 10
FLEETS = (10_000, 100_000, 500_000)
# A19 [ASSUMPTION]: cost per recalled vehicle (parts + labour at the dealer). Base: NADA average recall
# repair reimbursement, $440 (quoted by WardsAuto); low: Ford door-latch recall, $267 M / 1.3 M vehicles =
# $205; high: Atlas Copco whitepaper total recall cost per vehicle, about $850.
RECALL_COST = {"low": 205.0, "base": 440.0, "high": 850.0}


def candidates(lib=None, qty=True):
    """Library parts as candidates at their Sheet2 prices, entered as the user's prices (TMCS1101 has none
    and takes the current-sensor average, A14), with the A17 quantities."""
    lib = load_library() if lib is None else lib
    info = lib.set_index("part")
    out = []
    for part in PARTS:
        c = library_candidate(part, lib)
        price = info.loc[part, "unit_price_usd"]
        if pd.notna(price):
            c["unit_price_usd"] = float(price)
        if qty:
            c["qty_per_vehicle"] = QTY[part]
        out.append(c)
    return out


def run(condition=T_REF, mission=MISSION, target=TARGET, lib=None, qty=True, **kw):
    return select(candidates(lib, qty), condition, mission, target, **kw)


def parts_of(row):
    return [row[s] for s in SLOTS if s in row and isinstance(row[s], str)]


def least_reliable(sel):
    """The combination with the highest estimated system failure rate: the 'before' choice."""
    return sel.combinations.sort_values("system_fit_estimate").iloc[-1].to_dict()
