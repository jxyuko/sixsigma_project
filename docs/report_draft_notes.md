# Report 2 (rough draft): notes

Things the second report must say, collected while we finish the simulator. The Preliminary Results
numbers are **not** reused; every number in this report comes from the current simulator (method v4).
Assumption and equation numbers (A#, E#) refer to ROADMAP.md.

## Mission hours (A7)

- Mission used in the case study: **2,920 h = 8 years × 365 days × 1 powered-on hour per day.**
- **1 h/day:** Hungund & Steinbach, *American Driving Survey: 2024*, AAA Foundation for Traffic Safety
  (Dec. 2025). U.S. drivers average 60.4 minutes of driving per day.
- **8 years:** the federal requirement is **8 years or 80,000 miles**, whichever comes first.
  - Primary citation (U.S. government): U.S. DOE Alternative Fuels Data Center, "Battery Durability and
    Warranty Requirements for Model Years 2027 and Later", https://afdc.energy.gov/laws/14222
  - It applies to the high-voltage batteries and electric powertrain parts of light- and medium-duty
    BEVs and PHEVs, which EPA classes as specified major emission control components under Clean Air
    Act Section 207(i)(2), from model year 2027.
  - Carmakers commonly offer 8 years / 100,000 miles (secondary: Kelley Blue Book,
    https://www.kbb.com/car-advice/hybrid-ev-battery-warranty). California requires 10 yr / 150,000 mi.
  - Our mission uses the 8 years only; miles don't enter, because we convert years to powered-on hours.
- **What TI states (manufacturer's view):** TI gives a design lifetime, not a warranty in years.
  - Exact sentence: "For automotive grade products that are specified above 105°C TJ, their reliability
    mission profile is targeted for an AEC-Q100 mission profile of 15 years on with ~12% duty cycle."
  - That works out to 15 × 8,760 × 0.12 ≈ **15,800 powered-on hours**.
  - Industrial embedded processors: 10 years at 105 °C T_J, 100% on.
  - Source: TI SPRABX4C, *Calculating Useful Lifetimes of Embedded Processors* (A. Webber, Nov. 2014,
    rev. Oct. 2026), https://www.ti.com/lit/pdf/sprabx4
  - Possible sensitivity row: mission 15,800 h (TI's design life) vs 2,920 h (warranty).

## Reliability target 0.999 (A13)

- 0.999 is a **team assumption**: at most 1,000 failures per million systems over the mission. It is not
  a course number.
- The *check* is from the course: the 95% maximum failure rate χ²(0.95; 2r+2)/(2D) (Recitation 12).
- Industry quotes field failures in ppm. By ~2000 carmakers reported warranty data in single- to
  triple-digit ppm, and suppliers are pushed toward "zero defects" (under 1 ppm). There is no single
  official value. Sources:
  - Electronic Design, "What's the Price Tag on Failure in Automotive Electronics?",
    https://www.electronicdesign.com/markets/automotive/article/21808089/whats-the-price-tag-on-failure-in-automotive-electronics
  - Electronic Design, "Achieve 0 ppm In Your Automotive Testing",
    https://www.electronicdesign.com/technologies/test-measurement/article/21794591/achieve-0-ppm-in-your-automotive-testing
  - KLA, "Process Watch: The (automotive) problem with...", https://www.kla.com/documents/01_ProcessWatchAutomotive_2018_01.pdf
- **We checked an under-1 ppm target** (system R ≥ 0.999999 over 2,920 h at 55 °C, so at most 0.342 FIT)
  on the library parts. Nothing can demonstrate it with 95% confidence:

  | Target | Allowed system FIT | Parts meeting | Combinations meeting |
  |---|---|---|---|
  | 0.999999 (1 ppm) | 0.342 | 0 / 10 | 0 / 16 |
  | 0.99999 (10 ppm) | 3.42 | 7 / 10 | 0 / 16 |
  | 0.9999 (100 ppm) | 34.2 | 9 / 10 | 8 / 16 |
  | 0.999 (1,000 ppm) | 343 | 10 / 10 | 16 / 16 |

  - The best part reaches 1.1 ppm, and the best system reaches 27.5 FIT ≈ 80 ppm (95% maximum).
  - Reason: zero-failure tests of this size can't show rates that low.
  - So we keep 0.999 and state that industry practice is stricter. The 0.9999 row is worth showing:
    it is where the choice starts to matter.

- **What "zero defects / under 1 ppm" means in industry.** It is a quality metric for shipped parts,
  not a reliability demonstration:
  - **ppm (or DPM, defective parts per million):** the number of parts per million shipped that are
    found defective or returned from the field.
  - It is counted over millions to billions of units in production and in vehicles, from line
    rejects, customer returns and warranty claims. It is not measured from a qualification test.
  - **"Zero defects":** the automotive quality goal of driving that count toward 0 ppm through design,
    screening and process control (the AEC's Zero Defects framework, AEC-Q004). It is usually stated
    **per component** and per supplier, not per vehicle system over a mission.

- **Why our parts "fail" an under-1 ppm target although they come from these same manufacturers.**
  1. **Our check is a proof at 95% confidence, not a best guess.** We use the 95% maximum failure
     rate, the highest rate the test can't rule out. With zero failures it is 2.996 / D, so it depends
     only on the test's size. On the **estimate** (best guess), 7 of 10 parts are already under 1 ppm
     over 2,920 h at 55 °C:

     | Part | Estimate | 95% maximum |
     |---|---|---|
     | BQ79656, TMP4719 | 0.26 ppm | 1.1 ppm |
     | ISO7741, UCC21750 | 0.30 ppm | 1.3 ppm |
     | ADuM141E, LTC6811, ADuM4135 | 0.65–0.82 ppm | 3.1–3.6 ppm |
     | TMCS1101 (current sensor) | 3.7 ppm | 16 ppm |
     | C2000 / RH850 (MCUs) | 14 / 34 ppm | 59 / 146 ppm |

  2. **The tests are too small to prove 1 ppm.** Proving 1 ppm for one part over 2,920 h with zero
     failures needs D = 2.996 / (1e-6 / 2,920) ≈ 8.7 billion equivalent device-hours. The C2000 test
     gives 148 million, about 60 times too little. A qualification test can't do this for any
     supplier: a 77-unit AEC-Q100 test with zero failures demonstrates only about 30,000 ppm at 90%
     confidence (KLA source above). Suppliers' ppm claims rest on field and production data instead.
  3. **Our target is harsher.** We apply it to the whole six-part system over 8 years of driving, while
     industry ppm is per component.
  4. **The MCUs are different.** Even on the estimate they are 14–34 ppm. They are large, complex
     chips tested at 125–150 °C, so a higher rate is expected.

  - **Conclusion for the report:** the parts are not shown to be worse than industry claims. Proving
    under 1 ppm needs field-scale evidence that no single qualification report provides, so the
    simulator keeps 0.999 as its demonstrable target.
  - Sources on zero defects / AEC-Q004 (secondary; the official AEC-Q004 text, from aecouncil.com, was
    not found online):
    - Electronic Design, "A Portal to the World of Component Reliability",
      https://www.electronicdesign.com/markets/automotive/article/21797594/a-portal-to-the-world-of-component-reliability
      (zero defects means no failures over the component's life as each carmaker defines it, so the
      exact target varies by carmaker)
    - Amkor, "The Drive Toward Zero Defects", https://amkor.com/blog/the-drive-toward-zero-defects/
      (AEC-Q004 is a framework for a strategy toward zero defects, written across the supply chain)
    - In the report, say "AEC-Q004 provides a framework toward zero defects" and don't quote a ppm
      number as an AEC requirement.

## Prices (A14)

- An unpriced candidate gets the Sheet2 **average for its slot** (component type), whoever makes it.
  Within a slot, unpriced candidates differ only in reliability.
- Prices the user enters always win.
- Replacement cost = unit price, so labour and logistics are left out and warranty cost is understated.

## Goodness of fit and the life models (A1, A16)

- Keep this text, nearly verbatim: "Lesson 12B's chi-square goodness-of-fit test needs failure times
  grouped into intervals, which we don't have (HTOL reports give only failure counts, mostly zero). So
  we can't test whether the exponential fits. That's also why the professor said to then try the
  lognormal and Weibull: to see how much the answer depends on the assumption."
- Bootstrapping is impossible for the same reason: resampling zero failures always gives zero. The
  chi-square / k-factor bounds are the exact interval for the exponential.
- Lognormal / Weibull shapes come from SEMATECH (2000), p. 29, because the course gives no
  semiconductor values. Compare the picks, not the fit.

## 60% upper bound

- The simulator prints the 60% upper bound in the details. It is the suppliers' convention and
  reproduces TI's published FIT (6.21 vs 6.19 for the C2000). Discuss why we rank on the estimate and
  check the target at 95% instead.

## Why the exponential is the final model (references for the report)

- Lesson 12: the exponential needs only a nearly constant failure rate over the period we care about, and
  is fine when we only need the average failure rate for a period (our 8-year warranty).
- JEDEC JESD85A (2021), *Methods for Calculating Failure Rates in Units of FITs*: the industry method behind
  every supplier FIT we use. It applies to failure mechanisms with a constant failure rate, with the
  chi-square bound and Arrhenius acceleration (summaries: https://standards.globalspec.com/std/14580367/jesd85a ;
  Vishay reliability report, https://www.vishay.com/docs/72559/72559.pdf). Using the same model keeps us
  consistent with how the data were produced.
- SEMATECH (2000): the exponential works with few or zero failures; also the source of the lognormal and
  Weibull shapes we tried.
- What trying the other models showed (R8): the cheapest pick meeting the target is the same under every
  model; the Weibull β 0.8 gives the same three picks; the lognormal models and the Weibull β 2.4 move
  only the MCU pick (C2000 → RH850), because the RH850's 150 °C test is the longest in equivalent time.
  Wear-out shapes predict almost no failures within a 2,920 h mission, far shorter than the ~78,000 h
  equivalent test time.

## Where the rough-draft numbers are

- Results: `reports/rough_draft/results/key_numbers.md`, tables r1–r8, figures 1–3
  (`analysis/rough_draft/01_results.py`).
- Financial impacts: `reports/rough_draft/financial/key_numbers_financial.md`, tables fin_1–fin_6,
  figure F1 (`analysis/rough_draft/02_financial_impacts.py`).
- Case-study assumptions (quantities, recall trigger, recall cost): ROADMAP A17–A19.
