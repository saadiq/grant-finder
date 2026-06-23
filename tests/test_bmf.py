from pathlib import Path
from grant_finder import bmf, db
from grant_finder.models import GrantEdge
from grant_finder import ingest

FIX = Path(__file__).parent / "fixtures"


def test_load_bmf_csv():
    conn = db.init_db(":memory:")
    n = bmf.load_bmf_csv(conn, str(FIX / "bmf_sample.csv"))
    assert n == 3
    row = conn.execute("SELECT ntee, city FROM orgs WHERE ein='133957095'").fetchone()
    assert row["ntee"] == "B92" and row["city"] == "NEW YORK"


def _seed_orgs(conn):
    bmf.load_bmf_csv(conn, str(FIX / "bmf_sample.csv"))


def test_resolve_matches_despite_name_variation():
    conn = db.init_db(":memory:")
    _seed_orgs(conn)
    ein, score = bmf.resolve(conn, "READ ALLIANCE", "NEW YORK", "NY")
    assert ein == "133957095" and score >= 88


def test_resolve_returns_none_below_threshold():
    conn = db.init_db(":memory:")
    _seed_orgs(conn)
    ein, _ = bmf.resolve(conn, "COMPLETELY DIFFERENT THING", "NEW YORK", "NY")
    assert ein is None


def test_resolve_pf_recipients_fills_ein():
    conn = db.init_db(":memory:")
    _seed_orgs(conn)
    ingest.insert_edges(conn, [GrantEdge(
        "999", "F", "990PF", "READ ALLIANCE", "", "NEW YORK", "NY",
        "LITERACY", 5000, "PF-grant", 2022, None)])
    assert bmf.resolve_pf_recipients(conn) == 1
    row = conn.execute("SELECT recipient_ein FROM grants").fetchone()
    assert row["recipient_ein"] == "133957095"
