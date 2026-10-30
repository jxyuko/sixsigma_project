# TASER-EV Roadmap

**Read this first.** This is the single source of truth for *how* we build the TASER-EV simulator:
what it does, the model and approach, assumptions, equations, validation, code layout, build
order and data issues.

**Update rule:** every commit that changes the method, an assumption, a number, or the code
structure also updates this file and adds one line to the [Changelog](#15-changelog). If code and
roadmap disagree, fix one of them in the same commit.

Status tags: `[DECIDED]`, `[DEFAULT]` (our working choice, can still change), `[TODO]` (needs a
source or data), `[LATER]` (planned extension, not in the first build).

Contents:
1. [Research question](#1-research-question) |
2. [What the simulator does](#2-what-the-simulator-does) |
3. [Model / approach](#3-model--approach) |
4. [Component library](#4-component-library) |
5. [Inputs and outputs](#5-inputs-and-outputs) |
6. [Assumptions](#6-assumptions) |
7. [Equations](#7-equations) |
8. [Uncertainty](#8-uncertainty) |
9. [Results for the Preliminary Results report](#9-results-for-the-preliminary-results-report) |
10. [Financial model](#10-financial-model) |
11. [Validation](#11-validation-tests) |
12. [Code architecture](#12-code-architecture) |
13. [Build order](#13-build-order) |
14. [Data issues](#14-data-issues) |
15. [Changelog](#15-changelog)

---

## 1. Research question

> How can accelerated-life test results and thermal operating conditions for different automotive
> electronic components be translated to a common reliability basis, to estimate expected life
> under user-defined operating conditions and enable meaningful comparison?

**Unit of observation:** one EV electronic component from one supplier, under one defined
operating condition.

## 2. What the simulator does

TASER-EV is a simulator built on our **component library**: the supplier test parameters we
collected in `parameter_table.xlsx`. The user doesn't enter test data. They choose parts from the
library and give an **operating temperature**. The simulator turns each part's accelerated-life
test into reliability at that temperature.

The six component **slots** are ECU MCU, BMS AFE, digital isolator, temperature sensor, gate
driver and current sensor. A configuration fills **1 to 6** of the slots, with one library part
per slot.

### Mode 1: Evaluate (one configuration)

```
inputs:  operating temperature T_op  +  1–6 slots, each filled with one library part
              │
              ▼
per component:  AF, FIT, MTTF, R(t)
system:         series reliability R_sys(t), system FIT/MTTF, B0.1 life,
                B0.1-to-warranty ratio, estimated life
```

### Mode 2: Compare (two configurations)

```
inputs:  T_op  +  configuration A (1–6 slots)  +  configuration B (1–6 slots)
              │      the two can differ in which parts AND which slots are used
              ▼
Mode 1 outputs for A and for B, side by side
differences B − A for every component metric and every system metric (absolute and %)
```

**Input scope.** Operating temperature is the first and only required user input `[DECIDED]`.
Warranty period has a default, so the warranty ratio can be reported (A7). Other inputs are
`[LATER]` extensions: a temperature profile instead of one temperature, quantity per slot,
confidence level, and user-entered custom parts.

## 3. Model / approach

**The problem.** Suppliers report reliability from High Temperature Operating Life (HTOL) tests
run at different stress temperatures, sample sizes, test lengths and confidence levels. They then
quote a FIT at their own reference use temperature, usually 55 °C. An engineer whose part runs at
85 °C in an inverter can't use those numbers directly. Nor can they compare a TI part to an Analog
Devices part, because the two FITs weren't produced on the same basis. Our check of the collected
data confirms it: several published FIT values can't be reproduced from the supplier's own test
parameters (Section 14).

TASER-EV solves this by **not using the published FIT as the input**. For every part, we store
the raw test parameters:
- sample size n
- test duration t
- stress temperature T_test
- number of failures f
- activation energy Ea

We then recompute the failure rate at the temperature the user actually cares about. Every part
goes through the same equations at the same confidence level, so the outputs are comparable.

**Step 1 – Temperature acceleration (Arrhenius, E2).** HTOL tests speed up thermally activated
failure mechanisms. The Arrhenius model says the rate of such mechanisms scales with
exp(−Ea/kT). So one hour at T_test does the damage of AF hours at the user's operating
temperature T_op, where AF = exp[(Ea/k)(1/T_op − 1/T_test)]. The simulator computes a separate AF
for every selected part, because each was tested at its own temperature: 125 °C for most parts,
150 °C for the Renesas RH850. A higher T_op gives a smaller AF, so the same test buys fewer
equivalent field hours, and the part's estimated rate rises. That is how the user's temperature
input drives every output.

**Step 2 – Failure rate from a zero-failure test (chi-square bound, E3–E5).** Multiplying sample
size, test hours and AF gives equivalent device-hours at T_op. Failures are modelled as a Poisson
process. Most tests saw **zero failures**, and the point estimate f/D would then claim the part
never fails. So we use the standard **one-sided chi-square upper confidence bound**:
λ = χ²(CL; 2f+2) / (2D).

This is the method suppliers use themselves. We apply it at one confidence level for every part
(60% by default, the industry convention). From λ we report FIT (failures per 10⁹ hours) and
MTTF (1/λ). As a check, the simulator reproduces TI's published FIT when T_op = 55 °C (6.21 vs
6.19 for the C2000), which shows we're reading their data correctly.

**Step 3 – Component reliability over time (exponential, E7).** HTOL with zero failures can't
estimate the shape of a life distribution. FIT is by definition a constant rate. And
automotive-qualified parts are screened for infant mortality, while their wear-out lies beyond
the vehicle's life. So we model each part's useful life as exponential: R(t) = e^(−λt). This gives
the probability that the part survives to any time t, including the warranty period.

**Step 4 – System reliability (series block diagram, E8).** In the battery/inverter chain, each
selected component is a single point of failure: if the AFE, isolator, sensor, gate driver or
MCU fails, the function is lost. The configuration is therefore a **series system**. With
independent failures, the system reliability is the product of the component reliabilities. For
exponential parts this means the system failure rate is simply the sum of the selected parts'
rates. This works for any 1 to 6 slots the user fills.

**Step 5 – Life metrics the engineer can act on (E9–E10).** From the system rate we report:
- **System MTTF.**
- **B0.1 life:** the time by which 0.1% of systems have failed. This is the strict, early-failure
  metric warranty and quality teams care about, rather than the average life.
- **B0.1-to-warranty ratio:** B0.1 divided by the warranty period. Above 1 means fewer than 0.1%
  of systems are expected to fail under warranty. Below 1 means the configuration doesn't meet
  that target at the user's temperature.
- **Estimated life**, reported as both MTTF and B0.1, converted to years.

**Step 6 – Comparing two configurations (Mode 2, E11).** The user builds configurations A and B
from any parts and any subset of slots. The simulator runs Steps 1–5 on each at the same T_op, and
reports every component and system metric for both along with the difference B − A, in absolute
terms and as a percentage. This is what lets an engineer ask: "If I switch the gate driver from TI
to Analog Devices, or drop the separate isolator, how much warranty margin do I gain or lose?"

**Step 7 – Uncertainty (Monte Carlo, Section 8).** Every failure rate comes from a finite test, so
it is uncertain, and small tests are more uncertain than large ones. We draw each part's λ from
its chi-square sampling distribution (the same distribution behind Step 2's bound) and push every
draw through Steps 3–6. That gives **95% confidence intervals** on FIT, MTTF, B0.1, the warranty
ratio and the A-vs-B differences. A separate failure-time simulation draws a lifetime for each
component, takes the minimum to get system life, and checks that the simulated B0.1 matches the
closed-form one.

**How this answers the research question.** Steps 1–2 put accelerated-life data from different
suppliers onto a **common basis**: the same temperature, the same confidence level, the same
equations. Steps 3–5 turn that into the life, reliability and warranty metrics an engineer
decides with. Step 6 makes the comparison explicit, and Step 7 says how much to trust it.

## 4. Component library

`data/components.csv` holds one row per part, built from `data/raw/parameter_table.xlsx`.

| Slot | Library parts (supplier, part) | Notes |
|---|---|---|
| ECU MCU | TI C2000 (F280049 / F280039 / F280025 / F2800157); Renesas RH850 (R7F701xxxx) | The 4 TI parts share one dataset, as do the 5 Renesas parts (A9). RH850 data issue, see Section 14 |
| BMS AFE | TI BQ79656-Q1; ADI LTC6811-1; Renesas ISL78714 | LTC6811 and ISL78714 data issues |
| Digital isolator | TI ISO7741-Q1; ADI ADuM141E | ADuM141E had **f = 1** failure |
| Temperature sensor | TI TMP4719-Q1; ADI MAX31730 | MAX31730 has no sample size |
| Gate driver | TI UCC21750-Q1; ADI ADuM4135 | Typed "ASUM4135" in the raw table |
| Current sensor | TI TMCS1101-Q1 | Only one supplier so far |

Library columns:

| Column | Symbol | Unit | Meaning |
|---|---|---|---|
| slot | | | One of the six component slots |
| supplier, part | | | Manufacturer and part number |
| test_temp_c | T_test | °C | HTOL stress (junction) temperature |
| test_hours | t | h | Test duration per device |
| sample_size | n | devices | Units on test (may be pooled units; A6) |
| failures | f | count | Failures observed |
| ea_ev | Ea | eV | Activation energy the supplier assumed |
| fit_published | | FIT | Supplier's published FIT, used **only as a cross-check** |
| ref_temp_c | | °C | Use temperature the published FIT refers to |
| unit_price_usd | | USD | From the price sheet (used in the financial model) |
| source | | | Citation / URL of the reliability report |
| flag | | | Data-quality note (Section 14) |

**Out of scope:** mechanical parts, ICE vehicles, software failures, and failure mechanisms that
aren't thermally activated.

## 5. Inputs and outputs

### User inputs

| Input | Symbol | Default | Status |
|---|---|---|---|
| Operating temperature | T_op | 55 °C | `[DECIDED]`, required |
| Part chosen for each slot (1–6 slots) | | | `[DECIDED]`, required |
| Mode 2: a second configuration | | | `[DECIDED]` |
| Warranty period (operating hours) | t_w | See A7 | `[DEFAULT]`, fixed for now |
| Confidence level | CL | 0.60 | `[DEFAULT]`, fixed for now |
| Temperature profile instead of one T_op | {T_i, w_i} | | `[LATER]` (E6) |
| Quantity per slot | q_j | 1 | `[LATER]` |
| Custom user-entered part | | | `[LATER]` |

### Outputs

| Level | Output | Equation |
|---|---|---|
| Component | AF at T_op, λ, FIT, MTTF (hours and years), R(t_w) | E2–E5, E7 |
| System | λ_sys, system FIT, system MTTF, R_sys(t_w), R_sys(t) curve, B0.1 life, B0.1-to-warranty ratio | E8–E10 |
| Mode 2 | All of the above for A and for B, plus B − A (absolute and %) | E11 |
| Uncertainty | 95% CI on each of the above | Section 8 |

## 6. Assumptions

Each assumption has an ID so code comments and the report can cite it.

| ID | Assumption | Why it's reasonable / what it costs us | Status |
|---|---|---|---|
| A1 | **Constant failure rate (exponential life)** over the period of interest. | Zero-failure HTOL data can't identify a Weibull shape. FIT is by definition a constant rate, and constant hazard is the convention for the useful-life region. Infant mortality is removed by AEC-Q100 screening, and wear-out is assumed beyond vehicle life. | `[DECIDED]` |
| A2 | **Arrhenius temperature acceleration** with the supplier's Ea (0.7 eV for every part). | Matches how every supplier computed its FIT. Ea is uncertain, so we run a sensitivity analysis over 0.5–1.0 eV (Section 8). | `[DECIDED]` |
| A3 | **T_op is the component junction temperature** during operation, held constant. | The Arrhenius AF is defined at the junction. A single temperature is the simplest user input. A profile is the `[LATER]` extension (E6). | `[DECIDED]` |
| A4 | **Series system with independent failures.** | Every selected component is a single point of failure. Independence is standard without common-cause data. It's slightly optimistic if one thermal event hits several parts. | `[DECIDED]` |
| A5 | **The chi-square upper bound at a common CL (60%)** is the reported value. | Zero-failure tests have no useful point estimate. Using the same CL for every part keeps the comparison fair, and 60% is the supplier convention. The full uncertainty comes from Section 8. | `[DEFAULT]` |
| A6 | **Sample size × test hours = device-hours at T_test**, using the supplier's pooled sample size where one is given. | It's the only number published. TI's FIT reproduces exactly under this reading. | `[DEFAULT]` |
| A7 | **Warranty period in operating hours.** Default: 8 years / 100,000 miles, converted to powered-on hours. | Failure rates are per operating hour, but warranties are stated in years and miles. The conversion drives the ratio, so it's stated and checked for sensitivity. | `[DEFAULT]` `[TODO: sources for the conversion]` |
| A8 | **Only thermally activated failure mechanisms** are modelled. | HTOL only accelerates these. Cycling, vibration and humidity would add failures, so our life is an upper bound on field life. | `[DECIDED]` |
| A9 | **Parts in one qualification family share data**: the 4 TI C2000 parts, and the 5 RH850 parts. | That's how the suppliers report it. | `[DECIDED]` |
| A10 | **One part per slot** (quantity 1) for now. | It keeps comparisons clean. Quantities scale λ_sys linearly (E8), so adding them later is easy. | `[DEFAULT]` |

## 7. Equations

All equations are implemented once in `functions/` and cited by number in code comments.

**E1 · Kelvin.** T[K] = T[°C] + 273.15

**E2 · Arrhenius acceleration factor** from the part's test temperature T_s to the user's T_op:

  AF = exp[ (Ea / k) · (1/T_op − 1/T_s) ],  with k = 8.617333×10⁻⁵ eV/K

AF > 1 when T_op < T_s, and AF = 1 when T_op = T_s. Example: Ea = 0.7, T_op = 55 °C, T_s = 125 °C
gives AF = 77.65.

**E3 · Equivalent device-hours at T_op.**  D = n · t · AF

**E4 · Upper-bound failure rate at confidence level CL** (time-terminated test, f failures):

  λ = χ²(CL; 2f + 2) / (2 · D)   [failures per hour]

where χ²(CL; ν) is the CL-quantile of a chi-square distribution with ν degrees of freedom
(`scipy.stats.chi2.ppf`). With f = 0, λ = −ln(1 − CL) / D.

**E5 · FIT and MTTF.**  FIT = λ · 10⁹;  MTTF = 1/λ hours (÷ 8760 for years).

**E6 · Temperature profile** `[LATER]`. For {(T_i, w_i)} with Σw_i = 1, average the **rates**,
not the AFs or the temperatures:

  λ_profile = Σ w_i · λ(T_i)

This is equivalent to the Arrhenius average temperature of Tencer et al. (2004).

**E7 · Component life functions** (A1), with t in operating hours:

  R(t) = e^(−λt),  F(t) = 1 − R(t),  f(t) = λe^(−λt),  h(t) = λ

**E8 · Series system** over the selected slots S (1 ≤ |S| ≤ 6):

  R_sys(t) = Π_{j∈S} R_j(t) = exp(−λ_sys · t),  λ_sys = Σ_{j∈S} λ_j

Also: FIT_sys = λ_sys · 10⁹ and MTTF_sys = 1/λ_sys.

**E9 · B0.1 life** (time by which 0.1% of systems have failed):

  B0.1 = −ln(1 − 0.001) / λ_sys = 0.0010005 / λ_sys

**E10 · Warranty ratio.**  WR = B0.1 / t_w.  WR ≥ 1 means fewer than 0.1% of systems fail within
warranty.

**E11 · Comparison (Mode 2).** For every metric M (component or system):

  ΔM = M_B − M_A,  ΔM% = 100 · (M_B − M_A) / M_A

For system life this reduces to ΔB0.1% = 100 · (λ_sys,A / λ_sys,B − 1).

**E12 · Expected warranty failures and cost** for a fleet of N vehicles:

  E[failures] = N · F_sys(t_w);  Cost = E[failures] · C_fail

## 8. Uncertainty

The course pattern (`ZZ_financial_analysis.py`) bootstraps raw observations. **We have no raw
failure times**, because most tests had 0 failures. So we use a **parametric simulation** of λ
that's consistent with E4, then propagate it to every output.

**8a. Failure-rate draws.** For each part, draw

  λ* = X / (2 · D),  X ~ χ²(2f + 2)

The CL-quantile of this distribution is exactly E4 (the standard result for a Poisson count with
exposure D). Draw 10,000 replicates per part, independently across parts (A4).

**8b. Propagation.** For each replicate, compute every Mode 1 and Mode 2 output. Report the median
and the 95% CI (2.5–97.5 percentiles).

**8c. Sensitivity.** Sweep T_op from 25 to 125 °C; vary Ea from 0.5 to 1.0 eV, CL between 0.60
and 0.90, and t_w at low / base / high.

**8d. Failure-time Monte Carlo check.** Simulate 100,000 systems with T_j ~ Exp(λ_j) and
T_sys = min_j T_j. The empirical 0.1% quantile must match E9 within Monte Carlo error.

## 9. Results for the Preliminary Results report

These all come from running the simulator, not from separate one-off scripts.

1. **Library check:** every part's recomputed FIT at 55 °C against its published FIT, with
   mismatches flagged.
2. **Mode 1 at a reference temperature:** a full six-slot configuration, giving the component
   table and system R_sys(t), B0.1 and WR, with 95% CIs.
3. **Temperature sweep:** system B0.1 and WR from 25 to 125 °C, showing where WR drops below 1.
4. **Mode 2 examples:** the all-TI configuration against configurations that swap suppliers in
   one or more slots, giving differences with CIs.
5. **Sensitivity** (8c).

## 10. Financial model

All unit costs need citations `[TODO]`.

**10a. Warranty exposure, before vs after** (a natural Mode 2 output):
- Before = configuration A, after = configuration B.
- Cost = N · F_sys(t_w) · C_fail (E12), with the 95% CI from the Section 8 draws.
- Benefit = cost(A) − cost(B), minus any change in parts cost per vehicle × N.

**10b. Engineering evaluation time** (the charter goal is a 20% reduction):
- Hours per component evaluation × evaluations per year × $74.66/h (Federal Register, 2025).
- After = before × 0.8.
- The CI comes from simulating a range for hours per evaluation.

Inputs to source:
- C_fail: cost per warranty repair, including part and labour, e.g. ECU / BMS module replacement.
- N: annual EV production volume.
- Hours per evaluation.

## 11. Validation tests

| Test | Expected |
|---|---|
| E2: AF(55 °C, test at 125 °C, 0.7 eV) | 77.65 ± 0.01 (matches the table's 77.6454) |
| E2 degenerate: T_op = T_test | AF = 1 |
| E4 known answer: TI C2000, n = 1900, t = 1000, 125 °C, T_op = 55 °C, CL = 0.6, f = 0 | 6.21 FIT (TI publishes 6.19) |
| E4 closed form: f = 0 | equals −ln(1 − CL)/D |
| E4 monotone | higher T_op, more failures or higher CL each give a higher λ |
| E8 | one slot → λ_sys = λ of that part; system FIT = sum of component FITs |
| E9 | R_sys(B0.1) = 0.999 |
| E11 | comparing a configuration with itself gives every Δ = 0 |
| 8a | 60th percentile of λ* ≈ E4 (within 1%) |
| 8d | empirical 0.1% quantile ≈ E9 (within 2%) |

## 12. Code architecture

```
functions/
  arrhenius.py      kelvin(), accel_factor()                                   E1, E2 (E6 later)
  failure_rate.py   lambda_upper(), fit(), mttf()                              E3–E5
  reliability.py    r(), f(), h(), series_lambda(), b_life(), warranty_ratio() E7–E10
  library.py        load_library(), get_part()                                 component library
  simulator.py      evaluate(config, t_op)          → component table + system summary   (Mode 1)
                    compare(config_a, config_b, t_op) → A, B and differences          (Mode 2)
  uncertainty.py    draw_lambda(), evaluate_ci(), compare_ci(), simulate_failure_times()  Section 8
  finance.py        warranty_cost(), eval_time_cost()                          Section 10
code/
  01_clean_data.py   raw xlsx → data/components.csv + data/codebook.md
  02_results.py      runs the simulator for every result in Section 9 → results/tables, results/figures
  03_financial.py    Section 10 → before/after cost table with CIs
  04_make_report.py  writes reports/*.docx from the results tables
tests/
  test_arrhenius.py, test_failure_rate.py, test_reliability.py, test_simulator.py, test_uncertainty.py
```

A configuration is a plain mapping from slot to part, e.g.
`{"ECU MCU": "F280049", "Gate driver": "UCC21750-Q1"}`.
`evaluate()` and `compare()` return DataFrames and do no plotting. The later UI calls exactly
these two functions.

## 13. Build order

Each milestone ends with its tests passing and this file updated.

| # | Milestone | Done when |
|---|---|---|
| M0 | Roadmap agreed (this file) | The team has reviewed the simulator design and model |
| M1 | Component library | `data/components.csv` and codebook; every part flagged where needed |
| M2 | Equation functions (E1–E10) | Section 11 tests for E2–E10 pass |
| M3 | Simulator Mode 1 `evaluate()` | Component + system outputs for any 1–6 slot configuration |
| M4 | Simulator Mode 2 `compare()` | A, B and differences; self-comparison gives zero |
| M5 | Uncertainty | CIs on all outputs; 8a and 8d checks pass |
| M6 | Results + financial | Section 9 and 10 tables and figures in `results/` |
| M7 | Reports | Preliminary Results and Financial Impacts .docx in `reports/` |
| M8 | User interface `[LATER]` | Front end over `evaluate()` / `compare()` |

## 14. Data issues

**Rule:** when a part's published FIT doesn't match its own test data, the simulator uses the
**recomputed** value, keeping the common basis. The published value is shown beside it and the
part is flagged. The raw table's "Mission time = 120,000 hours" column isn't used.

| Part | Published FIT | Recomputed (60%, 55 °C) | Action |
|---|---|---|---|
| TI parts | match | match (C2000 6.21 vs 6.19) | ✓ |
| Renesas RH850 | 0.0011 | ≈ 15.3 | Recheck the report (published MTBF 9.09×10¹¹ h) |
| ADI LTC6811-1 | 33.95 (but its MTBF implies 0.16) | ≈ 0.32 | Recheck the report |
| ADI ADuM4135 | 11.28 | ≈ 0.37 | Recheck; fix the "ASUM4135" typo |
| Renesas ISL78714 | 3.72 | ≈ 3.06 | Check whether CL or Ea differs |
| ADI MAX31730 | 28.1 | n missing | Find the sample size; its reference temperature is 25 °C |
| ADI ADuM141E | 20.23 | ≈ 0.45 (f = 1, ν = 4) | Recheck the report |

## 15. Changelog

| Date | Change |
|---|---|
| 2026-10-29 | First draft: method, equations, assumptions, uncertainty plan, build order. |
| 2026-10-29 | Added the Model / approach narrative; replaced open decisions with defaults. |
| 2026-10-29 | Restructured around the simulator. Mode 1 Evaluate: T_op + 1–6 slots → component and system FIT, MTTF, R, B0.1, WR. Mode 2 Compare: two configurations → both sets of outputs plus differences. The temperature profile, quantities and custom parts move to `[LATER]`. Removed the 48-configuration factorial as a core result. Expanded the Model / approach. |
