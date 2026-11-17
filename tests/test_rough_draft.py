# test_rough_draft.py
# The rough-draft case study (analysis/rough_draft/case_study.py, A17-A19) and a run of both scripts.

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "analysis" / "rough_draft"))
import case_study as cs  # noqa: E402


def test_case_study_inputs():
    # Every part has a quantity; BMS AFE counts follow 96 cells / cells per chip (A17)
    assert set(cs.QTY) == set(cs.PARTS)
    assert cs.QTY["BQ79656PAPRQ1"] == 96 // 16 and cs.QTY["LTC6811-1"] == 96 // 12
    assert cs.RECALL_COST["low"] < cs.RECALL_COST["base"] < cs.RECALL_COST["high"]
    sel = cs.run()
    assert sel.picks["n_combinations"] == 16                 # 2 x 2 x 2 x 1 x 2 x 1 candidates
    t = sel.candidates.set_index("name")
    assert all(t.loc[p, "qty_per_vehicle"] == q for p, q in cs.QTY.items())
    # Degenerate: least reliable is the highest system FIT, most reliable the lowest
    fits = sel.combinations["system_fit_estimate"]
    assert cs.least_reliable(sel)["system_fit_estimate"] == fits.max()
    assert sel.picks["most_reliable"]["system_fit_estimate"] == fits.min()


@pytest.mark.parametrize("script", ["01_results.py", "02_financial_impacts.py"])
def test_scripts_run(script):
    out = subprocess.run([sys.executable, str(ROOT / "analysis" / "rough_draft" / script)],
                         capture_output=True, text=True, cwd=ROOT, timeout=600)
    assert out.returncode == 0, out.stderr
