# TASER-EV

**Thermal Acceleration-based Simulation and Evaluation of Reliability for EV Electronics**
SYSEN 5300 Six Sigma project - Alpomer Tolga Aksit, Luis Luna, Janset Erdenbil.

## What it does

A vehicle maker choosing between suppliers gets reliability reports that were tested at
different temperatures, for different times, on different numbers of chips, so they can't be
compared directly. TASER-EV puts every candidate on **one common basis: the user's own
operating temperature**, and says which supplier is more reliable, whether the part meets the
user's reliability target, and how sure we can be.

It covers six EV electronic components: ECU MCU, BMS AFE, digital isolator, temperature
sensor, gate driver and current sensor.

## How it works

For each candidate part, the simulator:

1. **Reads the test evidence** from the supplier's report: test temperature, hours, sample size and
   failures (or a published FIT / MTTF, which it turns back into test evidence).
2. **Moves it to the user's temperature** with the Arrhenius acceleration factor
   AF = exp[(Ea/k)(1/T_use − 1/T_test)]. This works in both directions: cooler than the test
   gives AF > 1, hotter gives AF < 1. A temperature profile averages the failure rates over time.
3. **Estimates the failure rate from the test** with the course's exponential method: estimate
   r / D (0.693 / D with zero failures), where D = devices × hours × AF, and a 95% confidence
   interval from the chi-square k-factors (Recitation 12). Ea is 0.7 eV, the value every report uses.
4. **Builds the system** as parts in series: system failure rate = sum of the part rates.
5. **Reports one baseline** (the estimates) and reruns everything with every part at its 2.5th and
   97.5th percentile failure rate.

Constant failure rate (exponential life) is the baseline; lognormal and Weibull alternatives, Ea,
temperature and mission are rows of one sensitivity table. Only thermal failure mechanisms are
modelled. Figure 0 (`reports/preliminary_results/figures/figure0_flowchart.png`) shows how it is
used. Every assumption (A1–A16) and equation (E1–E29) is in [`ROADMAP.md`](ROADMAP.md).

## What it computes

**Inputs:**
- **Required:** operating temperature (or a band), and the candidates for any slots.
- **Optional, with defaults:** mission hours (2,920 h = 8-year EV battery warranty × 1 h/day), parts per
  vehicle for each candidate (1), target reliability (0.999), fleet size (1,000), cost of one warranty
  replacement (default: the part's unit price), unit price (default: the slot's Sheet2 average).

**Outputs:**

| For | Outputs (estimate with 95% CI) |
|---|---|
| Each candidate | AF, FIT, MTTF, B0.1 life, reliability over the mission R(t), the 95% maximum failure rate and lower bound on R, whether the target is met, rank in its slot |
| Each system combination | system FIT, R(t), B0.1, target check, rank |
| Warranty exposure | expected failures, warranty cost and total cost (purchase + warranty) per 1,000 vehicles, using Sheet2 prices |

The output starts with a **plain-language summary**: the best candidate per slot, the most
reliable system, and the lowest-cost system.

## How to use it

```bash
.venv/Scripts/python code/02_run_simulator.py
```
asks for everything step by step. Or give a file of candidates (template:
[`data/examples/candidates_example.csv`](data/examples/candidates_example.csv)):
```bash
.venv/Scripts/python code/02_run_simulator.py --temp 55 --hours 2920 --candidates data/examples/candidates_example.csv
```
Add `--details` for the full tables. Results are also saved as CSV in `results/tables/runs/`.

## How we know it is right

- **Verified:** 135 tests with known answers. For example, TI C2000 (1,900 chips, 1,000 h, 125 °C,
  0 failures) gives 6.21 FIT at 55 °C; TI publishes 6.19.
- **Agrees with the course chi-square formula** within 0.65%.
- **Matches published TI values:** mean ratio 0.91 (95% CI 0.70–1.20), t-test p = 0.42.
- **Honest intervals:** in a known-truth study, the 95% upper bound contained the true failure rate
  99.8% of the time.

Details: [`reports/preliminary_results/key_numbers_significance.md`](reports/preliminary_results/key_numbers_significance.md).

## Data

The library of supplier test data comes from the team's `data/raw/parameter_table.xlsx`, cleaned into
`data/components.csv` (19 parts, 17 usable) and documented in [`data/codebook.md`](data/codebook.md).
It is used to build and test the simulator, not offered to users. Published FIT values are used only
to validate it, never as inputs. Unit prices come from Sheet2 (`data/prices.csv`).

## Layout

```
data/raw/         source data as collected (parameter_table.xlsx) - never edited by code
data/             cleaned inputs (components.csv, prices.csv), codebook, examples/
functions/        the simulator: equations, life models, planning, statistics (all tested)
code/             01 clean data, 02 run the simulator
analysis/         report analyses and plotnine figures (only call functions/)
reports/          Preliminary Results and Financial Impacts tables, figures and key numbers
results/          local outputs of simulator runs (git-ignored)
tests/            known-answer and degenerate-case checks for every statistic
ROADMAP.md        the single source of truth: approach, assumptions, equations, results, changelog
```

## Setup (Windows, Git Bash or PowerShell; Posit Cloud works the same with `python`)

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest
```

To regenerate the report results and figures:
```bash
.venv/Scripts/python analysis/01_preliminary_results.py
.venv/Scripts/python analysis/02_significance.py
.venv/Scripts/python analysis/03_financial_impacts.py
```
