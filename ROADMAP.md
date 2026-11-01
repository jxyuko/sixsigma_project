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

TASER-EV is a Monte Carlo simulator for a **vehicle maker choosing between suppliers**. The user
enters candidate parts for any of the six component **slots** (ECU MCU, BMS AFE, digital isolator,
temperature sensor, gate driver, current sensor), each from that supplier's reliability report,
plus their own operating temperature and how long the part must work. The simulator turns every
candidate's accelerated-life test into reliability at that one condition, *with its uncertainty*,
and compares them (the user-facing simulator, below).

**Team decision (2026-10-31): the user sees only this simulator** (formerly "Mode 3"). Our
**component library** (`parameter_table.xlsx`) is not offered to users; it is what we used to
**build and test** the simulator (default Ea, A12; validation, Section 11). The library-based
functions `evaluate()` and `compare()` (formerly Modes 1–2) stay in the code as the tested engine
for validation; they are not a user option.

### Internal engine 1: `evaluate()` (library parts; validation only)

```
inputs:  operating temperature T_op (or a temperature profile)  +  1–6 slots, one library part each
              │
              ▼
per component:  AF, equivalent device-hours, FIT, MTTF, R(t)            each as median + 95% CI
system:         R_sys(t) band, system FIT/MTTF, B0.1 life, B0.1-to-warranty ratio,
                estimated life in years, and P(meets warranty) = P(WR ≥ 1)
```

### Internal engine 2: `compare()` (library parts; validation only)

```
inputs:  T_op  +  configuration A (1–6 slots)  +  configuration B (1–6 slots)
              │      the two can differ in which parts AND which slots are used
              ▼
Mode 1 outputs for A and for B, side by side
differences B − A for every metric (absolute and %), with 95% CI
P(B outlasts A) = P(B0.1,B > B0.1,A)   ← "is B really better, given how much each was tested?"
```

### The simulator: supplier selection (`select()`, user-facing)

The user is a vehicle maker choosing between suppliers. For any of the six slots they enter as many
candidates as they like, each from that supplier's reliability report, and state their own
requirement. The simulator puts every candidate on the same basis (the user's operating condition)
and compares them.

```
inputs:  operating temperature (or profile)  +  mission hours  +  target R(mission)
         (required confidence is fixed at 95%, A13)
         + per slot (any of the six, skipped slots are left out of the system): any number of
           candidates, each with EITHER raw HTOL data (test temperature, hours, sample size, failures)
           OR a report summary (FIT or MTTF/MTBF, the temperature and confidence it refers to,
           failures), plus Ea if the report states one
         + optional (defaults in brackets): target [0.999], vehicles [1,000], repair cost per
           failure [the part's unit price], warranty hours [the mission hours], each candidate's
           unit price [Sheet2 price list], Ea [0.7 eV with A2 spread]
              │
              ▼
per candidate:   AF, FIT, MTTF, B0.1, R(mission) (median + 95% CI), lower confidence bound on
                 R(mission), P(R ≥ target), meets target (yes/no), P(best in its slot), unit price,
                 warranty failures, warranty cost, purchase cost and total cost (95% CIs)
combinations:    every pick of one candidate per entered slot, ranked by system FIT, with system
                 R(mission), lower bound, P(meets target), P(best combination), warranty failures,
                 warranty cost, total cost and total cost vs the most reliable one (paired draws);
                 plus the combination with the lowest total cost
output order:    SUMMARY: plain sentences, the best candidate per slot (reliability, target met,
                          chance it is best), the most reliable system, its warranty exposure and
                          total cost, and the lowest-cost system if different
                 KEY TABLE: one row per candidate: R(mission) with 95% CI, meets target, chance
                          best in slot, warranty failures, total cost
                 DETAILS (--details or on request; always saved to CSV): reliability, requirement
                          check with prices and costs, all combinations
note:            only operation above 150 °C (AEC-Q100 Grade 0) gets an informational note
```

**Why the user's report data, not a warranty:** a supplier warranty is a commercial promise
(period, remedy, exclusions such as use beyond datasheet ratings). It contains no test temperature,
sample size, failures or Ea, so it cannot put suppliers on a common basis. The **warranty exposure**
in the assignment is the vehicle maker's own: expected failures and cost over *their* warranty
(E12), computed from each candidate's reliability.

**Input scope.** See Section 5. `[LATER]`: quantity per slot (A10) and the web app (M9).

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
1. **Supplier results:** the FIT, MTBF and AF published in our parameter table, at each
   supplier's stated temperature and confidence level. These values are **never model inputs**;
   they are only used to check the simulator's output (11b).
2. **A known-truth coverage study:** synthetic suppliers with a true failure rate we set
   ourselves, used to check that the simulator's 95% intervals contain the truth about 95% of the
   time (11e).

Handbook (SN 29500, IEC 61709, MIL-HDBK-217F) and field-data comparisons were considered and
dropped by the team (2026-10-31): the team will not supply that data, and the parameter table's
published values already give a real-result check.

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

### User inputs (the simulator, `code/02_run_simulator.py`)

| Input | Required? | Default | Notes |
|---|---|---|---|
| Operating temperature, or a profile {(T_i, w_i)} | **required** | | One temperature is a one-bin profile (E6) |
| Mission hours: how long the part must work at that condition | **required** | | Sets R(mission) and the requirement (E17) |
| Candidates: for each slot of interest, any number, each with a name and its report's test temperature | **required** (≥ 1) | | Skipped slots are left out of the system |
| Each candidate's evidence: test hours + sample size + failures, **or** a FIT, **or** an MTTF/MTBF | **required** | failures 0 | Summary forms also take the temperature [test temperature] and confidence level [60%] they are stated at (A11, E15) |
| Target reliability over the mission | optional | 0.999 | Confidence fixed at 95% (A13) |
| Vehicles, for warranty exposure | optional | 1,000 | A14 |
| Cost of one warranty repair | optional | the part's unit price | Parts-only lower bound (A14) |
| Warranty period in operating hours | optional | the mission hours | |
| Candidate unit price | optional | Sheet2 price list | A14 |
| Activation energy Ea | optional | 0.7 eV with 0.5–0.9 spread | A12 |

### Outputs

Summary first, then a key table, then details (Section 2). Every number is a median with a 95%
CI unless it is a probability, a bound or a yes/no.

| Level | Output | Equation |
|---|---|---|
| Candidate | AF to the user's condition, FIT, MTTF, B0.1, R(mission) | E2–E7, E9 |
| Candidate, requirement | 95% lower bound on R(mission), P(R ≥ target), meets target | E17 |
| Candidate, comparison | P(best in slot), rank in slot | E16 |
| Candidate, money | unit price, warranty failures, warranty cost, purchase cost, total cost | E12, A14 |
| System (each combination) | system FIT, R(mission), B0.1, lower bound, P(meets target), P(best combination) | E8, E9, E16, E17 |
| System, money | warranty failures, warranty cost, total cost, total cost vs the most reliable system; lowest-cost system | E11, E12, A14 |

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
| A7 | **Warranty period in operating hours: one value for the whole system.** 8 years × 365 days × 1 powered-on hour per day = **2,920 h** (`DEFAULT_WARRANTY_HOURS` in `functions/simulator.py`). Every slot is treated as powered for the same hours, including the BMS parts that may also run while charging. | Failure rates are per operating hour, but warranties are stated in years and miles. One system value keeps WR simple and comparable across configurations. Parts powered longer (e.g. the BMS during charging) make this optimistic; the low/base/high sensitivity (8d) shows how much it matters. | `[DECIDED]` (team, 2026-10-31) `[TODO: cite a source for 1 h/day]` |
| A8 | **Only thermally activated failure mechanisms** are modelled. | HTOL only accelerates these. Cycling, vibration and humidity would add failures, so our life is an upper bound on field life, and we expect to under-predict field failure rates (11d). | `[DECIDED]` |
| A9 | **Parts in one qualification family share data**: the 4 TI C2000 parts, and the 5 RH850 parts. | That's how the suppliers report it. | `[DECIDED]` |
| A10 | **One part per slot** (quantity 1) for now. | It keeps comparisons clean. Quantities scale λ_sys linearly (E8), so adding them later is easy. | `[DEFAULT]` |
| A11 | **Mode 3 report summaries:** a supplier's FIT or MTTF is the chi-square bound (E4) at its stated temperature and confidence level, from its stated failures. Defaults when the report doesn't say: confidence 60%, failures 0, temperature = test temperature. | This is how suppliers compute published FIT (11b reproduces TI's values this way), so the summary can be turned back into test evidence (E15) and gets the same uncertainty treatment as raw data. | `[DEFAULT]` |
| A13 | **Mode 3 required confidence is fixed at 95%.** A candidate meets the target only if the 95% lower confidence bound on R(mission) is at least the target (E17). | Team decision (2026-10-31): one standard for every comparison, matching the 95% intervals used everywhere else. | `[DECIDED]` |
| A14 | **Cost basis for warranty exposure:** exposure is reported per 1,000 vehicles unless the user gives a fleet size. A candidate's unit price is the user's, else the Sheet2 price of a matching part number, else the Sheet2 average for its slot. Cost per warranty failure is the user's repair cost, else the part's unit price. Total cost = purchase (vehicles × unit price) + expected warranty cost. | The user may not know fleet size or repair cost. Per-1,000 figures are readable without them, and Sheet2 prices are sourced (distributor links). Parts-only cost is a **lower bound**: real repairs add labour and often a whole module, so it understates warranty cost. | `[DECIDED]` (team, 2026-10-31) |
| A12 | **Mode 3 activation energy:** a value stated in the report is used as given (fixed). Otherwise Ea is drawn as in A2, centred on the library ("training data") median Ea, which is 0.7 eV because every library report assumes 0.7. | Uses the supplier's own physics when known, and the evidence in our dataset when not. | `[DEFAULT]` |

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
share of paired draws where it's true. Ties (identical draws, e.g. comparing a configuration with
itself) count as half, so self-comparison gives exactly 0.5. Closed-form check: for two single zero-failure parts 1
and 2 at the same T_test (so they share an AF), the probability that part 1 has the lower failure
rate is P(λ_1 < λ_2) = D_1 / (D_1 + D_2).

**E14 · Probability of meeting warranty.**  P(WR ≥ 1) = share of draws with B0.1 ≥ t_w.

**E15 · Test evidence from a report summary (Mode 3, A11).** A published FIT (or 1/MTTF) λ_pub at
reference temperature T_ref, confidence CL and f failures implies

  n · t = χ²(CL; 2f + 2) / (2 · λ_pub · AF(T_ref))

with AF from the supplier's Ea (E2). Known answer: 6.211 FIT at 55 °C, 60%, f = 0 from a 125 °C
test gives n·t = 1.9×10⁶ device-hours, TI C2000's raw data.

**E16 · Probability of being the best of k.** P(i best) = share of draws in which candidate i has the
lowest rate (ties split evenly). Closed form for zero-failure candidates at one test temperature:
P(i best) = D_i / Σ_j D_j (generalizes E13).

**E17 · Reliability requirement (Mode 3).** For mission time t_m and target R*:
P(R(t_m) ≥ R*) = share of draws meeting it; lower confidence bound R_L = the (1 − confidence)
quantile of R(t_m) over draws, with confidence fixed at 95% (A13); "meets the target" ⇔ R_L ≥ R*.
Known answer at T_op = T_test with f = 0: R_L = exp(−t_m · (−ln 0.05) / D).

**Evidence needed to pass (Mode 3 reading aid).** With f = 0, a candidate meets R* over t_m with 95%
confidence only if its test evidence is at least n · t ≥ −ln(0.05) / (λ* · AF(T_op)), where
λ* = −ln(R*) / t_m. Example, 1,000 h at 200 °C with R* = 0.999: λ* = 1.0×10⁻⁶ /h and AF(200 °C from a
125 °C test) = 0.039, so n · t ≥ 7.6×10⁷ device-hours. TI C2000 has 1.9×10⁶ (40× short); UCC21750 has
8.7×10⁷ (passes).

**E18 · Maximum failure rate (course chi-square k-factor method).** One-sided (1 − α) upper bound on an
exponential rate from f failures in D device-hours at the use condition: f = 0 → λ₁₋α = −ln(α)/D;
f ≥ 1 → λ̂ · k with λ̂ = f/D and k = χ²(1 − α; 2(f + 1)) / (2f). Both equal χ²(1 − α; 2f + 2)/(2D) (E4).

**E19 · Target test.** H₀: λ ≥ λ* (target not met), λ* = −ln(R*)/t_m. Exact p-value = P(X ≤ f) with
X ~ Poisson(λ* D). Reject at α ⇔ λ₁₋α < λ*. Minimum MTTF = 1/λ₁₋α; minimum R(t_m) = exp(−λ₁₋α t_m).

**E20 · Maximum demonstrated temperature.** The use temperature at which E18 equals λ*:
AF_needed = χ²(1 − α; 2f + 2)/(2 n t λ*), then 1/T = 1/T_test + k ln(AF_needed)/Ea (inverse of E2).

**E21 · Two-rate test.** Exact conditional test that two Poisson rates are equal: given f₁ + f₂
failures, f₂ ~ Binomial(f₁ + f₂, D₂/(D₁ + D₂)) under H₀. With f₁ = f₂ = 0, p = 1 (no evidence).

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

**Reproducibility:** fixed random seed (default 5300), recorded in every results file.

**Common random numbers in code:** `draw_library()` draws Ea and one λ_test array per qualification
family (A9) for the whole library, in a fixed order. Any configuration run on the same `Draws`
therefore uses identical draws for the same part, which is what Mode 2 needs.

**Years in outputs:** `mttf_years_continuous` and `b01_years_continuous` are hours ÷ 8,760, i.e.
years of 24/7 operation, not calendar years. Calendar life depends on the duty assumption (A7).

## 9. Results for the Preliminary Results report

**Kept apart from the simulator code** (team decision 2026-11-01): `analysis/01_preliminary_results.py`
only *calls* the simulator and writes to `reports/preliminary_results/` (`tables/`, `figures/`,
`key_numbers.md`). It runs our library parts through the user-facing simulator as if they were a
vehicle maker's candidates (one part per qualification family, A9).

**Main condition** (team decision 2026-11-01): 55 °C (the parameter table's reference temperature),
mission 2,920 h (A7), target R ≥ 0.999 with 95% confidence (A13), 5,000 draws, seed 5300. Warranty
exposure as failures per 1,000 vehicles; no costs here (Section 10 is deferred).

| # | Analysis | Statistic | Output |
|---|---|---|---|
| 1 | Measures | FIT, MTTF, R(mission), B0.1, 95% lower bound on R, P(R ≥ target), P(best), failures per 1,000 vehicles; each a median + 95% CI over 5,000 draws | all tables |
| 2 | Common basis: every candidate at 55 °C with its test conditions and AF | E2–E9, E17 | Table 1, Figure 1 (forest plot, log FIT) |
| 3 | Supplier comparison within each slot | paired failure-rate ratio (alternative / TI, 95% CI) and P(TI best) (E11, E16) | Table 2 |
| 4 | System: all 16 combinations, most vs least reliable | system FIT, R(mission), B0.1, lower bound, P(meets target), P(best combination) (E8, E16, E17) | Table 3 |
| 5 | Temperature sweep 25–150 °C, most vs least reliable system; profile vs its mean temperature | failures per 1,000 vehicles (95% CI), P(meets target); E6 | Figures 2a and 2b, `profile_vs_mean_temperature.csv` |
| 6 | Sensitivity, one assumption at a time (8d) | median failures per 1,000 vehicles for: temperature ±10 °C, mission ½ / ×2, Ea fixed / independent, Jeffreys prior, MC seed | Figure 3 (tornado) |
| 7 | Validation | published FIT reproduced (11b); coverage (11e); Brier score of P(B outlasts A) | Table 4a, 4b |

**Results (2026-11-01):**
- **Per slot,** the TI candidate is more likely the more reliable in every contested slot
  (P(TI best) 0.70–0.85), but every paired ratio's 95% CI spans 1 (e.g. isolator: ADuM141E's rate
  is 3.65× ISO7741's, CI 0.29–110): with zero-failure tests the data favour TI without proving it.
- **System:** the all-TI combination is the most reliable: system FIT 7.0 (95% CI 1.1–38),
  R(2,920 h) = 0.99998 (95% lower bound 0.99991), meets the target, 0.021 failures per 1,000 vehicles
  (0.003–0.112). The least reliable (RH850 + LTC6811 + ADuM141E + ADuM4135 + TMP4719 + TMCS1101) has
  FIT 14.3 (1.8–109) and still meets the target at 55 °C. P(all-TI is truly the best of 16) = 0.32.
- **Temperature:** the most reliable system meets the target up to 90 °C, the least reliable up to
  75 °C. On the illustrative 40/70/105 °C profile the system FIT is 3.8× its value at the 62 °C mean.
- **Sensitivity:** operating temperature (±10 °C) and mission length (½ / ×2) each move failures
  roughly 2× either way; the prior moves them 2.5× lower (Jeffreys); Ea treatment and MC seed are
  negligible (< 5%).
- **Validation:** as in 11b and 11e.

## 9b. Significance and confidence (Preliminary Results)

`analysis/02_significance.py` (kept apart from the simulator; statistics in `functions/significance.py`,
tests in `tests/test_significance.py`) writes `sig_*` tables and figures and
`key_numbers_significance.md` to `reports/preliminary_results/`. Course methods only: exponential
chi-square bounds (k-factors), one-sample t-test, proportion CIs and the percentile bootstrap.

**Part 1, statistics about the simulator (is it trustworthy?), results 2026-11-01:**

| # | Test | Result |
|---|---|---|
| 1a | Simulator vs course chi-square formula (E18), 95% max FIT, 10 parts, 20 seeds | largest difference 0.65%, all within Monte Carlo error |
| 1b | Simulator vs published TI FIT, one-sample t-test on log10(simulated / published), 6 families | mean ratio 0.91 (95% CI 0.70–1.20), t = −0.88, p = 0.42: not significantly different |
| 1c | Coverage of the 95% intervals, exact (Clopper-Pearson) CIs, binomial test vs nominal | realistic world: central interval 94.0%, 96.2%, 95.3% (all p ≥ 0.46) once ≥ 0.1 failures are expected, 36.8% below that; upper bound 99.8% (99.3–100%). Model-consistent world: 95.3% overall (p = 0.72) |
| 1d | Calibration of P(B outlasts A), Brier score with bootstrap 95% CI | 0.119 (0.105–0.133) model-consistent, 0.186 (0.168–0.204) realistic; coin flip 0.25 |
| 1e | Monte Carlo error over 20 seeds | system FIT and failures per 1,000 vary 2.0% per run; lower bound on R 0.0003% |

**Part 2, what the simulator concludes on our data (55 °C, 2,920 h, R* = 0.999), results 2026-11-01:**

| # | Test | Result |
|---|---|---|
| 2a | Per part, 95% maximum failure rate and target test (E18, E19) | all 10 parts demonstrate the target (largest p = 1.2×10⁻⁹); 95% max FIT 0.38–50 vs target 343 FIT |
| 2a | Maximum demonstrated temperature per part (E20) | RH850 83 °C, C2000 97 °C, TMCS1101 121 °C, ADuM4135 152 °C, ADuM141E and LTC6811 155 °C, ISO7741 and UCC21750 176 °C, TMP4719 and BQ79656 179 °C (values above 150 °C exceed usual automotive ratings) |
| 2b | System 95% lower bound on R and target test (Monte Carlo); max demonstrated temperature (bisection) | most reliable (all-TI): R_L = 0.999913, p < 0.0002, demonstrated up to 95 °C; least reliable: R_L = 0.999766, up to 78 °C |
| 2c | Supplier differences per slot: exact two-rate test (E21) and simulation p | no difference significant at 0.05 (exact p = 1.00, 1.00, 0.40, 1.00; simulation p 0.15–0.30): zero-failure tests cannot separate the suppliers |
| 2d | 40/70/105 °C profile vs its 62 °C mean, paired ratio of system failure rate | 3.77× (95% CI 2.33–6.46), P(ratio ≤ 1) < 0.001: significant |

**Reading:** the simulator is verified (1a), agrees with published values (1b), and its upper bounds
are valid (1c), so the demonstrated-reliability conclusions (2a, 2b) can be trusted; supplier rankings
(2c) are not statistically significant, and the temperature profile effect (2d) is.

## 10. Financial model

**Deferred** (team decision 2026-11-01): the Financial Impacts report comes after the Preliminary
Results. The simulator already computes warranty exposure and cost (A14); the report analysis will
be added as `analysis/02_financial_impacts.py` → `reports/financial_impacts/`.

**Suggestion kept for later:** a cited cost of one warranty repair (part + labour, e.g. ECU/BMS
module replacement). Until then the cost per failure is the part's unit price, a parts-only lower
bound, and costs are reported per 1,000 vehicles only.

Unit prices come from Sheet2 of `parameter_table.xlsx` (distributor prices with links), cleaned
into `data/prices.csv` (A14).

**10a. Warranty exposure, before vs after** (built into the simulator, A14):
- For every candidate and combination: warranty failures N · F(t_w), warranty cost
  N · F(t_w) · C_fail (E12) and total cost = N · unit price + warranty cost, per draw, so 95% CIs
  come straight from the simulation. N defaults to 1,000 vehicles; C_fail defaults to the unit
  price (parts-only lower bound).
- Before vs after = any two combinations; the simulator reports each one's total cost vs the most
  reliable combination (paired draws) and names the lowest-cost combination.

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

Status: **all pass (77 tests, M5, 2026-10-31).** Run with `.venv/Scripts/python -m pytest`.

| Check | Expected | Result | Test(s) |
|---|---|---|---|
| E2: AF(55 °C, test at 125 °C, 0.7 eV) | 77.65 ± 0.01 (matches the table's 77.6454) | ✅ | `test_equations::test_af_known_answer` |
| E2 degenerate: T = T_test | AF = 1 | ✅ | `test_af_degenerate_same_temperature` |
| E4 known answer: TI C2000, n = 1900, t = 1000, 125 °C → 55 °C, CL = 0.6, f = 0 | 6.21 FIT (TI publishes 6.19) | ✅ 6.21 | `test_lambda_known_answer_ti_c2000`, `test_simulator::test_known_answer_fit_60pct_bound` |
| E4 closed form: f = 0 | λ_CL = −ln(1 − CL)/D | ✅ | `test_lambda_zero_failure_closed_form` |
| E4 distribution: 60th percentile of 100,000 Gamma(f+1, D) draws | within 1% of λ_0.60 (f = 0, 1, 3) | ✅ | `test_gamma_60th_percentile_is_chi_square_bound`, `test_gamma_draws_known_answer_ti_c2000_fit` |
| E4 monotone | higher T_op, more failures or higher CL each give a higher λ | ✅ | `test_lambda_increases_with_use_temperature`, `test_lambda_increases_with_failures_and_confidence`, `test_simulator::test_hotter_is_worse` |
| E6 degenerate: one-bin profile | equals the single-temperature result | ✅ | `test_effective_af_one_bin_equals_single_temperature`, `test_profile_one_bin_equals_scalar` |
| E6 Jensen: profile vs its mean temperature | λ_profile ≥ λ(mean T); 40/70/105 °C at 50/30/20% gives AF_eff = 12.3 vs 46.3 | ✅ 12.29 vs 46.30 | `test_effective_af_known_answer_and_jensen`, `test_profile_worse_than_mean_temperature` |
| E6 = Tencer T_aa | AF_eff = AF(T_aa) | ✅ to 1e-10 | `test_effective_af_matches_arrhenius_average_temperature` |
| E7 | R(MTTF) = e⁻¹; R(0) = 1; constant hazard | ✅ | `test_reliability::test_life_functions_*`, `test_hazard_is_constant_over_time` |
| E8 | one slot → λ_sys = λ of that part; system FIT = sum of component FITs (per draw) | ✅ | `test_series_*`, `test_one_slot_system_equals_component`, `test_system_rate_is_sum_per_draw` |
| E9 | R_sys(B0.1) = 0.999 | ✅ | `test_b01_reliability_is_0999`, `test_b01_reliability_band` |
| E10, E14 | WR = 1 at t_w = B0.1; P(WR ≥ 1) = 1 for a tiny warranty, 0 for a huge one | ✅ | `test_warranty_ratio_degenerate`, `test_p_meets_warranty_*` |
| E11 | comparing a configuration with itself gives every Δ = 0; differences are paired per draw | ✅ | `test_self_comparison_is_neutral`, `test_differences_are_paired_draws` |
| E13 | self-comparison gives P = 0.5; two zero-failure parts give D_1/(D_1 + D_2) within MC error | ✅ 0.733 ± 0.02 | `test_p_outlasts_closed_form_two_zero_failure_parts`, `test_p_outlasts_ties_and_swap` |
| 8a whole pipeline | `evaluate()` FIT quantiles for one part, with Ea drawn, match numerical integration over the triangular Ea density | ✅ median 4.47 vs 4.54; 97.5% 35.7 vs 34.0 | `test_evaluate_matches_numerical_integration_over_ea` |
| 8a MC precision | 10 seeds of 5,000 draws: median system FIT spread < 10%, 97.5th percentile < 20% | ✅ 7.03–7.37; 36.9–41.0 | `test_monte_carlo_precision_of_5000_draws` |
| 8a CRN / reproducibility | same part → same draws in any configuration; same seed → same result | ✅ | `test_same_part_same_draws_across_configs`, `test_family_parts_share_draws`, `test_same_seed_reproduces` |
| 8c | empirical 0.1% quantile ≈ E9 (within 5%: with 4×10⁶ systems the quantile rests on ~4,000 failures, so its MC error is ~1.6%) | ✅ | `test_failure_time_check_matches_b01` |
| A5 sensitivity | Jeffreys prior gives lower FIT than uniform | ✅ | `test_jeffreys_prior_lowers_rates` |

**Not covered by 11a** (these are validation, M6): whether the simulated rates match the
published values (11b) and whether the 95% intervals cover a known true rate 95% of the time (11e).

### 11b. Real result 1: the parameter table's published FIT, MTBF and AF ✅

- **Team decision (2026-10-31):** the published values are used to **validate** the simulator.
  They are still **not model inputs** (decision of 2026-10-30 stands), so the check is independent.
- **Method** (`validation.supplier_check()`, `code/03_validation.py`): for every usable part, run
  `evaluate()` at the part's published reference temperature (55 °C) and compare:
  - FIT: the simulator's FIT draws with Ea fixed at the suppliers' 0.7 eV, taken at the published
    confidence level (60%), against the published FIT; also whether the published FIT falls inside
    the simulator's default 95% interval (Ea uncertain);
  - MTBF: 1e9 / simulator FIT against the published MTBF;
  - AF: the simulator's AF at 0.7 eV against the table's AF column.
- **Expected:** TI rows reproduce (their published FIT rests on the same n, t, f as our table).
  Non-TI rows may not, because the team found their published values rest on more data (Section 14).
- **Result (5,000 draws, seed 5300):**

| Family | Published FIT | Simulator at 60% | Ratio | Published inside simulator 95% CI | Verdict |
|---|---|---|---|---|---|
| TI C2000 | 6.19 | 6.17 | 1.00 | yes | reproduced |
| TI TMCS1101 | 1.7 | 1.67 | 0.98 | yes | reproduced |
| TI BQ79656 | 0.1 | 0.115 | 1.15 | yes | reproduced (TI rounds to 0.1) |
| TI TMP4719 | 0.1 | 0.117 | 1.17 | yes | reproduced (TI rounds to 0.1) |
| TI ISO7741 | 0.2 | 0.132 | 0.66 | yes | reproduced within 2× (rounded) |
| TI UCC21750 | 0.2 | 0.133 | 0.66 | yes | reproduced within 2× (rounded) |
| Renesas RH850 | 0.0011 | 15.5 | 14,000 | no | simulator higher: Renesas uses more data (verified) |
| ADI LTC6811-1 | 33.95 | 0.32 | 0.009 | no | simulator lower: ADI's basis differs (verified) |
| ADI ADuM141E | 20.23 | 0.45 | 0.022 | no | simulator lower: basis unknown |
| ADI ADuM4135 | 11.28 | 0.36 | 0.032 | no | simulator lower: 11.28 not found in ADI's report |

  - **AF:** the simulator's AF equals the table's AF exactly wherever the table gives one (77.6454
    for 125 → 55 °C, 259.18 for RH850's 150 → 55 °C).
  - **MTBF:** the simulator's MTBF matches TI's published MTBF (e.g. 8.71×10⁹ h for BQ79656 and
    TMP4719, 1.62×10⁸ h for C2000). The table's MTBF and FIT disagree with each other for
    BQ79656/TMP4719 (0.1 FIT is rounded) and for LTC6811-1 (MTBF 6.07×10⁹ h ⇔ 0.16 FIT, not 33.95).
  - **Conclusion:** every published value that rests on the same test data as our table is
    reproduced by the full simulator and lies inside its 95% interval. The values that are not
    reproduced are the ones the team already found to rest on different data.
- Outputs (generated locally by `code/03_validation.py`, not committed): `results/tables/validation_supplier_fit.csv`, `results/figures/validation_supplier_fit.png`.

### 11c. Industry handbooks `[DROPPED]`

Dropped by team decision (2026-10-31): the team will not supply handbook data, and the public
per-part figures are incomplete (TI's C2000 FMEDA rates are under NDA).

### 11d. Field evidence `[DROPPED]`

Dropped by team decision (2026-10-31), for the same reason. A8 (only thermal mechanisms) still
means the simulator is expected to under-predict field failure rates; this is stated as a
limitation instead of being measured.

### 11e. Known-truth coverage study ✅

1. Invent 1,000 synthetic "suppliers", each with a true λ.
2. Generate an HTOL result for each by Poisson-sampling failures from realistic n, t and T_test
   (including small and zero-failure tests).
3. Run the simulator on each.
4. Count how often the 95% interval contains the true λ, and how often P(B outlasts A) picks the
   truly better part.

**Expected:** coverage near 95%, and P(B outlasts A) well calibrated (when it says 0.8, B is truly
better about 80% of the time).

**Design** (`functions/validation.py`, `code/03_validation.py`, seeds 11 and 12, 55 °C):
- n from the library's range (231 to 101,758), t = 1,000 h, T_test 125 or 150 °C, true Ea drawn
  as in A2.
- Two "worlds" for the true FIT: **log-uniform** over 0.01–100 FIT (realistic: many zero-failure
  tests) and **uniform** over 0–100 FIT (close to the model's own prior, A5).
- Calibration pairs share T_test and true Ea (A2).

**Results (1,000 suppliers, 1,000 pairs per world):**

| Expected failures in the test | Suppliers (log-uniform) | Central 95% coverage | Upper 97.5% coverage |
|---|---|---|---|
| < 0.1 | 310 | 37% | 100% |
| 0.1–1 | 248 | 94% | 100% |
| 1–10 | 210 | 96% | 100% |
| > 10 | 232 | 95% | 99% |
| all | 1,000 | 77% | 99.8% |

- **The upper bound is valid everywhere** (99.8% ≥ 97.5%). The supplier-style claim "FIT is at
  most X" is trustworthy for every part.
- **The central interval is valid once a test could expect ≥ 0.1 failures** (94–96%). For very
  reliable parts on small tests, its *lower* end sits above the truth, because the data cannot
  tell how far below the upper bound the true rate is. In the uniform world, where such parts are
  rare, overall coverage is 95.3%.
- **P(B outlasts A):** Brier score 0.12 in the uniform world (a coin is 0.25) and close to
  calibrated; 0.19 in the log-uniform world, where it is **overconfident**: when it says ≥ 0.8, B is
  truly better 84% of the time; when it says ≤ 0.2, B is still truly better 20% of the time. This
  comes from zero-failure pairs, where P mostly reflects which part was tested more ("demonstrated
  reliability"), not which is truly better. One bin (P ≈ 0.5, uniform world, ~90 pairs) read 0.69;
  three other seeds gave 0.44, 0.56 and 0.53, so this is sampling noise.
- **Report wording:** quote upper bounds as guarantees, and present P(B outlasts A) as "strength
  of the test evidence", not as the probability that B is truly better.
- Outputs (generated locally by `code/03_validation.py`, not committed): `results/tables/validation_coverage.csv`, `validation_calibration.csv`,
  `validation_summary.csv`; figures `results/figures/validation_coverage.png`,
  `validation_calibration.png`.

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
  candidates.py     select(candidates, profile, mission_hours, ...) → candidate table, ranked
                    combinations, warnings  (Mode 3: E12, E15–E17, A11–A12)
  validation.py     supplier_check(), coverage_study(), calibration_study()   Section 11b, 11e
  interface.py      parse_profile(), component_table(), system_table(), difference_table()
                    (input parsing and readable tables for the run script and the later UI)
  finance.py        warranty_cost(), eval_time_cost()                          Section 10
code/
  01_clean_data.py    raw xlsx → data/components.csv + data/codebook.md
  02_run_simulator.py the simulator for a user: asks for the operating temperature (or profile),
                      mission hours and candidates (or --temp --hours --candidates file.csv),
                      prints SUMMARY → key table → details, saves CSVs to results/tables/runs/
                      (git-ignored)
  03_validation.py    Section 11b and 11e → validation tables and figures
analysis/                report material, kept apart from the simulator (only calls functions/)
  01_preliminary_results.py   Section 9 → reports/preliminary_results/ (tables, figures, key_numbers.md)
  02_significance.py          Section 9b → reports/preliminary_results/ (sig_* tables and figures,
                              key_numbers_significance.md); statistics in functions/significance.py
  plots.py                    every report figure, drawn with plotnine (ggplot grammar in Python)
  (Financial Impacts: not planned for now, Section 10)
reports/
  preliminary_results/, financial_impacts/   report tables, figures and the .docx deliverables
data/reference/
  published_fit.csv, fit_verification.csv   (published values: validation only, never model input)
data/examples/
  candidates_example.csv   simulator input template, filled with real library data
data/prices.csv            Sheet2 unit prices and slot averages (A14), built by 01_clean_data.py
tests/
  test_library.py, test_equations.py (E1–E6, draws), test_reliability.py (E7–E10, E14),
  test_simulator.py, test_validation.py (11b, 11e), test_interface.py (run script),
  test_candidates.py (Mode 3)
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
| M3 ✅ | Simulator Mode 1 `evaluate()` | Component + system outputs with CIs for any 1–6 slot configuration and any profile; 18 tests in `tests/test_simulator.py` (68 in total) |
| M4 ✅ | Simulator Mode 2 `compare()` | A, B, differences and P(B outlasts A); self-comparison checks pass; 23 tests in `tests/test_simulator.py` (73 in total) |
| M5 ✅ | Verification | All 11a tests pass (77 tests) |
| M6 ✅ | Real-result validation, and a runnable simulator | 11b (published FIT/MTBF/AF) and 11e (coverage, calibration) done, 11c–11d dropped; `code/02_run_simulator.py` asks for the operating temperature and prints all outputs; 94 tests pass |
| M6b ✅ | Mode 3: supplier selection | `select()` for any number of user candidates per slot (raw HTOL data or report FIT/MTTF), requirement check, P(best), ranked combinations and warranty exposure; in the run script; 19 tests in `tests/test_candidates.py` (113 in total) |
| M6c ✅ | One user-facing simulator | `code/02_run_simulator.py` runs supplier selection only (no library picking), required vs optional inputs, summary first, warranty exposure per 1,000 vehicles with Sheet2 prices; 117 tests |
| M7a ✅ | Preliminary Results analysis | Section 9 tables and figures in `reports/preliminary_results/` from `analysis/01_preliminary_results.py`; 120 tests |
| M7c ✅ | Significance and confidence | Section 9b: simulator verification and validation statistics, chi-square target tests, max demonstrated temperature, supplier tests, profile effect; 6 figures; 135 tests |
| M7b | Financial Impacts analysis `[LATER]` | Section 10 before/after cost with CIs in `reports/financial_impacts/` |
| M8 | Reports | Preliminary Results and Financial Impacts .docx in `reports/` |
| M9 | User interface `[LATER]` | Front end over `evaluate()` / `compare()` |

## 14. Data issues

**Rule:**
- The simulator uses only the parts' **raw test data**, which keeps the common basis.
- Published FITs are stored in `data/reference/` and are never model inputs; they are used only
  to validate the simulator (11b).
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
| 2026-10-31 | M3 done. New `functions/simulator.py`: `draw_library()` (8a, per-family draws for common random numbers, shared or independent Ea), `evaluate()` (Mode 1: component AF_eff, D, FIT, MTTF, R(t_w) and the 60% datasheet-style FIT; system FIT, MTTF, R(t_w), B0.1, WR, P(WR ≥ 1), all as median + 95% CI), `reliability_band()`, `qi()`, `failure_time_check()` (8c). A7 placeholder warranty 2,920 h (8 yr × 1 h/day, unsourced). 8c tolerance set to 5% from the MC error. All-TI at 55 °C: system FIT 7.0 (95% CI 1.1–40), B0.1 142,000 h, WR 49, P(WR ≥ 1) = 1.00; on the 40/70/105 °C profile: FIT 46 (8.7–186), WR 7.5 (1.8–39), P = 0.999. 68 tests pass. |
| 2026-10-31 | Team decision (A7): the 2,920 h warranty (8 yr × 1 powered-on h/day) is adopted as one warranty for the whole system, no longer a placeholder. Source for 1 h/day still to cite. |
| 2026-10-31 | M4 done. `functions/simulator.py` adds `compare()` (Mode 2: both configurations on one set of draws, E11 differences per draw for every system metric, P(meets warranty) for each), `p_outlasts()` (E13, ties count half) and `system_draws()` (shared by `evaluate()` and `compare()`). Tests: self-comparison gives Δ = 0 and P = 0.5; LTC6811-1 vs BQ79656 matches the closed form D_B/(D_A+D_B) = 0.733; paired per-draw differences; adding slots never lowers λ_sys. Example at 55 °C, A = all-TI: B = RH850 MCU gives system FIT 13.7 vs 7.0, P(B outlasts A) = 0.29; B = ADI AFE + isolator + gate driver gives 7.9 vs 7.0, P = 0.09. 73 tests pass. |
| 2026-10-31 | M5 done. 11a now maps every check to its test(s) and result. New checks: λ monotone in T_op over 25–125 °C; whole-pipeline check of `evaluate()` against numerical integration over the Ea density (median 4.47 vs 4.54 FIT, 97.5% 35.7 vs 34.0); MC precision over 10 seeds (median system FIT 7.03–7.37); Jeffreys prior lowers FIT. 77 tests pass. |
| 2026-10-31 | M6 done. Team decisions: (1) validate against the parameter table's published FIT, MTBF and AF (still never model inputs); (2) drop handbook (11c) and field (11d) comparisons. New `validation.supplier_check()` (11b) runs the full simulator at each part's published conditions: all six TI families reproduced within 2× (C2000 6.17 vs 6.19) and inside the 95% CI, AF exact, MTBF matches; RH850, LTC6811-1, ADuM141E, ADuM4135 not reproduced (different published basis). New coverage and calibration study (11e): upper 97.5% bound covers 99.8%; central 95% interval 94–96% once a test expects ≥ 0.1 failures but 37% below that; P(B outlasts A) Brier 0.12 (model-consistent) / 0.19 (realistic), overconfident for zero-failure pairs. `draw_library()` gains `ea_mode="fixed"` (Ea = 0.7). New `code/02_run_simulator.py` (asks for the operating temperature or profile and parts, prints all Mode 1/2 outputs; also one-command use) with `functions/interface.py`; run outputs git-ignored. Section 9's results script renumbered `06_results.py`. 94 tests pass. |
| 2026-10-31 | M6b: Mode 3 supplier selection (team scenario: a vehicle maker compares candidate suppliers tested at different temperatures, at its own condition, e.g. 1,000 h at 200 °C). New `functions/candidates.py` (`select()`), E15 (report FIT/MTTF → test evidence), E16 (P(best of k)), E17 (requirement R(mission) ≥ target with confidence), A11 (summary defaults: 60%, f = 0), A12 (Ea from the report, else the library median 0.7 with A2 spread). Skipped slots are left out of the system. Warranty exposure (E12) per candidate and per combination, with extra cost vs the best combination. Warnings above 150 °C and above a test temperature. Run script gains Mode 3 (interactive and `--candidates`); example input `data/examples/candidates_example.csv` uses real library data. 113 tests pass. |
| 2026-10-31 | Team decision (A13): Mode 3's required confidence is fixed at 95% and is no longer an input (removed from the prompt and `--confidence`). Explained why the MCUs fail the 200 °C example: at 200 °C, C2000 would need ~40× and RH850 ~99× more test device-hours to show R(1,000 h) ≥ 0.999 with 95% confidence; at 55 °C both pass. 113 tests pass. |
| 2026-10-31 | Mode 3 output now leads with reliability at the user's condition (new `reliability_table()`: AF, R(mission) with 95% CI, FIT, MTTF, B0.1 per candidate), for operating temperatures below or above each test temperature alike. Removed the "extrapolated upward" warning (AF < 1 above T_test is normal Arrhenius use); the > 150 °C remark is now a note. Lower bounds shown to 6 decimals so borderline pass/fail is visible. 113 tests pass. |
| 2026-10-31 | The simulator is for users' own inputs: result files from our test and validation runs on the original data (validation tables/figures, demo runs) are not committed; `code/03_validation.py` regenerates them. Mode 3 printed tables now show MTTF and B0.1 with 95% CIs and warranty failures next to cost. 114 tests pass. |
| 2026-10-31 | Team decisions: (1) users see only the supplier-selection simulator; the library is used to build and test it, and `evaluate()`/`compare()` remain only as the validation engine (Modes 1–2 removed from the run script); (2) warranty exposure without inputs the user may not know (A14): per 1,000 vehicles, unit prices from Sheet2 (new `data/prices.csv`, 30 parts + 6 slot averages; the current-sensor average has no listed rows), cost per failure = unit price (parts-only lower bound) unless a repair cost is given, total cost = purchase + warranty, lowest-cost combination reported. Run script rewritten: only temperature, mission hours and candidates are required; output is SUMMARY → key table → details on request. Arguments now `--temp --hours --candidates [--target --fleet --repair-cost --warranty-hours --details]`. 117 tests pass. |
| 2026-11-01 | M7a done. Team decisions: report analyses live apart from the simulator (`analysis/` → `reports/`); main condition 55 °C, 2,920 h, target 0.999; Financial Impacts deferred; a cited repair cost kept as a suggestion; costs per 1,000 vehicles only. New `analysis/01_preliminary_results.py`: Tables 1–4, Figures 1–3, temperature sweep, profile vs mean, sensitivity, `key_numbers.md` (results in Section 9). `select()` gains `ea_mode` (shared / independent / fixed) for the sensitivity. New `tests/test_analysis.py` (paired ratio: identical evidence → 1, known answer D_ti/D_alt). 120 tests pass. |
| 2026-11-01 | M7c: significance and confidence (Section 9b). Team decision: the Preliminary Results reports statistics about the simulator (verification and validation) and the statistics it produces; Financial Impacts and report writing are not planned for now. New `functions/significance.py` (E18 course maximum failure rate, E19 target test, E20 max demonstrated temperature, E21 exact two-rate test, one-sample t-test, Clopper-Pearson CI, bootstrap CI, MC error) with 15 tests; new `analysis/02_significance.py` (11 tables, 6 figures, `key_numbers_significance.md`). Key results: simulator = chi-square within 0.65%; vs published TI p = 0.42; all parts demonstrate the target at 55 °C; all-TI system demonstrated up to 95 °C; no supplier difference significant; profile effect 3.77× (2.33–6.46). 135 tests pass. |
| 2026-11-01 | Report figures redrawn with plotnine (ggplot grammar, as in the course's Python track) so the team can run and adapt them in Posit Cloud: new `analysis/plots.py` holds all 10 figures; both analysis scripts call it. Figure 2 split into 2a (failures vs temperature) and 2b (P(meets target) vs temperature), one axis each. `plotnine` added to requirements.txt. Numbers unchanged; 135 tests pass. |
