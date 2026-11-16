# test_interface.py
# Input parsing for the user-facing simulator (functions/interface.py). The script itself is tested
# end to end in tests/test_candidates.py.

import pytest

from functions.interface import CANDIDATE_COLUMNS, describe_condition, parse_condition, read_candidates


def test_parse_single_temperature():
    assert parse_condition("55") == 55.0
    assert parse_condition(" 85.5 ") == 85.5


def test_parse_band():
    # the operating band (min-max) the part runs across (2026-11-15); profiles are no longer typed in
    assert parse_condition("40-105") == (40.0, 105.0)
    assert parse_condition("40.5 - 85") == (40.5, 85.0)


def test_parse_condition_rejects_text():
    with pytest.raises(ValueError):
        parse_condition("hot")


def test_describe_condition():
    assert describe_condition(55.0) == "55 C"
    assert describe_condition((40.0, 105.0)) == "40-105 C (time spread evenly over the band)"


def test_read_candidates_requires_key_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("slot,name\nGate driver,a\n")
    with pytest.raises(ValueError):
        read_candidates(bad)


def test_read_candidates_blank_cells_become_none(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("slot,name,test_temp_c,fit,unit_price_usd,notes\nGate driver,a,125,2.0,,ignored\n")
    c = read_candidates(f)[0]
    assert c["fit"] == 2.0 and c["unit_price_usd"] is None
    assert "notes" not in c and set(c) <= set(CANDIDATE_COLUMNS)
