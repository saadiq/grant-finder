from pathlib import Path
from funder_prospector import bmf, db

FIX = Path(__file__).parent / "fixtures"


def test_load_bmf_csv():
    conn = db.init_db(":memory:")
    n = bmf.load_bmf_csv(conn, str(FIX / "bmf_sample.csv"))
    assert n == 3
    row = conn.execute("SELECT ntee, city FROM orgs WHERE ein='133957095'").fetchone()
    assert row["ntee"] == "B92" and row["city"] == "NEW YORK"
