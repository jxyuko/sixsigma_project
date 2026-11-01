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
3. **Treats the failure rate as uncertain.** With zero failures we only know the rate is small,
   so it is drawn from Gamma(f + 1, n · t · AF); the activation energy Ea is drawn from
   0.5–0.9 eV (most likely 0.7).
4. **Builds the system** as parts in series: system failure rate = sum of the part rates.
5. **Repeats 5,000 times** (Monte Carlo) and reports each result as a median with a 95%
   confidence interval.

Constant failure rate (exponential life) is assumed, and only thermal failure mechanisms are
modelled. Every assumption (A1–A14) and equation (E1–E21) is in [`ROADMAP.md`](ROADMAP.md).

## What it computes

**Inputs:**
- **Required:** operating temperature (or profile), how many hours the part must work, and the
  candidates for any slots.
- **Optional, with defaults:** target reliability (0.999), fleet size (1,000), repair cost, unit price.

**Outputs:**

| For | Outputs (95% CIs) |
|---|---|
| Each candidate | AF, FIT, MTTF, B0.1 life, reliability over the mission R(t), the 95% lower bound on R, whether the target is met, chance it is the best in its slot |
| Each system combination | system FIT, R(t), B0.1, target check, chance it is the best combination |
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
functions/        the simulator: equations, Monte Carlo engine, statistics (all tested)
code/             01 clean data, 02 run the simulator, 03 validation
analysis/         report analyses and plotnine figures (only call functions/)
reports/          Preliminary Results tables, figures and key numbers
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
```
