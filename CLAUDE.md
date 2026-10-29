# CLAUDE.md - TASER-EV

SYSEN 5300 (Cornell, Fall 2026) Six Sigma project. Team: Alpomer Tolga Aksit, Luis Luna,
Janset Erdenbil. See [`README.md`](README.md) for the folder layout and setup.

## What we are building

An accelerated-life reliability simulator for six EV electronic components: ECU MCU, BMS AFE,
digital isolator, temperature sensor, gate driver and current sensor. It takes each
supplier's published HTOL test data and puts every part on a common basis under user-defined
thermal conditions. It reports component FIT/MTTF, series-system reliability, B0.1 life, the
ratio of B0.1 to the warranty period, and the % change in B0.1 when suppliers are swapped.

Code and results come first. A user interface comes later and must call the same functions.

## Method (state it this way in code comments and reports)

1. Arrhenius AF = exp[(Ea/k)(1/T_use - 1/T_test)], with T in Kelvin and k = 8.617333e-5 eV/K.
2. Upper-bound failure rate: lambda = chi2.ppf(CL, 2f+2) / (2 * n * t_test * AF); FIT = lambda * 1e9.
   Recompute from raw test data; the published FIT is only a cross-check.
3. Thermal profile: average the failure rates, not the AFs: lambda_use = lambda_test * sum(w_i / AF_i).
   This is the Arrhenius average temperature of Tencer et al. (2004).
4. Constant hazard (exponential): R(t) = exp(-lambda t).
5. Series system: lambda_sys = sum(qty_i * lambda_i); B0.1 = -ln(0.999) / lambda_sys.
6. Uncertainty and financial confidence intervals: bootstrap or Monte Carlo, following the course's
   `qi()` pattern in `timothyfraser/sysen` code/ZZ_financial_analysis.py.

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
