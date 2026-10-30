# CLAUDE.md - TASER-EV

SYSEN 5300 (Cornell, Fall 2026) Six Sigma project. Team: Alpomer Tolga Aksit, Luis Luna,
Janset Erdenbil. See [`README.md`](README.md) for the folder layout and setup.

**Read [`ROADMAP.md`](ROADMAP.md) first, every session.** It is the single source of truth for the
approach, assumptions (A#), equations (E#), validation tests, build order and data issues.
Every commit that changes the method, an assumption, a number or the code structure must also
update ROADMAP.md and add a line to its Changelog. Cite A#/E# numbers in code comments.

## What we are building

A Monte Carlo accelerated-life reliability simulator for six EV electronic component slots: ECU
MCU, BMS AFE, digital isolator, temperature sensor, gate driver and current sensor. The library
of supplier HTOL test data comes from `parameter_table.xlsx`. The user gives an operating
temperature (or a profile) and fills 1–6 slots.
- **Mode 1, `evaluate()`:** component and system FIT, MTTF, R(t), B0.1, warranty ratio and
  P(meets warranty), with 95% CIs.
- **Mode 2, `compare()`:** two configurations, their differences and P(B outlasts A).

The simulator is validated against supplier, handbook and field results (ROADMAP Section 11).

Code and results come first. A user interface comes later and must call the same functions.

## Method (state it this way in code comments and reports)

1. Arrhenius AF = exp[(Ea/k)(1/T_use - 1/T_test)], with T in Kelvin and k = 8.617333e-5 eV/K.
2. Failure rate as a distribution: lambda ~ Gamma(f+1, rate = n * t_test * AF). Its 60th percentile
   is the supplier chi-square bound chi2.ppf(CL, 2f+2) / (2 * n * t_test * AF); FIT = lambda * 1e9.
   Recompute from raw test data; the published FIT is only used for validation.
3. Dynamic AF over a thermal profile: average the failure rates, not the AFs or temperatures:
   lambda_use = lambda_test * sum(w_i / AF_i). This is the Arrhenius average temperature of
   Tencer et al. (2004). Ea is drawn from triangular(0.5, 0.7, 0.9) eV.
4. Constant hazard (exponential): R(t) = exp(-lambda t).
5. Series system: lambda_sys = sum(qty_i * lambda_i); B0.1 = -ln(0.999) / lambda_sys.
6. Uncertainty and financial confidence intervals: parametric Monte Carlo (5,000 draws, common random
   numbers for A vs B), following the course's `qi()` pattern in `timothyfraser/sysen`
   code/ZZ_financial_analysis.py.

## Rules

- **Python only**, in `.venv` (`.venv/Scripts/python`). Write plain functions in `functions/` and
  numbered scripts in `code/`.
- **Every statistic gets a test in `tests/`** with a known answer and a degenerate case before it
  is used in results. Known answer: TI C2000 F280049, n=1900, t=1000 h, 125 to 55 C, Ea=0.7,
  CL=60%, f=0 gives 6.21 FIT (TI publishes 6.19).
  Load the `stats-first-steering` skill before writing analysis code. Use `glossary` for course
  terminology.
- **Never edit `data/raw/`.** Cleaning code writes to `data/`, and a codebook documents every column.
- Never invent data and present it as real. Assumed values (thermal profile, quantity per vehicle,
  warranty hours, cost per failure) are labelled as assumptions, with a source where one exists.
- Course material (`timothyfraser/sysen`) may be used and cited. Never add its author as a
  contributor or co-author.
- Stage explicit paths (`git add <files>`, never `-A` or `.`). Commit or push only when asked.

## Known data issues in parameter_table.xlsx

- TI rows reproduce their published FIT from the test data.
- These rows don't match their own test data and need their source reports rechecked:

  | Part | Published FIT | FIT from test data |
  |---|---|---|
  | Renesas RH850 | 0.0011 | ~15.3 |
  | ADI LTC6811 | 33.95 | ~0.32 |
  | ADI ADuM4135 (typed "ASUM4135") | 11.28 | ~0.37 |
  | Renesas ISL78714 | 3.72 | ~3.06 |

- MAX31730 has no sample size, and its use temperature is 25 C.
- The current sensor has only one supplier (TI).
- "Mission time 120000 hours" may really mean 120,000 miles; confirm with the team.

## Current deliverable

Preliminary Results (measures, assumptions, model, results with confidence intervals, table/figure)
plus Financial Impacts: 300-500 words with cited costs, a before/after cost comparison and
confidence intervals. Both are submitted as .docx in `reports/`.
