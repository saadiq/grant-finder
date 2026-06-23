from grant_finder import db, match, bmf, ingest
from grant_finder.models import GrantEdge
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def _seed(conn):
    bmf.load_bmf_csv(conn, str(FIX / "bmf_sample.csv"))
    ingest.insert_edges(conn, [
        GrantEdge("F1", "Funder One", "990", "Read Alliance", "133957095",
                  "NEW YORK", "NY", "literacy", 10000, "SchedI", 2023, None),
        GrantEdge("F2", "Funder Two", "990PF", "Unrelated Org", "000000001",
                  "DALLAS", "TX", "general", 2000, "PF-grant", 2022, 95.0),
    ])


def test_find_funder_edges_by_ein():
    conn = db.init_db(":memory:")
    _seed(conn)
    rows = match.find_funder_edges(conn, ["133957095"])
    assert len(rows) == 1 and rows[0]["funder_ein"] == "F1"


def test_find_edges_by_ntee_prefix():
    conn = db.init_db(":memory:")
    _seed(conn)
    rows = match.find_edges_by_ntee(conn, ["B"])  # education
    assert [r["funder_ein"] for r in rows] == ["F1"]
