from pathlib import Path
from funder_prospector import ingest

FIX = Path(__file__).parent / "fixtures"


def test_parse_990pf_grant():
    edges = ingest.parse_filing(str(FIX / "990pf.xml"))
    assert len(edges) == 1
    e = edges[0]
    assert e.funder_ein == "386571896" and e.funder_type == "990PF"
    assert e.recipient_name == "READ ALLIANCE" and e.recipient_ein == ""
    assert e.recipient_state == "NY" and e.amount == 5000
    assert e.source == "PF-grant" and e.tax_year == 2022


def test_parse_990_schedule_i_grant():
    edges = ingest.parse_filing(str(FIX / "990schedi.xml"))
    assert len(edges) == 1
    e = edges[0]
    assert e.recipient_ein == "581309309" and e.source == "SchedI"
    assert e.amount == 47459 + 580600 and e.tax_year == 2023
