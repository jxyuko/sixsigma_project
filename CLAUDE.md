# CLAUDE.md - TASER-EV

SYSEN 5300 (Cornell, Fall 2026) Six Sigma project. Team: Alpomer Tolga Aksit, Luis Luna,
Janset Erdenbil. See [`README.md`](README.md) for the folder layout and setup.

**Read [`ROADMAP.md`](ROADMAP.md) first, every session.** It is the single source of truth for the
approach, assumptions (A#), equations (E#), validation tests, build order and data issues.
Every commit that changes the method, an assumption, a number or the code structure must also
update ROADMAP.md and add a line to its Changelog. Cite A#/E# numbers in code comments.

## What we are building

An accelerated-life reliability simulator for a vehicle maker choosing between
suppliers, for six EV electronic component slots: ECU MCU, BMS AFE, digital isolator, temperature
sensor, gate driver and current sensor.
- **The simulator, `select()`** (the only thing users see): the user enters candidates for any
  slots (from each report's raw HTOL data or its FIT/MTTF), their operating temperature and mission
  hours. Output: summary first, then per-candidate and per-combination reliability with 95% CIs,
  the target check (confidence fixed at 95%), ranking, and warranty exposure and total cost per
  1,000 vehicles with Sheet2 prices (A14).
- **Library** (`parameter_table.xlsx` → `data/components.csv`): used to build and test the
  simulator, not offered to users. `evaluate()` / `compare()` are the internal validation engine.

The simulator is validated against the published FIT, MTBF and AF in the parameter table (used only
for validation, never as inputs) and a known-truth coverage study (ROADMAP Section 11).

Run it: `.venv/Scripts/python code/02_run_simulator.py` asks for everything, or
`--temp 200 --hours 1000 --candidates data/examples/candidates_example.csv [--details]`.

A web front end is possible later; it must call the same `select()`.

## Method (state it this way in code comments and reports)

1. Arrhenius AF = exp[(Ea/k)(1/T_use - 1/T_test)], with T in Kelvin and k = 8.617333e-5 eV/K.
2. Failure rate from the test, the course exponential method (Recitation 12, v4 after the
   instructors' feedback): estimate r / D with D = n * t_test * AF, or -ln(0.5) / D when r = 0;
   95% CI from the chi-square k-factors: upper chi2.ppf(0.975, 2r+2) / (2D), lower
   chi2.ppf(0.025, 2r) / (2D), which is 0 when r = 0. The 60% upper bound is the supplier bound;
   FIT = lambda * 1e9. Always compute from raw test data; calculated values replace missing or
   mismatched published ones (Table 0); published FITs are stored for reference, not used.
   No Gamma, prior or posterior wording (outside the course).
3. Dynamic AF over a thermal profile: average the failure rates, not the AFs or temperatures:
   lambda_use = lambda_test * sum(w_i / AF_i). This is the Arrhenius average temperature of
   Tencer et al. (2004). Ea is 0.7 eV; 0.5 and 0.9 eV are sensitivity rows.
4. Constant hazard (exponential): R(t) = exp(-lambda t).
5. Series system: lambda_sys = sum(qty_i * lambda_i); B0.1 = -ln(0.999) / lambda_sys.
6. Uncertainty: one baseline setting (55 C, 2,920 h, Ea 0.7 eV, exponential, the estimate); every
   output also at the 2.5th and 97.5th percentile failure rates; every other change is a row of one
   sensitivity table (Table 5), including lognormal and Weibull with SEMATECH (2000) shapes (A16).
7. Requirement: a part or system meets the target if its 95% lower bound on R(mission) >= target;
   the course chi-square form is the maximum failure rate chi2.ppf(0.95, 2f+2) / (2 D).

## Rules

- **Python only**, in `.venv` (`.venv/Scripts/python`). Write plain functions in `functions/` and
  numbered scripts in `code/`; report analyses go in `analysis/` (they only call `functions/`).
- **Figures use plotnine** (ggplot grammar), all in `analysis/plots.py`, so the team can run them in
  Posit Cloud.
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
  stored in `data/reference/published_fit.csv`; they are used only to validate the simulator,
  never as inputs (team decisions 2026-10-30 and 2026-10-31). Never overwrite a published value.
- TI rows reproduce. RH850 and LTC6811 are verified manufacturer values on a larger basis than our
  test data. ADuM4135's 11.28 is not verified.
- ISL78714 (failures blank) and MAX31730 (sample size blank) are excluded from simulation until
  their reports are checked.
- Never fill a blank raw value with a guess.

## Current status

Method v4 (2026-11-14, after the instructors' feedback; v3 is git tag `v1-gamma-model`). The simulator,
the Preliminary Results and the Financial Impacts numbers are done:
`reports/preliminary_results/` and `reports/financial_impacts/` (tables, plotnine figures, key-numbers
files), regenerated by `analysis/01_preliminary_results.py`, `02_significance.py` and
`03_financial_impacts.py`. The .docx reports are written by the team outside the repo; do not add
them here.
