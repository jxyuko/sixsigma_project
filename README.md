# TASER-EV

**Thermal Acceleration-based Simulation and Evaluation of Reliability for EV Electronics**
SYSEN 5300 Six Sigma project - Alpomer Tolga Aksit, Luis Luna, Janset Erdenbil.

Translates suppliers' published accelerated-life (HTOL) test data for six EV electronic
components (ECU MCU, BMS AFE, digital isolator, temperature sensor, gate driver, current
sensor) to a common basis under user-defined thermal conditions, then reports component
FIT/MTTF, series-system reliability, B0.1 life, the B0.1-to-warranty ratio, and the change
in B0.1 when suppliers are swapped.

## Layout

```
data/raw/         source data as collected (parameter_table.xlsx) - never edited by code
data/             cleaned inputs the code reads, plus a codebook
functions/        reusable functions (Arrhenius AF, chi-square FIT, reliability, system)
code/             analysis scripts that produce results, run in numbered order
tests/            known-answer and degenerate-case checks for every statistic
results/tables/   CSV outputs
results/figures/  PNG figures
reports/          .docx deliverables (preliminary results, financial impacts)
```

## Setup (Windows, Git Bash or PowerShell)

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest
```
