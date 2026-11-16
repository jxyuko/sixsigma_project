# TASER-EV Roadmap

**Read this first.** This is the single source of truth for *how* we build the TASER-EV simulator:
what it does, the model and approach, assumptions, equations, how we evaluate it, code layout,
build order and data issues.

**Update rule:** every commit that changes the method, an assumption, a number, or the code
structure also updates this file and adds one line to the [Changelog](#15-changelog). If code and
roadmap disagree, fix one of them in the same commit. Earlier versions are kept in
`docs/roadmap_history/`.

Status tags: `[DECIDED]`, `[DEFAULT]` (our working choice, can still change), `[TODO]` (needs a
source or data), `[LATER]` (possible extension, not planned now).

**Current design (v4, 2026-11-14):** one user-facing simulator for supplier selection, built and
tested on the team's component library, using the course's exponential estimate and chi-square
confidence bounds (after the instructors' feedback), with the report analyses kept apart in
`analysis/`. Earlier designs (v1 Modes 1–2, v2 with Mode 3, v3 with Monte Carlo Gamma draws) are in
`docs/roadmap_history/`; the v3 code is git tag `v1-gamma-model`.

Contents:
1. [Research question](#1-research-question) |
2. [What the simulator does](#2-what-the-simulator-does) |
3. [Model / approach](#3-model--approach) |
4. [Component library](#4-component-library) |
5. [Inputs and outputs](#5-inputs-and-outputs) |
6. [Assumptions](#6-assumptions) |
7. [Equations](#7-equations) |
8. [Calculation engine](#8-calculation-engine) |
9. [Preliminary Results](#9-preliminary-results) |
10. [Warranty exposure, cost and Financial Impacts](#10-warranty-exposure-cost-and-financial-impacts) |
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

TASER-EV is an accelerated-life reliability simulator for a **vehicle maker choosing between
suppliers**. We developed it for this project; it is not taken from the literature, but every step is
a standard method we cite: the Arrhenius model (E2), the course's exponential estimate and
chi-square confidence bounds (E4; Tobias & Trindade 2003, ch. 3; Recitation 12), the Arrhenius
average temperature for profiles (E6; Tencer et al. 2004) and the series system (E8). Figure 0
(`reports/preliminary_results/figures/figure0_flowchart.png`) shows how it is used.

The user enters candidate parts for any of the six component **slots** (ECU MCU, BMS AFE, digital
isolator, temperature sensor, gate driver, current sensor), each from that supplier's reliability
report, plus their own operating temperature and how long the part must work. The simulator puts
every candidate's accelerated-life test on that one condition, *with its uncertainty*, and compares
them. Engine: `select()` in `functions/candidates.py`; program: `code/02_run_simulator.py`.

```
inputs:  operating temperature, or the band min-max the part runs across  +  mission hours  +  target R
         (required confidence is fixed at 95%, A13)
         + per slot (any of the six; skipped slots are left out of the system): any number of
           candidates, each with EITHER raw HTOL data (test temperature, hours, sample size, failures;
           one or several test groups)
           OR a report summary (FIT or MTTF/MTBF, the temperature and confidence it refers to,
           failures), plus Ea if the report states one
         + optional (defaults in brackets): target [0.999], vehicles [1,000], cost of one warranty
           replacement [the part's unit price], warranty hours [the mission hours], each candidate's
           unit price [Sheet2 price list], Ea [0.7 eV, or a 0.5–0.9 eV range by Monte Carlo]
              │
              ▼
per candidate:   AF, FIT, MTTF, B0.1, R(mission): estimate + 95% CI (E4); 95% maximum failure rate
                 and lower bound on R(mission); meets target (yes/no); rank in its slot; unit price,
                 warranty failures, warranty cost, purchase cost and total cost (estimate + 95% CI)
combinations:    every pick of one candidate per entered slot, ranked by estimated system FIT, with
                 system R(mission), lower bound, meets target, warranty failures, warranty cost, total
                 cost and total cost vs the most reliable one; plus the lowest-cost combination
output order:    SUMMARY: the condition and settings; then BEST COMBINATIONS, three picks, each with
                          system FIT (estimate; every part at its 2.5th / 97.5th percentile), failures
                          per 1,000, meets target (95% maximum vs the target FIT), worst case at the band's
                          maximum, the Ea range if chosen, and total cost:
                            most reliable  = lowest estimated system failure rate
                            safest         = lowest 95% maximum system failure rate
                            cheapest       = lowest total cost AMONG combinations that meet the target
                                             (none if no combination meets it)
                          then the best part in each slot (team decision 2026-11-16)
                 ALL CANDIDATES: one row per candidate: FIT (2.5th–97.5th %, "0*" marks a zero lower
                          bound), failures per 1,000, meets target, unit price
                 DETAILS (--details): R(mission), its 95% lower bound and B0.1 of the best combinations,
                          and every candidate's AF, FIT, the supplier-style 60% upper bound FIT
                          (comparable with datasheets; for the report discussion), MTTF, B0.1 and R
                 CSV (always): every candidate and every combination with all columns
note:            only operation above 150 °C (AEC-Q100 Grade 0) gets an informational note
```

**Why the user's report data, not a warranty:** a supplier warranty is a commercial promise
(period, remedy, exclusions such as use beyond datasheet ratings). It contains no test temperature,
sample size, failures or Ea, so it cannot put suppliers on a common basis. The **warranty exposure**
the simulator reports is the vehicle maker's own: expected failures and cost over *their* warranty
(E12, Section 10), computed from each candidate's reliability.

**The component library is not a user option** (team decision 2026-10-31). The team's
`parameter_table.xlsx` (Section 4) is what we used to **build and test** the simulator: it sets the
default Ea (A12), supplies real candidates for the Preliminary Results (Section 9), and is the data
for validation (Section 11).

**`[LATER]`:** quantity per slot (A10) and a web front end that calls the same `select()`.

## 3. Model / approach

**The problem.** Suppliers report reliability from High Temperature Operating Life (HTOL) tests
run at different stress temperatures, sample sizes, test lengths and confidence levels. They then
quote a FIT at their own reference use temperature, usually 55 °C. An engineer whose part runs at
85 °C in an inverter can't use those numbers directly. Nor can they compare a TI part to an Analog
Devices part, because the two FITs weren't produced on the same basis. Our check of the collected
data confirms it: several published FIT values can't be reproduced from the supplier's own test
parameters (Section 14).

TASER-EV therefore **doesn't use the published FIT as its input**. For every part it stores the
raw test parameters (sample size n, test duration T, stress temperature T_test, failures r,
activation energy Ea), **calculates** every reliability parameter from them (Table 0 lists the
calculated values next to the published ones, and the calculated values are the ones used), and
rebuilds the reliability through five layers. Every part goes through the same layers, so the
outputs are on a common basis.

**Method v4 (instructors' feedback, 2026-11-14).** The professor and the TA asked us to use the
exponential distribution with the course's estimation directly from test duration, sample size and
failures, to give upper and lower bounds on λ, to rerun the cost results at the 2.5th and 97.5th
percentile failure rates, to try the lognormal and Weibull, to present sensitivity analyses in one
table with one baseline setting, to add a flowchart, and to study how much data supplier
comparisons need. Our earlier "Gamma(f + 1, D)" draws were the same chi-square bounds written as a
Bayesian posterior, which is outside the course; v4 states everything with the course's methods
and drops the Monte Carlo draws, priors and posteriors. The v3 design is in
`docs/roadmap_history/ROADMAP_v3_2026-11-14.md` and git tag `v1-gamma-model`.

**Layer 1 – Evidence: each test is an amount of evidence, not a quality score (E3–E4).**
- A test of n units for T hours with r failures is, under a constant failure rate (exponential life,
  A1), *exactly* "n·T device-hours with r failures". Nothing else in the test matters for the rate.
- Point estimate λ̂ = r / D (D = device-hours at the use condition). Most tests saw **zero
  failures**, where r / D = 0 is unrealistic; the course's 50% zero-failure estimate −ln(0.5)/D =
  0.693/D is used instead (Recitation 12).
- 95% confidence interval from the chi-square k-factors (time-censored, Type I): upper
  χ²(0.975; 2r + 2)/(2D), lower χ²(0.025; 2r)/(2D), which is **0 when r = 0** (zero failures cannot
  rule out a rate of 0). The one-sided 95% upper bound χ²(0.95; 2r + 2)/(2D) is the course's
  "maximum failure rate" (E18), and its 60% version is the bound suppliers publish.
- Zero failures in 7,000 units and zero in 100,000 units are not "bad part" vs "good part"; they are
  **weak vs strong evidence**: the interval is wide for the first and narrow for the second.

**Layer 2 – Physics: from test temperature to the user's temperature (E1–E2, E6).**
- HTOL tests speed up thermally activated failure mechanisms. The Arrhenius model says their rate
  scales with exp(−Ea/kT), so one hour at T_test does the damage of AF hours at the use
  temperature.
- The simulator computes AF separately for every part, because each was tested at its own
  temperature: 125 °C for most, 150 °C for the Renesas RH850.
- **Dynamic AF.** Vehicles don't run at one temperature. Following the Research Design (Tencer et
  al., 2004), the user can give a profile: temperatures and the fraction of time at each.
  - The simulator averages the **failure rates** over the profile, not the temperatures or the AFs.
  - For a 50/30/20% profile at 40/70/105 °C, the mean temperature (62 °C) gives AF = 46.3, but the
    correct rate-averaged AF is 12.3: averaging temperatures would overstate life almost four-fold.
- **Ea** is 0.7 eV, the value every report in our library assumes (A2); 0.5 and 0.9 eV are rows of
  the sensitivity table.

**Layer 3 – Mission: what time period matters.** Failure rates are per operating hour, so the
user states the mission in operating hours. The report's case study uses 2,920 h, the team's
whole-system warranty converted to powered-on hours (8 years × 1 h/day, A7).

**Layer 4 – System: series block diagram (E7–E9).**
- Each selected component is a single point of failure in the battery/inverter chain, so a
  combination of candidates is a **series system**: the system rate is the sum of the parts' rates
  and R_sys(t) = e^(−λ_sys·t). Slots the user leaves empty are left out.
- The **baseline** sums the parts' estimates. The professor's uncertainty layer reruns everything
  with every part at its 2.5th and at its 97.5th percentile failure rate (a deliberately wide
  scenario range, not a 95% CI of the sum).

**Layer 5 – Requirement and comparison (E17–E21).**
- **Requirement:** a part or system "meets the target" if the R(mission) given by its 95% maximum
  failure rate is at least the target (A13; for a system, the sum of the parts' 95% bounds, which is
  conservative). The same test gives the maximum demonstrated temperature (E20).
- **Comparison:** candidates are ranked by their estimates; whether a difference is real is the
  exact two-rate test (E21), and how much data that test needs is Section 9c (E27–E29).
- **Warranty exposure and cost:** expected failures and cost per 1,000 vehicles, and total cost
  with the purchase price (Section 10).

**Other life distributions (E24–E26, A16).** The lognormal and Weibull are fitted to each test with
a shape parameter from the literature (SEMATECH 2000: lognormal σ ≈ 0.5 wear-out, ≈ 1.5 defects;
β = 1.2/σ), because zero-failure tests cannot estimate a shape. They are rows of the sensitivity
table; the exponential stays the baseline. The Lesson 12B chi-square goodness-of-fit test needs
observed failure times, which zero-failure HTOL tests do not have, so the distribution cannot be
tested from our data.

**Evaluation (Section 11).** Beyond the verification tests (11a, including every Recitation 12
worked example), we compare the calculated values with:
1. **Supplier results:** the FIT, MTBF and AF published in our parameter table. These values are
   **never model inputs**; they only check the calculation (11b).
2. **A known-truth coverage study:** synthetic suppliers with a true failure rate we set, used to
   check that the 95% intervals contain the truth at least 95% of the time (11e).

Because only thermally activated mechanisms are modelled (A8), the simulator is expected to predict
*fewer* failures than the field; this is stated as a limitation.

**How this answers the research question.**
- Layers 1–2 put accelerated-life data from different suppliers onto a **common basis**: the same
  temperature or profile, the same statistical treatment, the same equations.
- Layers 3–4 turn that into the life and reliability an engineer decides with, for one part or a
  whole system.
- Layer 5 checks the user's requirement and makes comparisons **meaningful** by testing whether a
  difference is real and saying how much test data a real comparison would need.
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
| unit_price_usd, price_part | | USD | Price-sheet price and which part number it came from (the simulator prices candidates from `data/prices.csv`, A14) |
| source | | | Bibliography number; report URL `[TODO]` |
| usable | | bool | All of T_test, t, n, f, Ea present |
| flag | | | Data-quality notes (Section 14) |

**The model reads only test data.** Manufacturer-published FITs, MTBFs and their reference
conditions, the team's verification of them, and our FIT calculated at the same conditions are
stored separately in `data/reference/published_fit.csv` and `data/reference/fit_verification.csv`.
They are **never model inputs** (team decision 2026-10-30); they are used only to validate the
simulator (11b, team decision 2026-10-31).

**Out of scope:** mechanical parts, ICE vehicles, software failures, and failure mechanisms that
aren't thermally activated.

## 5. Inputs and outputs

### User inputs (the simulator, `code/02_run_simulator.py`)

| Input | Required? | Default | Notes |
|---|---|---|---|
| Operating temperature, or a band min–max the part runs across (time spread evenly) | **required** | | One temperature, or a band (E6); a band also reports the worst case at its maximum (team decision 2026-11-15) |
| Mission hours: how long the part must work at that condition | **required** | | Sets R(mission) and the requirement (E17) |
| Candidates: for each slot of interest, any number, each with a name and its report's test temperature | **required** (≥ 1) | | Skipped slots are left out of the system |
| Each candidate's evidence: test hours + sample size + failures, **or** a FIT, **or** an MTTF/MTBF | **required** | failures 0 | Summary forms also take the temperature [test temperature] and confidence level [60%] they are stated at (A11, E15) |
| Target reliability over the mission | optional | 0.999 | Confidence fixed at 95% (A13) |
| Vehicles, for warranty exposure | optional | 1,000 | A14 |
| Cost of one warranty replacement | optional | the part's unit price | The failed part is replaced (A14) |
| Warranty period in operating hours | optional | the mission hours | |
| Candidate unit price | optional | Sheet2 price list | A14 |
| Activation energy Ea | optional | 0.7 eV, or the range 0.5–0.9 eV (Monte Carlo, shared or separate per part) | A2, A12; a stated Ea is always used as given |
| Test groups per candidate | optional | 1 | Several HTOL groups at different temperatures/sizes (E3) |

### Outputs

Summary first, then a key table, then details (Section 2). Every number is an estimate with its
95% CI (E4) unless it is a bound or a yes/no.

| Level | Output | Equation |
|---|---|---|
| Candidate | AF to the user's condition, FIT, MTTF, B0.1, R(mission) | E2–E7, E9 |
| Candidate, requirement | 95% maximum FIT, 95% lower bound on R(mission), meets target | E17, E18 |
| Candidate, comparison | rank in slot (by estimate) | E4 |
| Candidate, money | unit price, warranty failures, warranty cost, purchase cost, total cost | E12, A14 |
| System (each combination) | system FIT, R(mission), B0.1 (estimate and bound scenarios), lower bound, meets target | E8, E9, E17 |
| System, money | warranty failures, warranty cost, total cost, total cost vs the most reliable system; lowest-cost system | E12, A14 |

## 6. Assumptions

Each assumption has an ID so code comments and the report can cite it.

| ID | Assumption | Why it's reasonable / what it costs us | Status |
|---|---|---|---|
| A1 | **Constant failure rate (exponential life)** over the period of interest: the baseline. | Zero-failure HTOL data can't identify a Weibull or lognormal shape. FIT is by definition a constant rate, constant hazard is the convention for the useful-life region (Lesson 12), and SEMATECH (2000, p. 29) notes the exponential "works well if there are very few or zero failures". Infant mortality is removed by AEC-Q100 screening. The lognormal and Weibull are sensitivity rows (A16). | `[DECIDED]` (professor's feedback, 2026-11-14) |
| A2 | **Arrhenius acceleration; Ea = 0.7 eV by default, or a range 0.5–0.9 eV at the user's choice.** With the range, a Monte Carlo draws Ea ~ triangular(0.5, 0.7, 0.9) (5,000 draws, seed 5300), one draw shared by all parts unless the user picks a separate draw per part, and reports the 2.5th–97.5th percentile of the estimate over the draws, a full range (Ea plus the rate's 95% bounds), and whether the target still holds at the unfavourable end. | 0.7 eV is every supplier's assumption in our library. The 0.5–0.9 range spans common thermally activated mechanisms. Ea is not data, so its range is propagated by simulation rather than estimated. At 55 °C (125 °C tests) it changes λ̂ 12× across the range, at 85 °C 3.7×, at the test temperature not at all, so it is the largest uncertainty at normal vehicle temperatures. | `[DECIDED]` (2026-11-15). Sources: Blish & Durrant, *Semiconductor Device Reliability Failure Models*, International SEMATECH #00053955A-XFR (2000): electromigration 0.5–0.6 eV (Al, Al-Si) and 0.7–0.9 eV (Al-Cu), corrosion 0.7–0.8 eV, stress migration 0.55 eV; Vigrass, *Calculation of Semiconductor Failure Rates*, Intersil/Renesas application note: 0.7 eV assumed for an unknown mechanism. |
| A3 | **T_op is the component junction temperature.** The user gives one temperature, or a band T_min–T_max the part runs across with its time spread evenly (team decision 2026-11-15, replacing typed-in profiles); the estimate at T_max is reported as a worst case. | The Arrhenius AF is defined at the junction. Rates are averaged over the band (E6), following Tencer et al. (2004), so hot hours count more. | `[DECIDED]` |
| A4 | **Series system with independent failures.** | Every selected component is a single point of failure. Independence is standard without common-cause data. It's slightly optimistic if one thermal event hits several parts. | `[DECIDED]` |
| A5 | **Failure rate from the test: the course's exponential estimate and chi-square bounds** (E4): λ̂ = r/D, or 0.693/D with zero failures (the 50% zero-failure estimate); 95% CI from the k-factors, with a lower bound of 0 when r = 0. | The course method (Recitation 12; Tobias & Trindade 2003, ch. 3), estimated directly from test duration, sample size and failures, as the professor asked. It reproduces the supplier convention (60% bound) exactly. A positive zero-failure lower bound was tried and rejected: it covers the truth only 81% of the time (11e). v3's Gamma draws were the same bounds written as a Bayesian posterior, outside the course. | `[DECIDED]` (2026-11-14) |
| A6 | **Sample size × test hours = device-hours at T_test**, using the supplier's pooled sample size where one is given. | It's the only number published. TI's FIT reproduces exactly under this reading. | `[DEFAULT]` |
| A7 | **Warranty period in operating hours: one value for the whole system.** 8 years × 365 days × 1 powered-on hour per day = **2,920 h** (`DEFAULT_WARRANTY_HOURS` in `functions/reliability.py`). Every slot is treated as powered for the same hours, including the BMS parts that may also run while charging. | Failure rates are per operating hour, but warranties are stated in years and miles. One system value keeps the comparison simple. It is the mission used in the report's case study (Section 9). Parts powered longer (e.g. the BMS during charging) make this optimistic; the sensitivity (½ / ×2, Section 9) shows how much it matters. | `[DECIDED]` (team, 2026-10-31). Source for 1 h/day: Hungund & Steinbach, *American Driving Survey: 2024*, AAA Foundation for Traffic Safety (Dec. 2025): U.S. drivers average 60.4 minutes of driving per day. |
| A8 | **Only thermally activated failure mechanisms** are modelled. | HTOL only accelerates these. Cycling, vibration and humidity would add failures, so our life is an upper bound on field life, and we expect to under-predict field failure rates (stated as a limitation). | `[DECIDED]` |
| A9 | **Parts in one qualification family share data**: the 4 TI C2000 parts, and the 5 RH850 parts. | That's how the suppliers report it. | `[DECIDED]` |
| A10 | **One part per slot** (quantity 1) for now. | It keeps comparisons clean. Quantities scale λ_sys linearly (E8), so adding them later is easy. | `[DEFAULT]` |
| A11 | **Report summaries as input:** a supplier's FIT or MTTF is the chi-square bound (E4) at its stated temperature and confidence level, from its stated failures. Defaults when the report doesn't say: confidence 60%, failures 0, temperature = test temperature. | This is how suppliers compute published FIT (11b reproduces TI's values this way), so the summary can be turned back into test evidence (E15) and gets the same uncertainty treatment as raw data. | `[DEFAULT]` |
| A12 | **Activation energy for user candidates:** a value stated in the report is used as given. Otherwise the library ("training data") median Ea, 0.7 eV, because every library report assumes 0.7. | Uses the supplier's own physics when known, and the evidence in our dataset when not. | `[DEFAULT]` |
| A13 | **Required confidence is fixed at 95%.** A candidate meets the target only if the 95% lower confidence bound on R(mission), from the 95% maximum failure rate, is at least the target (E17, E18); a system uses the sum of its parts' bounds. | Team decision (2026-10-31): one standard for every comparison, matching the 95% intervals used everywhere else. | `[DECIDED]` |
| A14 | **Cost basis for warranty exposure:** exposure is reported per 1,000 vehicles unless the user gives a fleet size. A candidate's unit price is the user's, else the Sheet2 price of a matching part number, else the Sheet2 average for its slot. Each warranty failure is a replacement of the failed component; its cost is the user's replacement cost, else the part's unit price. Total cost = purchase (vehicles × unit price) + expected warranty cost. | The user may not know fleet size or replacement cost. Per-1,000 figures are readable without them, and Sheet2 prices are sourced (distributor links). Pricing a replacement at the component's own price leaves out labour and logistics, so it understates the full warranty cost. | `[DECIDED]` (team, 2026-10-31) |
| A15 | **Prices of library candidates in the financial analysis** are the library's Sheet2 match: the exact part, an orderable variant, or a **family proxy** (C2000 priced as F2800157, RH850 as R7F7016843); TMCS1101 has none and uses the Sheet2 current-sensor average. | These are the only sourced prices in our data. The MCU proxy prices drive most of the purchase difference, so the purchase saving is stated as depending on them (Section 10). | `[DEFAULT]` |
| A16 | **Shapes for the lognormal and Weibull alternatives:** lognormal σ = 0.5 (wear-out) and 1.5 (defects); Weibull β = 1.2/σ = 2.4 and 0.8. Each test fixes the scale through its fraction failed at the equivalent test time T·AF (E24–E25). | Zero-failure tests can't estimate a shape. Source: Blish & Durrant, *Semiconductor Device Reliability Failure Models*, International SEMATECH #00053955A-XFR (2000), p. 29: "Typical sigma values are: ~0.5 for wearout; ~1.5 for defects", and β = 1.2/σ. Time scaling by AF assumes the same Arrhenius acceleration for every model. | `[DEFAULT]` |

## 7. Equations

All equations are implemented once in `functions/` and cited by number in code comments.

**E1 · Kelvin.** T[K] = T[°C] + 273.15

**E2 · Arrhenius acceleration factor** from the part's test temperature T_s to a use temperature T:

  AF(T) = exp[ (Ea / k) · (1/T − 1/T_s) ],  with k = 8.617333×10⁻⁵ eV/K

AF > 1 when T < T_s, and AF = 1 when T = T_s. Example: Ea = 0.7, T = 55 °C, T_s = 125 °C gives
AF = 77.65.

**E3 · Equivalent device-hours at the use condition.**  D = Σ_g n_g · T_g · AF_eff,g over the part's
test groups g (one group for most reports), with r = Σ_g r_g failures (AF_eff from E6; for one
temperature, AF_eff = AF(T_op)). Each group keeps its own test temperature.

**E4 · Failure rate: estimate and confidence bounds** (course exponential method, Recitation 12;
time-censored HTOL tests, r failures in D device-hours):

  λ̂ = r / D  (r ≥ 1);   λ̂ = −ln(0.5) / D = 0.693 / D  (r = 0, the 50% zero-failure estimate)
  upper p-percentile (p ≥ 0.5):  λ_p = χ²(p; 2r + 2) / (2D)    = k-factor × λ̂, k = χ²(p; 2(r+1))/(2r)
  lower p-percentile (p < 0.5):  λ_p = χ²(p; 2r) / (2D)        = 0 when r = 0
  95% CI = [λ_0.025, λ_0.975];  with r = 0 the upper bound is −ln(0.025)/D = 3.689/D (Table 3.7)

λ_0.60 is the bound suppliers publish (with r = 0, −ln(0.4)/D). Known answers (all in `tests/`):
Recitation 12 Examples 1, 2, 6, 7 (k-factors and CIs), Example 8 (zero failures: 433.2, 752.5,
1,872.3 FIT) and Table 3.7.

**E5 · FIT and MTTF.**  FIT = λ · 10⁹;  MTTF = 1/λ hours (∞ at a lower bound of 0).

**E6 · Dynamic AF over a temperature profile** {(T_i, w_i)}, Σw_i = 1. Average the **rates**:

  λ_profile = Σ w_i · λ(T_i)   ⇔   1/AF_eff = Σ w_i / AF(T_i)

This is equivalent to the Arrhenius average temperature T_aa of Tencer et al. (2004), defined by
exp(−Ea/kT_aa) = Σ w_i · exp(−Ea/kT_i). Never average the temperatures or the AFs. A band T_min–T_max
with time spread evenly is 1/AF_eff = (1/(T_max − T_min)) ∫ dT / AF(T), computed with 200 equal bins
(`operating_profile()`); e.g. 40–105 °C from a 125 °C test gives AF_eff = 11.9 (AF(105 °C) = 2.9,
AF(40 °C) = 254).

**E7 · Component life functions** (A1), with t in operating hours:

  R(t) = e^(−λt),  F(t) = 1 − R(t),  f(t) = λe^(−λt),  h(t) = λ

**E8 · Series system** over the selected slots S (1 ≤ |S| ≤ 6):

  R_sys(t) = Π_{j∈S} R_j(t) = exp(−λ_sys · t),  λ_sys = Σ_{j∈S} λ_j

Also: FIT_sys = λ_sys · 10⁹ and MTTF_sys = 1/λ_sys. The baseline sums estimates; the bound scenarios
sum every part's 2.5th or 97.5th percentile.

**E9 · B0.1 life.**  B0.1 = −ln(1 − 0.001) / λ_sys = 0.0010005 / λ_sys

**E10 · Warranty ratio.**  WR = B0.1 / t_w (WR ≥ 1: B0.1 outlasts the warranty).

**E11–E14, E16** (paired Monte Carlo differences, P(B outlasts A), P(meets warranty), P(best)):
**retired in v4** with the Monte Carlo draws. Their numbers are kept for reference.

**E12 · Warranty exposure: expected warranty failures and cost** for a fleet of N vehicles over the
warranty t_w, at the baseline and at each bound:

  E[failures of part i] = N · (1 − e^(−λᵢ·t_w))
  Warranty cost = Σᵢ E[failures of part i] · C_fail,i
  Total cost = N · Σᵢ (unit price)ᵢ + Warranty cost

C_fail,i is the cost of replacing the failed part: its unit price unless a replacement cost is given (A14). The system's failures,
N · (1 − e^(−λ_sys·t_w)), equal the sum of the parts' expected failures to first order when F is small.

**E15 · Test evidence from a report summary (A11).** A published FIT (or 1/MTTF) λ_pub at
reference temperature T_ref, confidence CL and f failures implies

  n · t = χ²(CL; 2f + 2) / (2 · λ_pub · AF(T_ref))

with AF from the supplier's Ea (E2). Known answer: 6.211 FIT at 55 °C, 60%, f = 0 from a 125 °C
test gives n·t = 1.9×10⁶ device-hours, TI C2000's raw data.

**E17 · Reliability requirement.** For mission time t_m and target R*: the 95% lower confidence bound
R_L = exp(−λ_0.95 · t_m) with the one-sided 95% upper bound λ_0.95 (E4, E18); "meets the target" ⇔
R_L ≥ R* (A13). For a system, λ_0.95 is the sum of the parts' bounds (conservative). Known answer at
T_op = T_test with r = 0: R_L = exp(−t_m · (−ln 0.05)/D).

**E18 · Maximum failure rate (course chi-square k-factor method).** One-sided (1 − α) upper bound on an
exponential rate from r failures in D device-hours at the use condition: r = 0 → λ₁₋α = −ln(α)/D;
r ≥ 1 → λ̂ · k with λ̂ = r/D and k = χ²(1 − α; 2(r + 1))/(2r). Both equal χ²(1 − α; 2r + 2)/(2D) (E4).

**E19 · Target test.** H₀: λ ≥ λ* (target not met), λ* = −ln(R*)/t_m. Exact p-value = P(X ≤ r) with
X ~ Poisson(λ* D). Reject at α ⇔ λ₁₋α < λ*. Minimum MTTF = 1/λ₁₋α; minimum R(t_m) = exp(−λ₁₋α t_m).

**E20 · Maximum demonstrated temperature.** The use temperature at which E18 equals λ*:
AF_needed = χ²(1 − α; 2r + 2)/(2 n T λ*), then 1/T = 1/T_test + k ln(AF_needed)/Ea (inverse of E2).

**E21 · Two-rate test.** Exact conditional test that two Poisson rates are equal: given f₁ + f₂
failures, f₂ ~ Binomial(f₁ + f₂, D₂/(D₁ + D₂)) under H₀. With f₁ = f₂ = 0, p = 1 (no evidence).

**E22 · Saving from a change.** For a "before" and an "after" combination: saving = cost_before −
cost_after for purchase, warranty and total cost (E12), at the baseline and at each bound.

**E23 · Break-even replacement cost.** C* = (purchase_after − purchase_before) / (failures_before −
failures_after). Implemented and tested (`break_even_replacement_cost()`), not reported: the
recommended parts are cheaper to buy (Section 10).

**E24 · Fraction failed in the test** (life models, A16). With r of n devices failed by t_eq = T·AF
equivalent use-hours: estimate F = r/n (r = 0: 1 − 0.5^(1/n)); p-percentile = exact binomial
(Clopper-Pearson); r = 0: 1 − (1 − p)^(1/n) above the median, 0 below it.

**E25 · Scale that passes through the test.** Exponential λ = −ln(1 − F)/t_eq (r = 0 gives exactly
the course formula −ln(1 − p)/(n t_eq)); Weibull η = t_eq / (−ln(1 − F))^(1/β); lognormal
t50 = t_eq / exp(σ z(F)).

**E26 · Unreliability at the mission.** Exponential 1 − e^(−λt); Weibull 1 − exp(−(t/η)^β);
lognormal Φ(ln(t/t50)/σ). Series system: F_sys = 1 − Π(1 − F_i).

**E27 · Planning: sample size or test time** (Recitation 12). Device-hours to demonstrate λ_obj with
confidence c and at most r failures: n·T = χ²(c; 2r + 2)/(2 λ_obj) (r = 0: −ln(1 − c)/λ_obj); solve for
n or T. Known answers: Examples 9, 10, 12, 13 (928 units, 3,392 h, 12 units, 16,094 h).

**E28 · Power of the two-rate test.** For expected failures μ₁ and μ₂ (μ = λ·D), power = Σ over the
Poisson outcomes of P(f₁, f₂) · 1[the E21 one-sided p ≤ α], computed exactly.

**E29 · Failures needed for a comparison.** The smallest μ₁ (better supplier's expected failures,
equal device-hours) at which E28 reaches 80% for a true rate ratio ρ; device-hours = μ₁/λ.

## 8. Calculation engine

v4 has **no random draws in the simulator**: every output is a closed-form estimate and its 95%
bounds (E4), so results are exact and reproducible. One **baseline setting** is used throughout
(55 °C, 2,920 h, Ea 0.7 eV, exponential life, the failure-rate estimate); every change is one row of a
single sensitivity table (Section 9, Table 5), as the professor asked.

**8a. Per candidate:** AF_eff (E2, E6) → D = n·T·AF (E3) → λ̂, λ_0.025, λ_0.975 and λ_0.95 (E4,
E18) → FIT, MTTF, R(mission), B0.1, warranty failures and costs at the estimate and at each bound
(E5, E7, E9, E12); R, MTTF and B0.1 take their lower bound from the rate's upper bound.

**8b. Per combination:** the same outputs for λ_sys (E8), the requirement with the summed 95% bounds
(E17), ranking by estimated FIT, and the lowest-cost combination.

**8c. Simulation is kept only where it answers a question about the method itself:** the
known-truth coverage study (11e, Poisson-sampled test outcomes) and nothing else. Power (E28) is
computed exactly, not simulated.

## 9. Preliminary Results

**Kept apart from the simulator code** (team decision 2026-11-01): `analysis/01_preliminary_results.py`
only *calls* the simulator and writes to `reports/preliminary_results/` (`tables/`, `figures/`,
`key_numbers.md`). It runs our library parts through the user-facing simulator as if they were a
vehicle maker's candidates (one part per qualification family, A9), priced as in A15
(`analysis/common.py` holds the shared settings).

**Baseline** (team decision 2026-11-01, method v4 2026-11-14): 55 °C (the parameter table's
reference temperature), mission 2,920 h (A7), target R ≥ 0.999 with 95% confidence (A13), Ea 0.7 eV,
exponential life, the failure-rate estimate. Figures are drawn with plotnine in `analysis/plots.py`.

| # | Analysis | Statistic | Output |
|---|---|---|---|
| 0 | How the simulator is used | flowchart (TA feedback) | Figure 0 |
| 1 | Calculated parameters for every part in the parameter table | AF, D, FIT estimate and 95% CI, MTTF, 60% FIT next to the published FIT/MTBF/AF; which value is used | Table 0 |
| 2 | Common basis: every candidate at 55 °C | E2–E9, E17, E18 | Table 1, Figure 1 |
| 3 | Supplier comparison within each slot | estimates with 95% CIs side by side; exact test in 9b | Table 2 |
| 4 | System: all 16 combinations | system FIT (estimate, bound scenarios), R, lower bound, meets target | Table 3 |
| 5 | Life distributions | F(mission) per 1,000 vehicles under the exponential, lognormal (σ 0.5, 1.5) and Weibull (β 2.4, 0.8) | Table 4 |
| 6 | Sensitivity, one setting at a time | failures per 1,000 (most / least reliable), target met, warranty and total saving | Table 5 |
| 7 | Temperature sweep 25–150 °C; profile vs its mean | failures per 1,000 (estimate and bound band) | Figure 2, `profile_vs_mean_temperature.csv` |

**Results (2026-11-14):**
- **Calculated parameters (Table 0):** 17 of 19 parts calculated from their own test data. 8 differ
  from the published FIT (RH850 family, LTC6811-1, ADuM141E, ADuM4135) and the calculated value is
  used; the ADI parts' AF was blank in the table and is calculated (77.65). ISL78714 and MAX31730
  cannot be calculated (blank raw value) and stay excluded.
- **Per part at 55 °C (Table 1):** FIT estimates 0.088 (BQ79656, TMP4719) to 11.6 (RH850); C2000
  4.70 (95% CI 0–25.0). Every part meets the target (95% max FIT 0.38–50 vs 343 allowed).
- **Per slot (Table 2):** the TI candidate has the lower estimate in every contested slot, but every
  pair of 95% intervals overlaps (and the exact tests in 9b are not significant).
- **System (Table 3):** all-TI is the most reliable: FIT 6.36 (every part at its bound: 0–33.8),
  95% lower bound on R(2,920 h) 0.99992, meets the target, 0.019 failures per 1,000 vehicles
  (0–0.099). The least reliable (RH850 + LTC6811 + ADuM141E + ADuM4135 + TMP4719 + TMCS1101) has FIT
  13.7 (0.006–72.9) and also meets the target at 55 °C.
- **Temperature (Figure 2):** most reliable system demonstrated up to 90 °C, least reliable up to
  80 °C (5 °C grid; exact values in 9b). On the 40/70/105 °C profile the system FIT is 3.77× its
  value at the 62 °C mean.
- **Life distributions (Table 4):** with the wear-out shapes (σ 0.5, β 2.4) the mission failures fall
  to ~0 because the 2,920 h mission is far shorter than the equivalent test time (78,000 h per
  device at 55 °C), and the ranking flips (the RH850's 150 °C test gives it the longest equivalent
  time). The defect shapes give 0.000015 (lognormal σ 1.5) to 0.036 (Weibull β 0.8) per 1,000 for the
  all-TI system. The exponential is therefore the conservative choice, as SEMATECH (2000, p. 29)
  notes for few or zero failures.
- **Sensitivity (Table 5):** the failure-rate bounds (0 to 0.099 per 1,000, all-TI) and Ea (0.005 at
  0.9 eV to 0.064 at 0.5 eV) move results most; the hot profile is the one setting where the least
  reliable system stops meeting the target. The total saving of the change stays $3,080–3,083 in
  every row.
- **Data caveat (team decision 2026-11-02):** every result is *demonstrated reliability from the
  qualification test data in our table*. RH850 is very likely under-rated; LTC6811-1, ADuM141E and
  ADuM4135 may be optimistic (Section 14). The same caveat heads every key-numbers file
  (`analysis/caveats.py`).

### 9b. Significance and confidence

`analysis/02_significance.py` (statistics in `functions/significance.py` and `functions/planning.py`,
tests in `tests/test_significance.py` and `tests/test_planning.py`) writes `sig_*` tables and
figures and `key_numbers_significance.md`. Course methods only: chi-square bounds, exact Poisson
tests, one-sample t-test and exact proportion CIs.

| # | Test | Result (2026-11-14) |
|---|---|---|
| 1a | Calculated vs published TI FIT, one-sample t-test on log10(calculated / published), 6 families | mean ratio 0.92 (95% CI 0.71–1.20), t = −0.80, p = 0.46: not significantly different |
| 1b | Coverage of the 95% interval, 1,000 known-truth suppliers, exact CIs | central 98.7% (97.8–99.3%), upper bound 99.7%: valid (conservative) in every evidence group |
| 2a | Per part, 95% maximum failure rate and target test (E18, E19); max demonstrated temperature (E20) | all 10 parts demonstrate the target (largest p = 1.2×10⁻⁹); RH850 83 °C, C2000 97 °C, TMCS1101 121 °C, ADuM4135 152 °C, ADuM141E and LTC6811 155 °C, ISO7741 and UCC21750 176 °C, TMP4719 and BQ79656 179 °C |
| 2b | System: sum of 95% bounds vs target; max demonstrated temperature (bisection) | all-TI 27.5 FIT vs 343, demonstrated up to 92 °C; least reliable 59.3 FIT, up to 80 °C |
| 2c | Supplier differences per slot: exact two-rate test (E21) | p = 1.00, 1.00, 0.40, 1.00: no difference significant |
| 2d | 40/70/105 °C profile vs its 62 °C mean | 3.77× at Ea 0.7 eV (2.03× at 0.5 eV, 7.59× at 0.9 eV) |

### 9c. How much data is enough? (TA feedback)

The TA suggested using the simulator to find how much data supplier comparisons need. Course method:
Recitation 12 planning (E27) and the power of the exact test (E28–E29).

| # | Question | Result (2026-11-14) |
|---|---|---|
| 3a | Devices needed (zero failures, 1,000 h) to demonstrate R(2,920 h) ≥ 0.999 at 55 °C | 113 per part tested at 125 °C, 34 at 150 °C; our tests had 231–101,758, so **demonstrating the target needs far less data than we have** |
| 3b | Expected failures in the better supplier's test for 80% power | 65 at a 1.5× true difference, 20 at 2×, 6.7 at 3×, 2.5 at 5×, 0.9 at 10×; at C2000's rate a 2× difference needs 29× the C2000 test's device-hours |
| 3c | Power of our own comparisons | 1% if the alternative were truly 2× worse, 9–13% at 5×, 35–55% at 10× |

**Reading:** the data are sufficient to show every part meets the target (the professor's point) but
not to rank suppliers: zero-failure tests can only separate suppliers whose rates differ by about
10× or more, and a 2× difference needs about 20 failures in each test.

## 10. Warranty exposure, cost and Financial Impacts

**How warranty exposure is calculated** (E12, A14):
1. Each part's failure rate λᵢ at the user's condition comes from the simulator (E4): the estimate
   for the baseline, then its 2.5th and 97.5th percentiles.
2. Expected warranty failures of part i over the warranty t_w for N vehicles: N · (1 − e^(−λᵢ·t_w)).
   Each failure is a replacement of the failed component.
3. Warranty cost = Σᵢ expected replacements of part i × cost of one replacement, which is the part's
   unit price unless a replacement cost is given.
4. Total cost = purchase (N × Σ unit prices) + warranty cost.

**Cost model, built into the simulator** (A14, E12):
- **Defaults:** N = 1,000 vehicles; t_w = the mission hours; C_fail = the part's unit price (the
  failed component is replaced; labour and logistics are not included).
- **Prices:** Sheet2 of `parameter_table.xlsx` (distributor prices with links), cleaned into
  `data/prices.csv`: the candidate's own price if entered, else the Sheet2 price of a matching part
  number, else the Sheet2 average for its slot.

**Financial Impacts analysis** (team decisions 2026-11-02; `analysis/03_financial_impacts.py`,
statistics in `functions/finance.py`, tests in `tests/test_finance.py`, outputs in
`reports/financial_impacts/`). Report writing happens outside the repo.
- **Change evaluated:** BEFORE = the least reliable combination of our library candidates
  (RH850 + LTC6811-1 + ADuM141E + TMP4719 + ADuM4135 + TMCS1101); AFTER = the simulator's
  recommended, most reliable combination (all TI).
- **Cost:** per 1,000 vehicles; purchase at Sheet2 prices (A15); warranty = expected replacements over
  2,920 h × the component's unit price (team decision); total = purchase + warranty.
- **Conditions:** 55 °C and the 40/70/105 °C profile (the hot case).
- **Uncertainty (professor's feedback):** baseline at the failure-rate estimates, rerun with every part
  at its 2.5th and at its 97.5th percentile. No figure (none required).
- **Engineering evaluation time:** dropped (team decision 2026-11-02). It needs a measured
  reduction in evaluation time; the charter's 20% is a target, not a result, and no published study
  gives hours per supplier-reliability evaluation (searched: the only peer-reviewed figure, Robinson
  2010, JASIST 61(4), is 55.75% of engineers' time on all information work). $74.66/h is verified
  (NHTSA, Federal Register, 14 Feb 2025, docket NHTSA-2025-0004: BLS May 2023 engineer wage in motor
  vehicle manufacturing $52.56 ÷ 0.704) and kept for when a reduction can be measured.

**Results (2026-11-14, per 1,000 vehicles, 2,920 h):**

| Quantity | 55 °C: baseline (2.5th / 97.5th percentile) | 40/70/105 °C profile |
|---|---|---|
| Purchase saving | $3,080 (fixed prices) | $3,080 |
| Replacements, before → after | 0.040 → 0.019 (0 → 0; 0.213 → 0.099) | 0.252 → 0.117 (0 → 0; 1.344 → 0.624) |
| Warranty saving | $0.45 ($0.00; $2.40) | $2.85 ($0.00; $15.16) |
| Total saving | $3,080 ($3,080; $3,082) | $3,083 ($3,080; $3,095) |

- **Replacements** halve at every setting, but the absolute numbers are tiny, so the warranty saving is
  negligible next to purchase prices: almost all of the financial difference is the purchase price,
  which depends on the MCU family-proxy prices (A15).
- **Caveat:** the BEFORE combination is least reliable *by the evidence in our table*, which
  under-rates the RH850 and may over-rate the ADI parts (Section 9, Section 14).
- **Reading:** with Sheet2 prices the recommended suppliers are both more reliable and cheaper.

## 11. Evaluating the simulator

There are two questions here:
- **Verification:** did we code the equations correctly? (11a)
- **Validation:** do the results match reality? (11b, 11e)

### 11a. Verification tests (`tests/`)

Status: **all 127 pass** (`.venv/Scripts/python -m pytest`). Each statistic has a known answer and a
degenerate case.

| Check | Expected | Test(s) |
|---|---|---|
| E2: AF(55 °C, test at 125 °C, 0.7 eV); T = T_test | 77.65 (the table's 77.6454); AF = 1 | `test_equations::test_af_*` |
| E4 known answer: TI C2000, n = 1900, T = 1000, 125 → 55 °C, 60%, r = 0 | 6.21 FIT (TI publishes 6.19) | `test_lambda_known_answer_ti_c2000`, `test_upper_percentile_equals_supplier_bound` |
| E4: Recitation 12 Examples 1, 2, 6, 7, 8 and Table 3.7 | k = 0.6108/1.5444, 1.4531, 0.6953/1.3966; 41.2–584.5 FIT; 433.2, 752.5, 1,872.3 FIT; k0 table | `test_k_factors_*`, `test_ci_recitation_example_7`, `test_zero_failures_recitation_example_8`, `test_zero_failure_factors_table_3_7` |
| E4 degenerate: r = 0 lower bound; 10× the evidence | 0; every value 10× lower | `test_zero_failure_lower_bound_is_zero`, `test_estimate_and_bounds_ordered_and_scale_with_evidence` |
| E6 | one-bin profile = single temperature; 12.3 vs 46.3; = Tencer T_aa | `test_effective_af_*` |
| E7–E10 | R(MTTF) = e⁻¹; system FIT = sum; R_sys(B0.1) = 0.999; WR = 1 at B0.1 | `test_reliability::*` |
| select() | known answer at T_op = T_test; bounds flip for R/MTTF/B0.1; system = sum of parts in every case; target ⇔ E19 | `test_candidates::*` |
| E12, E22–E23 | costs per case; saving known answer; break-even known and degenerate | `test_finance::*` |
| E24–E26 | course formula for the exponential; Weibull β = 1 = exponential; every model passes through the test point | `test_life_models::*` |
| E27–E29 | Recitation 12 Examples 9, 10, 12, 13; power = direct enumeration; equal rates ≤ α | `test_planning::*` |
| 11b, 11e | TI reproduced, AF matches the table, mismatches flagged; coverage ≥ 94% / 97% | `test_validation::*` |

### 11b. Real result 1: the parameter table's published FIT, MTBF and AF ✅

- **Team decision (2026-10-31):** the published values are used to **validate** the calculation.
  They are **not model inputs**, so the check is independent.
- **Method** (`validation.supplier_check()`, Table 0, 9b test 1a): for every usable part, calculate
  the supplier convention (the chi-square 60% bound at the published reference temperature, Ea 0.7 eV)
  and compare it with the published FIT; MTBF = 1e9 / calculated FIT; AF at 0.7 eV against the table.
- **Result:**

| Family | Published FIT | Calculated at 60% | Ratio | Verdict |
|---|---|---|---|---|
| TI C2000 | 6.19 | 6.21 | 1.00 | reproduced |
| TI TMCS1101 | 1.7 | 1.69 | 1.00 | reproduced |
| TI BQ79656, TMP4719 | 0.1 | 0.116 | 1.16 | reproduced (TI rounds to 0.1) |
| TI ISO7741, UCC21750 | 0.2 | 0.135 | 0.68 | reproduced within 2× (rounded) |
| Renesas RH850 | 0.0011 | 15.3 | 13,900 | calculated higher: Renesas uses more data (verified) |
| ADI LTC6811-1 | 33.95 | 0.32 | 0.009 | calculated lower: ADI's basis differs (verified) |
| ADI ADuM141E | 20.23 | 0.45 | 0.022 | calculated lower: basis unknown |
| ADI ADuM4135 | 11.28 | 0.37 | 0.033 | calculated lower: 11.28 not found in ADI's report |

  - **AF:** the calculated AF equals the table's AF wherever the table gives one (77.6454; 259.18 for
    the RH850); the ADI rows had no AF and use the calculated 77.65.
  - **MTBF:** matches TI's published MTBF; the table's MTBF and FIT disagree with each other for
    BQ79656/TMP4719 (rounding) and LTC6811-1 (MTBF 6.07×10⁹ h ⇔ 0.16 FIT, not 33.95).
  - **Conclusion:** every published value that rests on the same test data as our table is reproduced;
    the ones that are not rest on different data (Section 14). The calculated values are used.

### 11c–11d. Handbooks and field evidence `[DROPPED]`

Dropped by team decision (2026-10-31): the team will not supply handbook or field data, and public
per-part handbook figures are incomplete (TI's C2000 FMEDA rates are under NDA). A8 (only thermal
mechanisms) means the simulator is expected to under-predict field failure rates; this is stated as
a limitation.

### 11e. Known-truth coverage study ✅

1. Invent 1,000 synthetic "suppliers", each with a true FIT (log-uniform 0.01–100 FIT at 55 °C).
2. Generate an HTOL result for each by Poisson-sampling failures from realistic n (231–101,758),
   T = 1,000 h and T_test 125 or 150 °C (Ea 0.7 eV in truth and estimate).
3. Compute the 95% interval exactly as `select()` does (E4).
4. Count how often it contains the truth.

**Result (seed 11):** central interval 98.7% overall (99.7%, 99.6%, 99.2%, 95.9% by expected failures
< 0.1, 0.1–1, 1–10, > 10); upper bound 99.7%. The chi-square interval is valid and conservative
everywhere. **Why the zero-failure lower bound must be 0:** reading the zero-failure formula at the
2.5th percentile instead (−ln(0.975)/D, positive) gave only **81%** coverage in this study (2,000
suppliers), because a very reliable part with zero failures can have a true rate below any positive
bound.

## 12. Code architecture

```
functions/                 the simulator (plain functions, all tested)
  arrhenius.py      kelvin(), accel_factor(), effective_af()                          E1, E2, E6, A2
  evidence.py       device_hours(), lambda_hat(), lambda_percentile(), lambda_ci(),
                    lambda_bound(), k_factor(), fit(), mttf_hours()                    E3–E5, A5
  reliability.py    reliability(), unreliability(), density(), hazard(), series_lambda(),
                    b_life(), warranty_ratio(), DEFAULT_WARRANTY_HOURS                 E7–E10, A7
  candidates.py     select(candidates, profile, mission_hours, ...)  THE SIMULATOR   E12, E15, E17, A11–A14
                    price_for(), load_prices(), library_candidate()
  interface.py      parse_profile(), read_candidates(), summary_text(), key_table(), detail tables
  library.py        load_library(), get_part()                                        component library
  life_models.py    fraction_failed(), scale(), unreliability(), mission_unreliability() E24–E26, A16
  planning.py       unit_hours_needed(), sample_size(), required_test_time(),
                    two_rate_power(), failures_for_power()                            E27–E29
  significance.py   max_failure_rate(), target_test(), max_demonstrated_temp(), two_rate_test(),
                    one_sample_t(), proportion_ci()                                   E18–E21, 9b
  validation.py     supplier_check(), coverage_study()                                11b, 11e
  finance.py        combination_costs(), compare_costs(), break_even_replacement_cost()  E12, E22–E23
code/
  01_clean_data.py       raw xlsx → data/components.csv, data/prices.csv, data/reference/published_fit.csv
  02_run_simulator.py    the program users run: asks for temperature, mission hours and candidates
                         (or --temp --hours --candidates file.csv); prints SUMMARY → key table →
                         details; saves CSVs to results/tables/runs/ (git-ignored)
analysis/                  report analyses, kept apart from the simulator (they only call functions/)
  common.py                   shared baseline, candidates and prices
  01_preliminary_results.py   Section 9 → reports/preliminary_results/
  02_significance.py          Sections 9b, 9c → reports/preliminary_results/ (sig_*)
  03_financial_impacts.py     Section 10 → reports/financial_impacts/
  plots.py                    every report figure (and the flowchart), drawn with plotnine
reports/preliminary_results/  tables/, figures/, key_numbers.md, key_numbers_significance.md
reports/financial_impacts/    tables/, key_numbers_financial.md
data/
  components.csv, prices.csv, codebook.md, examples/candidates_example.csv, reference/, raw/
tests/
  test_library, test_equations (E1–E6), test_reliability (E7–E10), test_candidates (the simulator),
  test_interface, test_validation (11b, 11e), test_significance (E18–E21), test_life_models
  (E24–E26), test_planning (E27–E29), test_finance (E22–E23), test_analysis
```

- A candidate is a plain dict (or a row of a candidates CSV): slot, name, test temperature, and
  either test hours + sample size + failures or a FIT / MTTF (see `data/codebook.md`).
- A profile is one temperature or a list of (temperature °C, fraction), e.g. `[(40, 0.5), (70, 0.5)]`.
- `select()` returns tables and does no plotting or printing; a later web front end would call it
  directly.

## 13. Build order

Each milestone ended with its tests passing and this file updated.

| # | Milestone | Status |
|---|---|---|
| M1 | Component library from `parameter_table.xlsx` | ✅ 19 parts, 17 usable |
| M2–M6 | Equations, Monte Carlo engine, verification and validation (v1–v3) | ✅ superseded by M8 (tag `v1-gamma-model`) |
| M6b–c | The user-facing simulator: `select()`, `code/02_run_simulator.py`, Sheet2 costs | ✅ |
| M7a–c | Preliminary Results, significance, Financial Impacts (v3) | ✅ |
| M8 | Method v4 after the instructors' feedback: course exponential estimate and CIs, calculated parameter table, lognormal/Weibull, single sensitivity table, cost reruns at the 2.5th/97.5th percentiles, data thresholds, flowchart | ✅ 2026-11-14 |
| — | Report writing (.docx) | done by the team outside the repo |
| — | Web front end over `select()`; quantity per slot | `[LATER]` |

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
- Sheet2 lists no individual current-sensor prices, only a stated average (17.35 USD over 6
  products); the simulator uses that average (A14).

**Effect on results (team decision 2026-11-02: keep these parts, label the results).** RH850 is
likely under-rated (one 231-device test vs Renesas's larger verified basis); LTC6811-1, ADuM141E and
ADuM4135 may be over-rated (our FIT lower than ADI's). They stay in the library because removing them
would leave one candidate per slot and no comparison; every report states the caveat. Two fixes are
open: re-run with their published FITs as report-summary inputs (E15) as a sensitivity, or transcribe
the full test data from the Renesas and ADI reports.

**Calculated values are used** (team decision 2026-11-14). Wherever a parameter is missing (the ADI
rows' AF) or a published value does not match the test data (RH850, LTC6811-1, ADuM141E, ADuM4135),
it is calculated from the part's own test data and the calculated value is used: Table 0
(`reports/preliminary_results/tables/table0_calculated_parameters.csv`). Raw blanks that the
calculation itself needs (ISL78714 failures, MAX31730 sample size) cannot be calculated and stay
excluded.

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
| 2026-11-01 | v3 roadmap: rewritten to match the current design (v2 saved in `docs/roadmap_history/ROADMAP_v2_2026-11-01.md`). Sections 2, 3, 8, 10, 12, 13 rewritten: one user-facing simulator (`select()`), the library and `evaluate()`/`compare()` as the build-and-test base, cost model (Section 10, formerly Financial model), current code layout and milestones; Section 9 renamed Preliminary Results with 9b nested; 11c–11d merged as dropped; 'Mode' wording removed from assumptions and equations (numbers unchanged). Code comments, CLAUDE.md and the codebook updated to match. No numbers changed. |
| 2026-11-02 | M7b Financial Impacts. Team decisions: evaluate the supplier change (least reliable → recommended); 55 °C plus the 40/70/105 °C profile; parts-only repair cost; per 1,000 vehicles; drop the engineering-time benefit until a reduction can be measured (charter's 20% is a target; no published hours per evaluation). New `functions/finance.py` (E22 saving, E23 break-even repair cost, `qi_cost`) with 6 tests; `analysis/03_financial_impacts.py` (4 tables, 3 plotnine figures, `key_numbers_financial.md`); A15 (library prices incl. MCU family proxies) with an equal-MCU-price sensitivity. Results: saving $3,080 per 1,000 vehicles with Sheet2 prices; −$4,980 with equal MCU prices, break-even repair cost $148k (55 °C) / $23k (profile). $74.66/h verified on govinfo.gov. 141 tests pass. |
| 2026-11-02 | Team decision: keep RH850, LTC6811-1, ADuM141E and ADuM4135 in the library and label every result as demonstrated reliability from our table's test data (RH850 likely under-rated, ADI parts possibly over-rated). New `analysis/caveats.py`; the caveat heads all three key-numbers files; Sections 9, 10 and 14 updated. Numbers unchanged. |
| 2026-11-02 | Sources added for A2 (Ea 0.5–0.9 eV: SEMATECH 2000 failure-models report; Vigrass, Intersil/Renesas note, 0.7 eV default) and A7 (1 h/day: AAA Foundation American Driving Survey 2024, 60.4 min/day); both `[TODO]` tags removed. No numbers changed. |
| 2026-11-02 | Warranty exposure calculation written out step by step (E12, Section 10, code comments in `candidates.py` and `finance.py`, and `key_numbers_financial.md`). Calculation and numbers unchanged. |
| 2026-11-02 | Financial Impacts finalized (team decision): "repair" renamed "replacement" everywhere (`replacement_cost`, `--replacement-cost`); the equal-MCU-price sensitivity, the break-even output and all three financial figures dropped (no figure required); every reported number has median, SE and 95% CI. Tables now fin_1 to fin_3. Calculation and main-case numbers unchanged. |
| 2026-11-14 | **v4, after the instructors' feedback** (TA and professor, 2026-11-14; v3 saved as `docs/roadmap_history/ROADMAP_v3_2026-11-14.md` and git tag `v1-gamma-model`). Failure rate now the course's exponential estimate and chi-square CI (E4, A5): λ̂ = r/D (0.693/D at r = 0), lower bound 0 at r = 0 (a positive one covered the truth only 81% of the time); Monte Carlo draws, priors, P(best), P(outlasts) and calibration removed (`functions/simulator.py`, `code/03_validation.py` deleted). One baseline (55 °C, 2,920 h, Ea 0.7 eV, exponential); new single sensitivity table (Table 5) with the 2.5th/97.5th percentile reruns, Ea 0.5/0.9, temperature, profile, mission and the lognormal/Weibull alternatives (A16, E24–E26, `functions/life_models.py`). New Table 0 of calculated parameters (calculated values used). New Section 9c, data thresholds (E27–E29, `functions/planning.py`, Recitation 12 planning). New Figure 0 flowchart. Financial Impacts rerun at the bounds. Every Recitation 12 worked example is a test. Results: all parts meet the target; all-TI FIT 6.36; no supplier difference significant; 2× differences need ~20 failures per test; total saving $3,080. 127 tests pass. |
| 2026-11-15 | Simulator inputs (team decisions, step by step with the user): (1) **Ea option**: 0.7 eV, or a 0.5–0.9 eV range propagated by a Monte Carlo over Ea only (A2), shared or separate per part, with Ea and full-range columns and a target check at the unfavourable Ea; (2) **test groups**: a part may have several HTOL groups, D and r summed over them (E3; CSV rows with the same name, or asked interactively); (3) **temperature band** min–max replaces typed-in profiles (A3, E6), with the worst case at T_max. New `tests/test_new_inputs.py`; 137 tests pass. Reports not regenerated (they are written later). |
| 2026-11-16 | Simulator output (team decision): the summary shows only the three best combinations (most reliable by λ̂, safest by the 95% maximum rate, cheapest among those meeting the target) and the best part per slot, led by FIT with its 2.5th/97.5th percentile and failures per 1,000; R(mission), MTTF and B0.1 moved to --details and the CSVs; the full combination list is only saved to CSV. `select()` gains `picks` (`pick_combinations()`) and lists every combination by default. 137 tests pass. |
| 2026-11-16 | Output tidy-up after testing with made-up inputs (13 of 13 hand checks exact): numbers print readably (1,382, not 1.38e+03); a part whose report states its Ea shows "fixed (report Ea … eV)" in the Ea-range column; the details add each part's 60% upper bound FIT (`fit_upper_60`, the supplier convention, which reproduces a published FIT or MTTF input exactly), to be discussed in the reports. 140 tests pass. |
