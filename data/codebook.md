# Codebook

`code/01_clean_data.py` builds two files from `data/raw/parameter_table.xlsx`, which is never
edited:

| File | What it is | Used by the model? |
|---|---|---|
| `data/components.csv` | The **component library**: one row per part, with the HTOL test data the simulator runs on | **Yes** |
| `data/reference/published_fit.csv` | Manufacturer-published FITs, the team's verification of them, and our FIT calculated at the same conditions | **No.** Stored for reference; we may decide to use it later |

To rebuild both:

```bash
.venv/Scripts/python code/01_clean_data.py
```

**Source of every value:** the team's parameter table, transcribed from supplier reliability
reports (TI, Analog Devices, Renesas) and distributor price pages (Sheet2). The report URLs aren't
in the raw file yet `[TODO]`, except those in `data/reference/fit_verification.csv`. No values are
invented. Where the raw table is blank, the cell stays blank and the part is flagged.

## `data/components.csv`: the model's input

| Column | Type | Unit | Meaning | Raw-table source |
|---|---|---|---|---|
| `slot` | category | | One of the six component slots: ECU MCU, BMS AFE, Digital isolator, Temperature sensor, Gate driver, Current sensor | Row label or section header in `SubComponent` |
| `supplier` | text | | Manufacturer, normalized ("Rensas" → "Renesas Electronics") | `Manufacturer` |
| `part` | text | | Part number used by the simulator (unique key) | `Reference`, with typo fixes |
| `raw_part` | text | | Part number exactly as typed in the raw table | `Reference` |
| `family` | text | | Qualification family whose data the part shares (A9); equals `part` for stand-alone parts | Derived from the part prefix |
| `test_temp_c` | number | °C | HTOL stress (junction) temperature, T_test | `Test temp (C)` |
| `test_hours` | number | h | HTOL duration per device, t | `Test duration (hours)` |
| `sample_size` | number | devices | Units used in the supplier's FIT calculation, n (may be pooled across lots or tests, A6) | `Sample size` |
| `failures` | number | count | Failures observed, f | `Fails` |
| `ea_ev` | number | eV | Activation energy the supplier assumed, Ea | `Activation energy (eV)` |
| `htol_sample_size` | number | devices | Size of the single HTOL test lot set (3 × 77 = 231), for information only | `HTOL sample size` |
| `unit_price_usd` | number | USD | Unit price from the price sheet; blank if none | Sheet2 `Unit price (USD)` |
| `price_part` | text | | Price-sheet part number the price came from (may be a variant or family proxy) | Sheet2 `Product / part number` |
| `source` | text | | Bibliography number in the raw table; report URL still `[TODO]` | `Bibliography` |
| `usable` | bool | | True if every required test parameter (T_test, t, n, f, Ea) is present, so the simulator can use the part | Derived |
| `flag` | text | | Data-quality notes, separated by "; " | Derived |

### Current contents (19 parts, 17 usable)

| Slot | Parts | Usable |
|---|---|---|
| ECU MCU | 4 TI C2000 (one shared dataset), 5 Renesas RH850 (one shared dataset) | 9 |
| BMS AFE | TI BQ79656, ADI LTC6811-1, Renesas ISL78714 | 2 (ISL78714: failures blank) |
| Digital isolator | TI ISO7741, ADI ADuM141E (1 failure) | 2 |
| Temperature sensor | TI TMP4719, ADI MAX31730 | 1 (MAX31730: sample size blank) |
| Gate driver | TI UCC21750, ADI ADuM4135 | 2 |
| Current sensor | TI TMCS1101 | 1 (no unit price) |

## `data/reference/published_fit.csv`: reference only, not used by the model

One row per part, keyed by `part` (plus `slot`, `supplier`, `family`).

| Column | Type | Unit | Meaning | Source |
|---|---|---|---|---|
| `fit_published` | number | FIT | FIT exactly as in the raw table (manufacturer-reported). Never overwritten | raw `FIT` |
| `fit_published_status` | text | | `verified` (team found it in the supplier report), `not verified` (looked, couldn't find it), or `not checked` | `fit_verification.csv` |
| `fit_published_source` | text | | Report, page and URL where the published FIT was checked | `fit_verification.csv` |
| `fit_published_note` | text | | What the published FIT is based on, and why it may differ from our calculation | `fit_verification.csv` |
| `mtbf_published_h` | number | h | Published MTBF (one non-numeric duplicate entry is dropped) | raw `MTBF` |
| `ref_temp_c` | number | °C | Use temperature the published FIT refers to | raw `Usage temp (C)` |
| `ref_conf_level` | number | fraction | Confidence level the published FIT used (60% → 0.60) | raw `Conf level (%)` ÷ 100 |
| `af_published` | number | | Team's Arrhenius AF from T_test to `ref_temp_c` (TI and RH850 rows only) | raw `Thermal acceleration factor AF` |
| `fit_calculated` | number | FIT | Our FIT from the test data: the chi-square bound (E2–E5) at the same `ref_temp_c` and `ref_conf_level`. Blank if the part isn't usable | Derived |
| `fit_calc_ratio` | number | | `fit_calculated / fit_published`. About 1 means our calculation reproduces the manufacturer | Derived |
| `fit_calc_note` | text | | The assumption behind `fit_calculated`: the table's n, t and f are the supplier's full basis (A6) | Derived |

`data/reference/fit_verification.csv` is the team's hand-maintained record of which published
values were checked in supplier reports (columns `family_or_part`, `fit_status`, `fit_source`,
`fit_basis_note`, `checked_on`). To add a check, add a row and rebuild.

### Published vs calculated FIT

| Family | Published | Status | Calculated | Ratio | Why they differ |
|---|---|---|---|---|---|
| TI C2000 | 6.19 | not checked | 6.21 | 1.00 | Reproduced |
| TI TMCS1101 | 1.7 | not checked | 1.69 | 1.00 | Reproduced |
| TI BQ79656, TMP4719 | 0.1 | not checked | 0.116 | 1.16 | TI rounds FIT to 0.1; their MTBF (8.71e9 h → 0.115 FIT) matches |
| TI ISO7741, UCC21750 | 0.2 | not checked | 0.135 | 0.68 | Rounded; their MTBF (5.0e9 h → 0.2 FIT) suggests a slightly different basis |
| Renesas RH850 | 0.0011 | verified | 15.3 | 13,900 | Renesas's basic failure rate rests on more data than the single 231-device HTOL test in our table |
| ADI LTC6811-1 | 33.95 | verified | 0.32 | 0.009 | ADI reports 33.95 directly (0.7 eV, 60%); our table's test data isn't ADI's basis |
| Renesas ISL78714 | 3.72 | verified | — | — | Team reproduced 3.72 from all seven HTOL groups; our table lacks the per-group data and failures |
| ADI ADuM141E | 20.23 | not checked | 0.45 | 0.02 | Unknown; check the report |
| ADI ADuM4135 | 11.28 | not verified | 0.37 | 0.03 | 11.28 not found in ADI's qualification summary |
| ADI MAX31730 | 28.1 | not checked | — | — | Sample size missing |

**Takeaway:** the raw table mixes FITs reported directly by manufacturers with FITs that can be
calculated from the test data in the table. A large ratio doesn't mean a value is wrong; it means
the manufacturer used a larger or different dataset than the one we transcribed.

## What the build does

1. Walks the raw sheet top to bottom. Section-header rows (e.g. "Gate Driver") set the slot for
   the alternative-supplier rows under them.
2. Keeps every row with a part number, and drops duplicates (keeping the first occurrence).
3. Normalizes supplier names and fixes part-number typos, keeping the original in `raw_part`.
4. Joins unit prices from Sheet2 through an explicit mapping. Orderable variants and family proxies
   are flagged, not hidden.
5. Marks a part `usable = False` if a required test parameter is blank, and adds flags.
6. Splits the output:
   - test data → `components.csv`;
   - published values, verification and our calculated FIT → `reference/published_fit.csv`.

**Dropped raw columns:** `Mission time (hours)` (its unit is unclear, and the simulator takes the
warranty from A7 instead), plus empty helper rows and duplicate rows.

## `data/examples/candidates_example.csv`: Mode 3 input template

Input for supplier selection (`code/02_run_simulator.py --candidates <file>`). One row per candidate.
The example is filled with **real** data from the parameter table (no invented values), including
one candidate entered in report-summary form (UCC21750's published 0.2 FIT at 55 °C, 60%).

| Column | Required | Unit | Meaning |
|---|---|---|---|
| `slot` | yes | | One of the six slots |
| `name` | yes | | Candidate name (unique within a slot) |
| `supplier` | no | | Supplier name |
| `test_temp_c` | yes | °C | HTOL stress temperature |
| `test_hours`, `sample_size`, `failures` | raw-data form | h, devices, count | Raw test data (E3, E4) |
| `fit` or `mttf_hours` | summary form | FIT or h | The report's FIT or MTTF/MTBF (E15) |
| `ref_temp_c` | summary form, optional | °C | Temperature the FIT/MTTF refers to (default `test_temp_c`) |
| `conf_level` | summary form, optional | fraction | Confidence level of the FIT/MTTF (default 0.60, A11) |
| `ea_ev` | optional | eV | Activation energy stated in the report (default: library median, A12) |
| `source` | no | | Where the values come from (not read by the code) |
