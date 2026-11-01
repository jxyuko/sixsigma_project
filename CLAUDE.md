# CLAUDE.md - TASER-EV

SYSEN 5300 (Cornell, Fall 2026) Six Sigma project. Team: Alpomer Tolga Aksit, Luis Luna,
Janset Erdenbil. See [`README.md`](README.md) for the folder layout and setup.

**Read [`ROADMAP.md`](ROADMAP.md) first, every session.** It is the single source of truth for the
approach, assumptions (A#), equations (E#), validation tests, build order and data issues.
Every commit that changes the method, an assumption, a number or the code structure must also
update ROADMAP.md and add a line to its Changelog. Cite A#/E# numbers in code comments.

## What we are building

A Monte Carlo accelerated-life reliability simulator for a vehicle maker choosing between
suppliers, for six EV electronic component slots: ECU MCU, BMS AFE, digital isolator, temperature
sensor, gate driver and current sensor.
- **The simulator, `select()`** (the only thing users see): the user enters candidates for any
  slots (from each report's raw HTOL data or its FIT/MTTF), their operating temperature and mission
  hours. Output: summary first, then per-candidate and per-combination reliability with 95% CIs,
  the target check (confidence fixed at 95%), P(best), and warranty exposure and total cost per
  1,000 vehicles with Sheet2 prices (A14).
- **Library** (`parameter_table.xlsx` → `data/components.csv`): used to build and test the
  simulator, not offered to users. `evaluate()` / `compare()` are the internal validation engine.

The simulator is validated against the published FIT, MTBF and AF in the parameter table (used only
for validation, never as inputs) and a known-truth coverage study (ROADMAP Section 11).

Run it: `.venv/Scripts/python code/02_run_simulator.py` asks for everything, or
`--temp 200 --hours 1000 --candidates data/examples/candidates_example.csv [--details]`.

Code and results come first. A user interface comes later and must call the same functions.

## Method (state it this way in code comments and reports)

1. Arrhenius AF = exp[(Ea/k)(1/T_use - 1/T_test)], with T in Kelvin and k = 8.617333e-5 eV/K.
2. Failure rate as a distribution: lambda ~ Gamma(f+1, rate = n * t_test * AF). Its 60th percentile
   is the supplier chi-square bound chi2.ppf(CL, 2f+2) / (2 * n * t_test * AF); FIT = lambda * 1e9.
   Always compute from raw test data; published FITs are stored for reference, not used.
3. Dynamic AF over a thermal profile: average the failure rates, not the AFs or temperatures:
   lambda_use = lambda_test * sum(w_i / AF_i). This is the Arrhenius average temperature of
   Tencer et al. (2004). Ea is drawn from triangular(0.5, 0.7, 0.9) eV.
4. Constant hazard (exponential): R(t) = exp(-lambda t).
5. Series system: lambda_sys = sum(qty_i * lambda_i); B0.1 = -ln(0.999) / lambda_sys.
6. Uncertainty and financial confidence intervals: parametric Monte Carlo (5,000 draws, common random
   numbers for A vs B), following the course's `qi()` pattern in the class financial-analysis
   example.

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
- Course material may be used for ideas. Never name its author in the repo, and never add them as
  a contributor or co-author.
- Stage explicit paths (`git add <files>`, never `-A` or `.`). Commit or push only when asked.

## Known data issues in parameter_table.xlsx

The current list is in ROADMAP Section 14, and each part's notes are in the `flag` column of
`data/components.csv` (see `data/codebook.md`). In short:
- The raw table mixes manufacturer-reported FITs with FITs calculable from the test data.
  **The model uses test data only.** Published FITs, their verification and our calculated FIT are
  stored in `data/reference/published_fit.csv` and are not used (team decision 2026-10-30). Never
  overwrite a published value.
- TI rows reproduce. RH850 and LTC6811 are verified manufacturer values on a larger basis than our
  test data. ADuM4135's 11.28 is not verified.
- ISL78714 (failures blank) and MAX31730 (sample size blank) are excluded from simulation until
  their reports are checked.
- Never fill a blank raw value with a guess.

## Current deliverable

Preliminary Results (measures, assumptions, model, results with confidence intervals, table/figure)
plus Financial Impacts: 300-500 words with cited costs, a before/after cost comparison and
confidence intervals. Both are submitted as .docx in `reports/`.
