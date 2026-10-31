# library.py
# Load the TASER-EV component library (data/components.csv) and look up parts.
# ROADMAP Section 4. The library is built by code/01_clean_data.py.

from pathlib import Path

import pandas as pd

LIBRARY_PATH = Path(__file__).resolve().parents[1] / "data" / "components.csv"

# The six component slots of the series system (ROADMAP Section 2)
SLOTS = (
    "ECU MCU",
    "BMS AFE",
    "Digital isolator",
    "Temperature sensor",
    "Gate driver",
    "Current sensor",
)

# Test parameters every part needs before the simulator can use it (E2-E4)
REQUIRED = ("test_temp_c", "test_hours", "sample_size", "failures", "ea_ev")


# load_library(): read the component library
# path: [str/Path] csv file; defaults to data/components.csv
# usable_only: [bool] drop parts that are missing a required test parameter
def load_library(path=LIBRARY_PATH, usable_only=False):
    lib = pd.read_csv(path)
    lib["flag"] = lib["flag"].fillna("")
    if usable_only:
        lib = lib[lib["usable"]].reset_index(drop=True)
    return lib


# get_part(): return one part's row as a Series
# part: [str] part number as it appears in the library's `part` column
# library: [DataFrame] from load_library(); loaded fresh if not given
# Raises KeyError for an unknown part, ValueError for a part the simulator can't use.
def get_part(part, library=None):
    lib = load_library() if library is None else library
    match = lib[lib["part"] == part]
    if match.empty:
        raise KeyError(f"{part!r} is not in the library. Parts: {', '.join(lib['part'])}")
    row = match.iloc[0]
    if not row["usable"]:
        raise ValueError(f"{part!r} can't be simulated: {row['flag']}")
    return row
