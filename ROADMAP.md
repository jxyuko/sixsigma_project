# TASER-EV Roadmap

**Read this first.** This is the single source of truth for *how* we build the TASER-EV simulator:
what it does, the model and approach, assumptions, equations, how we evaluate it, code layout,
build order and data issues.

**Update rule:** every commit that changes the method, an assumption, a number, or the code
structure also updates this file and adds one line to the [Changelog](#15-changelog). If code and
roadmap disagree, fix one of them in the same commit. Earlier versions are kept in
`docs/roadmap_history/`.

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
8. [Simulation engine](#8-simulation-engine) |
9. [Results for the Preliminary Results report](#9-results-for-the-preliminary-results-report) |
10. [Financial model](#10-financial-model) |
11. [Evaluating the simulator](#11-evaluating-the-simulator) |
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

TASER-EV is a Monte Carlo simulator built on our **component library**: the supplier test
parameters we collected in `parameter_table.xlsx`. The user doesn't enter test data. They choose
parts from the library and give the **operating temperature**. The simulator turns each part's
accelerated-life test into reliability at that temperature, *with its uncertainty*.

The six component **slots** are ECU MCU, BMS AFE, digital isolator, temperature sensor, gate
driver and current sensor. A configuration fills **1 to 6** of the slots, with one library part
per slot.

### Mode 1: Evaluate (one configuration)

```
inputs:  operating temperature T_op (or a temperature profile)  +  1–6 slots, one library part each
              │
              ▼
per component:  AF, equivalent device-hours, FIT, MTTF, R(t)            each as median + 95% CI
system:         R_sys(t) band, system FIT/MTTF, B0.1 life, B0.1-to-warranty ratio,
                estimated life in years, and P(meets warranty) = P(WR ≥ 1)
```

### Mode 2: Compare (two configurations)

```
inputs:  T_op  +  configuration A (1–6 slots)  +  configuration B (1–6 slots)
              │      the two can differ in which parts AND which slots are used
              ▼
Mode 1 outputs for A and for B, side by side
differences B − A for every metric (absolute and %), with 95% CI
P(B outlasts A) = P(B0.1,B > B0.1,A)   ← "is B really better, given how much each was tested?"
```

**Input scope.**
- **Required:** operating temperature `[DECIDED]`. One temperature is a profile with a single bin,
  and an optional multi-bin profile (the dynamic AF) uses the same code path.
- **Has a default:** warranty period (A7), so the warranty ratio can be reported.
- **`[LATER]`:** quantity per slot, user-chosen confidence level, and user-entered custom parts.

## 3. Model / approach

**The problem.** Suppliers report reliability from High Temperature Operating Life (HTOL) tests
run at different stress temperatures, sample sizes, test lengths and confidence levels. They then
quote a FIT at their own reference use temperature, usually 55 °C. An engineer whose part runs at
85 °C in an inverter can't use those numbers directly. Nor can they compare a TI part to an Analog
Devices part, because the two FITs weren't produced on the same basis. Our check of the collected
data confirms it: several published FIT values can't be reproduced from the supplier's own test
parameters (Section 14).

TASER-EV therefore **doesn't use the published FIT as its input**. For every part it stores the
raw test parameters (sample size n, test duration t, stress temperature T_test, failures f,
activation energy Ea) and rebuilds the reliability from them through five layers. Every part goes
through the same layers, so the outputs are on a common basis.

**Layer 1 – Evidence: each test is an amount of evidence, not a quality score (E3–E4).**
- A test of n units for t hours with f failures is, under a constant failure rate, *exactly*
  "n·t device-hours with f failures". Nothing else in the test matters for the rate.
- Most tests saw **zero failures**, so the point estimate f/D would claim the part never fails.
- Instead, the simulator holds each part's failure rate as a **probability distribution**:
  λ ~ Gamma(shape f + 1, rate D), where D is the equivalent device-hours.
- The 60th percentile of this distribution is exactly the chi-square upper bound
  χ²(0.6; 2f+2)/(2D) that suppliers publish. So we lose nothing from the supplier convention, and
  we gain the full uncertainty.
- This also makes the most important property of the data visible. Zero failures in 7,000 units
  and zero in 100,000 units are not "bad part" vs "good part"; they are **weak vs strong
  evidence**. The distribution is wide for the first and narrow for the second.

**Layer 2 – Physics: from test temperature to the user's temperature (E1–E2, E6).**
- HTOL tests speed up thermally activated failure mechanisms. The Arrhenius model says their rate
  scales with exp(−Ea/kT), so one hour at T_test does the damage of AF hours at the use
  temperature.
- The simulator computes AF separately for every part, because each was tested at its own
  temperature: 125 °C for most, 150 °C for the Renesas RH850.
- **Dynamic AF.** Vehicles don't run at one temperature. Following the Research Design (Tencer et
  al., 2004), the user can give a profile: temperatures and the fraction of time at each.
  - The simulator averages the **failure rates** over the profile, not the temperatures or the AFs.
  - This matters: for a 50/30/20% profile at 40/70/105 °C, the mean temperature (62 °C) gives
    AF = 46.3, but the correct rate-averaged AF is 12.3. Averaging temperatures would overstate
    life almost four-fold, because hot periods do most of the damage.
- **Ea is uncertain.** Every supplier assumes 0.7 eV, but real mechanisms range roughly from 0.5
  to 0.9 eV. Each simulation run draws Ea from that range. The further T_op is from T_test, the
  more Ea uncertainty widens the intervals, which is physically right: a longer extrapolation
  deserves less confidence.

**Layer 3 – Mission: what time period matters (A7).** Warranties are stated in years and miles,
but failure rates are per operating hour. The simulator converts the warranty to powered-on hours
under stated assumptions. This sets t_w for the warranty ratio and warranty cost.

**Layer 4 – System: series block diagram, by nested Monte Carlo (E7–E10, Section 8).**
- Each selected component is a single point of failure in the battery/inverter chain: if the
  AFE, isolator, sensor, gate driver or MCU fails, the function is lost. So the configuration is
  a **series system**. With independent failures and constant rates (exponential life, A1), the
  system rate is the sum of the selected parts' rates, and R_sys(t) = e^(−λ_sys·t). This works
  for any 1 to 6 filled slots.
- The engine repeats this about 5,000 times:
  1. Draw an Ea.
  2. Draw every selected part's failure rate from Layer 1.
  3. Apply the AFs from Layer 2.
  4. Sum into the system rate.
  5. Compute R_sys(t), system FIT/MTTF, the B0.1 life (the time by which 0.1% of systems fail)
     and the warranty ratio WR = B0.1 / t_w.
- Each output is reported as a **median with a 95% interval**. The simulator also reports the
  decision metric **P(WR ≥ 1)**: the probability that fewer than 0.1% of systems fail within
  warranty at the user's conditions.
- A separate failure-time simulation draws a lifetime for every component of 100,000 simulated
  vehicles and takes the minimum. Its 0.1% quantile must match the closed-form B0.1.

**Layer 5 – Comparison (Mode 2, E11–E13).**
- Configurations A and B are evaluated on the **same random draws**: the same Ea, and the same λ
  for any part they share. Their difference reflects only what's actually different between
  them.
- The simulator reports every metric for both, the difference B − A with a 95% interval, and
  **P(B outlasts A)**.
- This is the honest answer to "is B better?":
  - For two zero-failure parts at the same test temperature it reduces to
    P = D_A / (D_A + D_B).
  - TI's BQ79656 (~101,758 units tested) against Renesas's ISL78714 (3,856 units) gives
    P = 0.96: strong evidence that the TI part is more reliable.
  - Two parts with similar test sizes give P ≈ 0.5: the data can't tell them apart, and the
    simulator says so instead of crowning a false winner.

**Evaluation: comparing the simulator to real results (Section 11).** A simulator is only useful
if its numbers resemble reality. Beyond unit tests, we compare it against four kinds of outside
evidence:
1. **Supplier results:** each supplier's own published FIT at their stated conditions. *On hold:*
   published FITs are stored in `data/reference/` but not used (Section 14).
2. **Industry prediction handbooks:** Siemens SN 29500, IEC 61709 and MIL-HDBK-217F, for the same
   part types and temperatures.
3. **Field evidence:** published field failure rates for automotive ICs, and real warranty
   extensions and recalls for these component types (e.g. BMW's HV-battery temperature sensor
   extension, cited in our charter).
4. **A known-truth coverage study:** synthetic suppliers with a true failure rate we set
   ourselves, used to check that the simulator's 95% intervals contain the truth about 95% of the
   time.

For each comparison we state the **expected direction of disagreement in advance**. For example,
the simulator models only thermally activated mechanisms (A8), so it should predict *fewer*
failures than field data. A gap in that direction supports the model; a gap the other way points
to a bug or a data error.

**How this answers the research question.**
- Layers 1–2 put accelerated-life data from different suppliers onto a **common basis**: the same
  temperature or profile, the same statistical treatment, the same equations.
- Layers 3–4 turn that into the life, reliability and warranty metrics an engineer decides with.
- Layer 5 makes comparisons **meaningful** by saying how confident we can be that one choice beats
  another.
- The evaluation shows how far the numbers can be trusted against the real world.

## 4. Component library

`data/components.csv` holds one row per part, built from `data/raw/parameter_table.xlsx` by
`code/01_clean_data.py`. **`data/codebook.md` is the authoritative column list.** It has 19 parts:
17 usable, and 2 excluded because a required test parameter is blank in the raw table.

| Slot | Library parts (supplier, part) | Notes |
|---|---|---|
| ECU MCU | TI C2000 (F280049 / F280039 / F280025 / F2800157); Renesas RH850 (R7F701xxxx) | The 4 TI parts share one dataset, as do the 5 Renesas parts (A9). RH850 data issue, see Section 14 |
| BMS AFE | TI BQ79656-Q1; ADI LTC6811-1; Renesas ISL78714 | LTC6811 data issue. **ISL78714 not usable: failures blank** |
| Digital isolator | TI ISO7741-Q1; ADI ADuM141E | ADuM141E had **f = 1** failure |
| Temperature sensor | TI TMP4719-Q1; ADI MAX31730 | **MAX31730 not usable: sample size blank** |
| Gate driver | TI UCC21750-Q1; ADI ADuM4135 | Typed "ASUM4135" in the raw table |
| Current sensor | TI TMCS1101-Q1 | Only one supplier so far |

Key library columns (full list in `data/codebook.md`):

| Column | Symbol | Unit | Meaning |
|---|---|---|---|
| slot | | | One of the six component slots |
| supplier, part, raw_part, family | | | Manufacturer, part number, the raw-table spelling, and the shared qualification family (A9) |
| test_temp_c | T_test | °C | HTOL stress (junction) temperature |
| test_hours | t | h | Test duration per device |
| sample_size | n | devices | Units on test (may be pooled units; A6) |
| failures | f | count | Failures observed |
| ea_ev | Ea | eV | Activation energy the supplier assumed |
| unit_price_usd, price_part | | USD | Price-sheet price and which part number it came from |
| source | | | Bibliography number; report URL `[TODO]` |
| usable | | bool | All of T_test, t, n, f, Ea present |
| flag | | | Data-quality notes (Section 14) |

**The model reads only test data.** Manufacturer-published FITs, MTBFs and their reference
conditions, the team's verification of them, and our FIT calculated at the same conditions are
stored separately in `data/reference/published_fit.csv` and `data/reference/fit_verification.csv`.
They're kept in the repo but **not used by the model** (team decision 2026-10-30; may be revisited).
Other reference data for validation also lives in `data/reference/` (Section 11).

**Out of scope:** mechanical parts, ICE vehicles, software failures, and failure mechanisms that
aren't thermally activated.

## 5. Inputs and outputs

### User inputs

| Input | Symbol | Default | Status |
|---|---|---|---|
| Operating temperature, or a profile {(T_i, w_i)} | T_op | 55 °C, single bin | `[DECIDED]`, required |
| Part chosen for each slot (1–6 slots) | | | `[DECIDED]`, required |
| Mode 2: a second configuration | | | `[DECIDED]` |
| Warranty period (operating hours) | t_w | See A7 | `[DEFAULT]`, fixed for now |
| Quantity per slot | q_j | 1 | `[LATER]` |
| Custom user-entered part | | | `[LATER]` |

### Outputs (each as median and 95% CI unless noted)

| Level | Output | Equation |
|---|---|---|
| Component | AF at T_op (or effective AF over the profile), equivalent device-hours D, FIT, MTTF (hours and years), R(t_w) | E2–E7 |
| Component, supplier-comparable | FIT at the 60% bound (a single number, same convention as datasheets) | E4 |
| System | λ_sys, system FIT, system MTTF, R_sys(t_w), R_sys(t) band, B0.1 life, warranty ratio WR | E8–E10 |
| System decision | P(WR ≥ 1): probability of meeting the warranty target | E14 |
| Mode 2 | All of the above for A and B; B − A (absolute and %); P(B outlasts A) | E11–E13 |

## 6. Assumptions

Each assumption has an ID so code comments and the report can cite it.

| ID | Assumption | Why it's reasonable / what it costs us | Status |
|---|---|---|---|
| A1 | **Constant failure rate (exponential life)** over the period of interest. | Zero-failure HTOL data can't identify a Weibull shape. FIT is by definition a constant rate, and constant hazard is the convention for the useful-life region. Infant mortality is removed by AEC-Q100 screening, and wear-out is assumed beyond vehicle life. | `[DECIDED]` |
| A2 | **Arrhenius acceleration, with uncertain Ea.** Each run draws Ea from a triangular distribution (min 0.5, mode 0.7, max 0.9 eV), shared by all parts in that run. | 0.7 eV is every supplier's assumption, so it's the mode. The 0.5–0.9 range spans common thermally activated mechanisms. Sharing one draw per run treats them as the same silicon technology. Independent Ea per part is run as a sensitivity. | `[DEFAULT]` `[TODO: cite JEDEC JEP122 for the range]` |
| A3 | **T_op is the component junction temperature.** A profile is a set of junction temperatures with time fractions; one temperature is a one-bin profile. | The Arrhenius AF is defined at the junction. Rates are averaged over the profile (E6), following Tencer et al. (2004). | `[DECIDED]` |
| A4 | **Series system with independent failures.** | Every selected component is a single point of failure. Independence is standard without common-cause data. It's slightly optimistic if one thermal event hits several parts. | `[DECIDED]` |
| A5 | **Failure-rate uncertainty: λ ~ Gamma(f + 1, D).** This is the posterior under a uniform prior, and its 60th percentile equals the supplier chi-square bound. | It reproduces the industry convention exactly and adds a full distribution, which is what makes CIs and P(B outlasts A) possible. A Jeffreys prior, Gamma(f + ½, D), is run as a sensitivity. | `[DEFAULT]` |
| A6 | **Sample size × test hours = device-hours at T_test**, using the supplier's pooled sample size where one is given. | It's the only number published. TI's FIT reproduces exactly under this reading. | `[DEFAULT]` |
| A7 | **Warranty period in operating hours.** Default: 8 years / 100,000 miles, converted to powered-on hours. | Failure rates are per operating hour, but warranties are stated in years and miles. The conversion drives WR, so it's stated and checked for sensitivity. | `[DEFAULT]` `[TODO: sources for the conversion]` |
| A8 | **Only thermally activated failure mechanisms** are modelled. | HTOL only accelerates these. Cycling, vibration and humidity would add failures, so our life is an upper bound on field life, and we expect to under-predict field failure rates (11d). | `[DECIDED]` |
| A9 | **Parts in one qualification family share data**: the 4 TI C2000 parts, and the 5 RH850 parts. | That's how the suppliers report it. | `[DECIDED]` |
| A10 | **One part per slot** (quantity 1) for now. | It keeps comparisons clean. Quantities scale λ_sys linearly (E8), so adding them later is easy. | `[DEFAULT]` |

## 7. Equations

All equations are implemented once in `functions/` and cited by number in code comments.

**E1 · Kelvin.** T[K] = T[°C] + 273.15

**E2 · Arrhenius acceleration factor** from the part's test temperature T_s to a use temperature T:

  AF(T) = exp[ (Ea / k) · (1/T − 1/T_s) ],  with k = 8.617333×10⁻⁵ eV/K

AF > 1 when T < T_s, and AF = 1 when T = T_s. Example: Ea = 0.7, T = 55 °C, T_s = 125 °C gives
AF = 77.65.

**E3 · Equivalent device-hours at the use condition.**  D = n · t · AF_eff
(AF_eff from E6; for one temperature, AF_eff = AF(T_op))

**E4 · Failure-rate distribution and the supplier-comparable bound.**

  λ ~ Gamma(shape = f + 1, rate = D)

Its CL-quantile is the chi-square upper bound

  λ_CL = χ²(CL; 2f + 2) / (2 · D)

which with f = 0 simplifies to −ln(1 − CL)/D. We report λ_0.60 as the "datasheet-style" value.

**E5 · FIT and MTTF.**  FIT = λ · 10⁹;  MTTF = 1/λ hours (÷ 8760 for years).

**E6 · Dynamic AF over a temperature profile** {(T_i, w_i)}, Σw_i = 1. Average the **rates**:

  λ_profile = Σ w_i · λ(T_i)   ⇔   1/AF_eff = Σ w_i / AF(T_i)

This is equivalent to the Arrhenius average temperature T_aa of Tencer et al. (2004), defined by
exp(−Ea/kT_aa) = Σ w_i · exp(−Ea/kT_i). Never average the temperatures or the AFs.

**E7 · Component life functions** (A1), with t in operating hours:

  R(t) = e^(−λt),  F(t) = 1 − R(t),  f(t) = λe^(−λt),  h(t) = λ

**E8 · Series system** over the selected slots S (1 ≤ |S| ≤ 6):

  R_sys(t) = Π_{j∈S} R_j(t) = exp(−λ_sys · t),  λ_sys = Σ_{j∈S} λ_j

Also: FIT_sys = λ_sys · 10⁹ and MTTF_sys = 1/λ_sys.

**E9 · B0.1 life.**  B0.1 = −ln(1 − 0.001) / λ_sys = 0.0010005 / λ_sys

**E10 · Warranty ratio.**  WR = B0.1 / t_w

**E11 · Differences (Mode 2).** For every metric M: ΔM = M_B − M_A and ΔM% = 100·(M_B − M_A)/M_A,
computed draw by draw, then summarized as a median and 95% CI.

**E12 · Expected warranty failures and cost** for a fleet of N vehicles:

  E[failures] = N · F_sys(t_w);  Cost = E[failures] · C_fail

**E13 · Probability B outlasts A.**  P(B0.1,B > B0.1,A) = P(λ_sys,B < λ_sys,A), estimated as the
share of paired draws where it's true. Closed-form check: for two single zero-failure parts 1
and 2 at the same T_test (so they share an AF), the probability that part 1 has the lower failure
rate is P(λ_1 < λ_2) = D_1 / (D_1 + D_2).

**E14 · Probability of meeting warranty.**  P(WR ≥ 1) = share of draws with B0.1 ≥ t_w.

## 8. Simulation engine

The course pattern (`ZZ_financial_analysis.py`) bootstraps raw observations. **We have no raw
failure times**, because most tests had 0 failures. So the engine is a **parametric Monte Carlo**
built on the evidence distributions (E4), following the same `qi()` idea: repeat, collect, take
quantiles.

**8a. Outer loop (parameter uncertainty), R = 5,000 draws:**
1. Draw Ea (A2).
2. Draw each library part's λ at T_test from Gamma(f + 1, n·t).
3. Convert each to the use condition: λ_use = λ_test / AF_eff (E6).

A and B share the same draws (common random numbers).

**8b. Per-draw outputs:** compute E5–E14 for each draw. Report the median, the 95% CI
(2.5–97.5 percentiles) and the probabilities E13–E14.

**8c. Inner check (aleatory variation):** for one set of λs, simulate 100,000 systems with
T_j ~ Exp(λ_j) and T_sys = min_j T_j. The empirical 0.1% quantile must match E9 within Monte Carlo
error.

**8d. Sensitivity:**
- T_op from 25 to 125 °C.
- Ea range, and shared vs independent Ea draws (A2).
- Uniform vs Jeffreys prior (A5).
- t_w at low / base / high.

Shown as tornado charts and line plots.

**Reproducibility:** fixed random seed, recorded in every results file.

## 9. Results for the Preliminary Results report

All of these come from running the simulator.

1. **Library table:** every usable part's test evidence (device-hours, failures) and its FIT at a
   reference temperature, all from test data.
2. **Mode 1 at a reference temperature:** a full six-slot configuration, giving the component
   table and system R_sys(t) band, B0.1, WR and P(WR ≥ 1), all with 95% CIs.
3. **Temperature sweep:** system B0.1 and P(WR ≥ 1) from 25 to 125 °C, showing where the
   configuration stops meeting warranty. Also the profile vs mean-temperature comparison (E6).
4. **Mode 2 examples:** the all-TI configuration against configurations that swap suppliers in
   one or more slots, giving differences with CIs and P(B outlasts A).
5. **Sensitivity** (8d).
6. **Comparison to real results** (11c–11e): simulator FIT against handbook and field values on a
   log-scale chart, plus the coverage-study result.

## 10. Financial model

All unit costs need citations `[TODO]`.

**10a. Warranty exposure, before vs after** (a natural Mode 2 output):
- Before = configuration A, after = configuration B.
- Cost = N · F_sys(t_w) · C_fail (E12), computed per draw, so the 95% CI comes straight from the
  simulation.
- Benefit = cost(A) − cost(B), minus any change in parts cost per vehicle × N.
- P(benefit > 0) is reported alongside.

**10b. Engineering evaluation time** (the charter goal is a 20% reduction):
- Hours per component evaluation × evaluations per year × $74.66/h (Federal Register, 2025).
- After = before × 0.8.
- The CI comes from simulating a range for hours per evaluation.

Inputs to source:
- C_fail: cost per warranty repair, including part and labour, e.g. ECU / BMS module replacement.
- N: annual EV production volume.
- Hours per evaluation.

## 11. Evaluating the simulator

There are two questions here:
- **Verification:** did we code the equations correctly? (11a)
- **Validation:** do the results match reality? (11b–11e)

For each real-world comparison we state the **expected direction** of any disagreement before
looking at the result.

### 11a. Verification tests (`tests/`)

| Test | Expected |
|---|---|
| E2: AF(55 °C, test at 125 °C, 0.7 eV) | 77.65 ± 0.01 (matches the table's 77.6454) |
| E2 degenerate: T = T_test | AF = 1 |
| E4 known answer: TI C2000, n = 1900, t = 1000, 125 °C → 55 °C, CL = 0.6, f = 0 | 6.21 FIT (TI publishes 6.19) |
| E4 closed form: f = 0 | λ_CL = −ln(1 − CL)/D |
| E4 distribution: 60th percentile of 100,000 Gamma(f+1, D) draws | within 1% of λ_0.60 |
| E4 monotone | higher T_op, more failures or higher CL each give a higher λ |
| E6 degenerate: one-bin profile | equals the single-temperature result |
| E6 Jensen: profile vs its mean temperature | λ_profile ≥ λ(mean T); example 40/70/105 °C at 50/30/20% gives AF_eff = 12.3 vs 46.3 |
| E8 | one slot → λ_sys = λ of that part; system FIT = sum of component FITs |
| E9 | R_sys(B0.1) = 0.999 |
| E11 | comparing a configuration with itself gives every Δ = 0 |
| E13 | self-comparison gives P = 0.5; two zero-failure parts give D_1/(D_1 + D_2) within MC error |
| 8c | empirical 0.1% quantile ≈ E9 (within 2%) |

### 11b. Real result 1: supplier-published FIT `[ON HOLD]`

- **Team decision (2026-10-30):** published FITs are **not used**, neither in the model nor in this
  validation. They're stored in `data/reference/published_fit.csv` in case we decide otherwise.
- **Why:** the team's report check showed that some published values (RH850, LTC6811, ISL78714)
  rest on larger datasets than the test data in our table. So a mismatch says nothing about our
  model.
- **If revived:** the file already holds our FIT calculated at each supplier's reference
  conditions, and the ratio to the published value. TI parts reproduce (C2000 6.21 vs 6.19), which
  remains the E4 known-answer test in 11a.

### 11c. Real result 2: industry reliability-prediction handbooks

- **Comparison:** predicted FIT for the same part *type* at the same temperature, from Siemens
  SN 29500, IEC 61709 and MIL-HDBK-217F Notice 2 (IC category, complexity and temperature
  factors), stored in `data/reference/handbook_rates.csv` with sources.
- **Metric:** log₁₀(simulator / handbook).
- **Expected:**
  - Agreement within about one order of magnitude.
  - Simulator values *at or below* SN 29500 / IEC 61709, because HTOL covers only thermal
    mechanisms and modern automotive ICs outperform reference rates.
  - Simulator values *well below* MIL-HDBK-217F, which is known to be pessimistic for modern
    parts.
- `[TODO: collect handbook values for the six part types]`

### 11d. Real result 3: field evidence

Collected in `data/reference/field_evidence.csv`, with sources:
- **Field failure rates** published for automotive ICs, as ppm or FIT from supplier quality
  reports, AEC/industry papers, or zero-defect program targets.
- **Real warranty and recall cases** for these component types:
  - the BMW HV-battery temperature sensor extended warranty (10 yr / 120,000 mi);
  - the Toyota Prius inverter current-sensor campaign;
  - the Mercedes EPS-ECU solder recall;
  - (charter references 1–4).

**Use:** recall populations rarely give a failure *rate*, so these are **plausibility checks**.
- Where a field rate exists: compare it to the simulator's FIT at a realistic profile. The
  expected direction is simulator ≤ field (A8).
- Where only a case exists: check whether the simulator flags that component type as a large
  share of system λ, or as sensitive to temperature.

`[TODO: collect field data]`

### 11e. Known-truth coverage study

1. Invent 1,000 synthetic "suppliers", each with a true λ.
2. Generate an HTOL result for each by Poisson-sampling failures from realistic n, t and T_test
   (including small and zero-failure tests).
3. Run the simulator on each.
4. Count how often the 95% interval contains the true λ, and how often P(B outlasts A) picks the
   truly better part.

**Expected:** coverage near 95%, and P(B outlasts A) well calibrated (when it says 0.8, B is truly
better about 80% of the time). This is the strongest check that the confidence intervals are
valid, and it needs no new data.

## 12. Code architecture

```
functions/
  arrhenius.py      kelvin(), accel_factor(), effective_af(), draw_ea()        E1, E2, E6, A2
  evidence.py       device_hours(), lambda_bound(), fit(), mttf_hours(), draw_lambda()   E3–E5, A5
  reliability.py    reliability(), unreliability(), density(), hazard(), series_lambda(),
                    b_life(), warranty_ratio(), p_meets_warranty()             E7–E10, E14
  library.py        load_library(), get_part()                                 component library
  simulator.py      evaluate(config, profile)               → component + system tables  (Mode 1)
                    compare(config_a, config_b, profile)    → A, B, differences, P(B > A) (Mode 2)
  validation.py     supplier_check(), handbook_check(), field_check(), coverage_study()  Section 11
  finance.py        warranty_cost(), eval_time_cost()                          Section 10
code/
  01_clean_data.py    raw xlsx → data/components.csv + data/codebook.md
  02_results.py       runs the simulator for every result in Section 9 → results/tables, results/figures
  03_validation.py    Section 11b–11e → validation tables and figures
  04_financial.py     Section 10 → before/after cost table with CIs
  05_make_report.py   writes reports/*.docx from the results tables
data/reference/
  handbook_rates.csv, field_evidence.csv   (with source citations)
tests/
  test_library.py, test_equations.py (E1–E6, draws), test_reliability.py (E7–E10, E14),
  test_simulator.py, test_validation.py
```

- A configuration is a plain mapping from slot to part, e.g.
  `{"ECU MCU": "F280049", "Gate driver": "UCC21750-Q1"}`.
- A profile is a list of (temperature °C, fraction), e.g. `[(55, 1.0)]`.
- `evaluate()` and `compare()` return DataFrames and do no plotting. The later UI calls exactly
  these two functions.

## 13. Build order

Each milestone ends with its tests passing and this file updated.

| # | Milestone | Done when |
|---|---|---|
| M0 | Roadmap agreed (this file) | The team has reviewed the simulator design and model |
| M1 ✅ | Component library | `data/components.csv` (19 parts, 17 usable), `data/codebook.md`, `functions/library.py`; 16 tests in `tests/test_library.py` pass |
| M2 ✅ | Equation functions (E1–E10, E14) and Monte Carlo draws (A2, A5) | 11a tests for these pass (50 tests in total) |
| M3 | Simulator Mode 1 `evaluate()` | Component + system outputs with CIs for any 1–6 slot configuration and any profile |
| M4 | Simulator Mode 2 `compare()` | A, B, differences and P(B outlasts A); self-comparison checks pass |
| M5 | Verification | All 11a tests pass (11b on hold) |
| M6 | Real-result validation | 11c–11e done, reference data cited |
| M7 | Results + financial | Section 9 and 10 tables and figures in `results/` |
| M8 | Reports | Preliminary Results and Financial Impacts .docx in `reports/` |
| M9 | User interface `[LATER]` | Front end over `evaluate()` / `compare()` |

## 14. Data issues

**Rule:**
- The simulator uses only the parts' **raw test data**, which keeps the common basis.
- Published FITs are stored in `data/reference/` and not used (11b on hold).
- A part missing any of T_test, t, n, f or Ea is `usable = False` and is excluded from simulation.
  We never fill the gap with a guess.
- The raw table's "Mission time = 120,000 hours" column isn't used.

**Missing values** (parts excluded until the values are found in the supplier reports):
- **Renesas ISL78714:** failures blank. Its published 3.72 FIT is verified and comes from seven HTOL
  test groups, so we need each group's temperature, duration, sample size and failures.
- **ADI MAX31730:** sample size blank.

**Other cleaning fixes:**
- "ASUM4135" corrected to ADuM4135.
- "Rensas" corrected to Renesas Electronics.
- Some prices are for orderable variants or family proxies; each is flagged in `flag`.
- The current sensor has no price.

**Published vs calculated FIT.** The team checked the supplier reports (2026-10-30). The raw table
**mixes FITs reported directly by manufacturers with FITs that can be calculated from the
transcribed test data**. A mismatch therefore usually means the manufacturer used a larger or
different dataset, not that a value is wrong.

These are stored, outside the model, in `data/reference/published_fit.csv`:
- `fit_published`, unchanged, with `fit_published_status`, `fit_published_source` and
  `fit_published_note` from `data/reference/fit_verification.csv`;
- `fit_calculated` and `fit_calc_ratio`, our chi-square bound at the same reference conditions.

The full table is in `data/codebook.md`. The headlines:

| Family | Published | Status | Calculated | Reading |
|---|---|---|---|---|
| TI (all) | 0.1–6.19 | not checked | ratio 0.68–1.16 | Reproduced within TI's rounding |
| Renesas RH850 | 0.0011 | verified (pp. 4, 7) | 15.3 | Renesas's basis is much larger than the 231-device HTOL test |
| ADI LTC6811-1 | 33.95 | verified (r582 p. 2) | 0.32 | Reported directly by ADI at 0.7 eV / 60%; our table's data isn't ADI's basis |
| Renesas ISL78714 | 3.72 | verified (7 HTOL groups) | — | Needs per-group data |
| ADI ADuM4135 | 11.28 | **not verified** | 0.37 | Left out of FIT comparisons until ADI replies |
| ADI ADuM141E | 20.23 | not checked | 0.45 | Check the report |

## 15. Changelog

| Date | Change |
|---|---|
| 2026-10-29 | v1: simulator design with Mode 1 Evaluate and Mode 2 Compare; equations, assumptions, build order. Saved in `docs/roadmap_history/ROADMAP_v1_simulator_2026-10-29.md`. |
| 2026-10-29 | v2: failure rates held as Gamma(f+1, D) distributions (the 60% bound kept as the datasheet-style value). Dynamic AF over temperature profiles built in. Ea uncertainty (A2). Nested Monte Carlo engine with common random numbers. New outputs P(WR ≥ 1) and P(B outlasts A) (E13–E14). Added Section 11, evaluating the simulator: verification, plus validation against supplier FITs, handbooks, field evidence and a known-truth coverage study. |
| 2026-10-29 | M1 done: `code/01_clean_data.py` builds `data/components.csv` (19 parts, 17 usable) with `data/codebook.md`; `functions/library.py` (`load_library`, `get_part`); 10 tests pass. Found that ISL78714's failure count is blank, so it's excluded alongside MAX31730. Added `pytest.ini`. |
| 2026-10-30 | Team verified published FITs against supplier reports (LTC6811, ISL78714 and RH850 verified; ADuM4135 not verified). Added `data/fit_verification.csv`, plus library columns `fit_published_status/source/note` and `fit_calculated`, `fit_calc_ratio`, `fit_calc_note`; published values are never overwritten. Added `functions/arrhenius.py` (E1–E2) and `functions/evidence.py` (E3–E5) with 9 tests in `tests/test_equations.py`; 23 tests pass. |
| 2026-10-30 | Team decision: keep published FITs **out of the model**. The model stays on test data only (the v2 approach). Published values, verification and our calculated FIT moved out of `components.csv` into `data/reference/published_fit.csv` and `data/reference/fit_verification.csv`, stored for a possible later decision. 11b put on hold. 25 tests pass. |
| 2026-10-31 | M2 done. `functions/arrhenius.py` adds `effective_af()` (E6, vectorized over Ea draws) and `draw_ea()` (A2). `functions/evidence.py` adds `draw_lambda()` (E4/A5, uniform or Jeffreys prior). New `functions/reliability.py` (E7–E10, E14). Tests: E6 one-bin degenerate, the 40/70/105 °C example (AF_eff 12.29 vs 46.30), the Tencer T_aa equivalence, the Gamma 60th percentile vs the chi-square bound (f = 0, 1, 3), 6.21 FIT from draws, series sum/product, R(B0.1) = 0.999, warranty ratio and P(WR ≥ 1). 50 tests pass. |
