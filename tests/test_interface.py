# test_interface.py
# Input parsing for the user-facing simulator (functions/interface.py). The script itself is tested
# end to end in tests/test_candidates.py.

import pytest

from functions.interface import CANDIDATE_COLUMNS, describe_profile, parse_profile, read_candidates


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
