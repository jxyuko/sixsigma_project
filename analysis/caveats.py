# caveats.py
# The data caveat printed in every key-numbers file (ROADMAP Sections 9, 10 and 14), kept in one place
# so the three reports use the same wording.

DATA_CAVEAT = """## Data caveat: what these results mean

All results are **demonstrated reliability from the qualification test data in our parameter table**
(test temperature, hours, sample size, failures). The calculation is verified (it reproduces the course
chi-square formula and TI's published FITs), but a part's result only reflects the test data we
transcribed. For four parts the manufacturer's published FIT rests on other or more data than our table:

- **Renesas RH850:** only one 231-device HTOL test is in the table. Renesas's verified published FIT
  (0.0011) rests on much more data, so the RH850 is very likely **more reliable than our result shows**
  (our 60% FIT at 55 C is 15.5).
- **ADI LTC6811-1, ADuM141E, ADuM4135:** our table gives them **lower** FITs (0.32-0.45 at 55 C, 60%)
  than ADI publishes (11-34; LTC6811-1 verified, ADuM4135 not found in ADI's report, ADuM141E not
  checked), so their results **may be optimistic**.

So the supplier comparisons in the MCU, BMS AFE, digital isolator and gate driver slots, and the "least
reliable" combination built from these parts, compare the evidence in our table, not settled true
reliability. No supplier difference is statistically significant (Preliminary Results, 9b).
"""
