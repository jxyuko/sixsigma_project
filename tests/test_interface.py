# test_interface.py
# Input parsing and output formatting for the command-line simulator (code/02_run_simulator.py).

import subprocess
import sys
from pathlib import Path

import pytest

from functions.interface import DEFAULT_CONFIG, describe_profile, parse_profile
from functions.library import SLOTS

ROOT = Path(__file__).resolve().parents[1]


def test_parse_single_temperature():
    assert parse_profile("55") == 55.0
    assert parse_profile(" 85.5 ") == 85.5


def test_parse_profile_fractions_and_percent():
    expected = [(40.0, 0.5), (70.0, 0.3), (105.0, 0.2)]
    assert parse_profile("40:0.5, 70:0.3, 105:0.2") == expected
    pct = parse_profile("40:50,70:30,105:20")
    assert [t for t, _ in pct] == [t for t, _ in expected]
    assert [w for _, w in pct] == pytest.approx([w for _, w in expected])


def test_parse_profile_rejects_text():
    with pytest.raises(ValueError):
        parse_profile("hot")


def test_describe_profile():
    assert describe_profile(55.0) == "55 C"
    assert describe_profile([(40, 0.5), (70, 0.5)]) == "40 C for 50%, 70 C for 50%"


def test_default_config_fills_all_six_slots():
    assert set(DEFAULT_CONFIG) == set(SLOTS)


def run(*args, stdin=None):
    return subprocess.run([sys.executable, str(ROOT / "code" / "02_run_simulator.py"), *args, "--draws", "500"],
                          input=stdin, capture_output=True, text=True, cwd=ROOT, timeout=120)


def test_script_mode1_from_temperature():
    out = run("--temp", "55")
    assert out.returncode == 0, out.stderr
    assert "B0.1 life (hours)" in out.stdout and "P(meets warranty)" in out.stdout


def test_script_mode2_compare():
    out = run("--temp", "40:50,70:30,105:20", "--compare", "ECU MCU=R7F7016903AFP-C")
    assert out.returncode == 0, out.stderr
    assert "P(B outlasts A)" in out.stdout


def test_script_interactive_asks_for_temperature():
    # Temperature 85, Mode 1, default warranty, then Enter for the default part in all six slots
    out = run(stdin="85\n1\n\n" + "\n" * 6)
    assert out.returncode == 0, out.stderr
    assert "Operating temperature in C" in out.stdout
    assert "Operating condition: 85 C" in out.stdout
