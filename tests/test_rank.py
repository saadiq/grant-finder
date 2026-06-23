from funder_prospector import db, rank, ingest
from funder_prospector.models import GrantEdge


def _rows(conn):
    return conn.execute("SELECT * FROM grants").fetchall()


def test_rank_orders_more_peers_first():
    conn = db.init_db(":memory:")
    ingest.insert_edges(conn, [
        GrantEdge("BIG", "Big Funder", "990", "A", "111", "", "NY", "x", 1000, "SchedI", 2023, None),
        GrantEdge("BIG", "Big Funder", "990", "B", "222", "", "NY", "y", 1000, "SchedI", 2022, None),
        GrantEdge("SMALL", "Small Funder", "990PF", "A", "111", "", "NY", "z", 9000, "PF-grant", 2021, None),
    ])
    prospects = rank.rank_funders(_rows(conn))
    assert prospects[0].funder_ein == "BIG"
    assert prospects[0].n_peers == 2 and prospects[0].total_amount == 2000
    assert prospects[0].recent_year == 2023


def test_rank_handles_negative_total():
    """Regression test: funders with negative net totals (returned grants) should not crash."""
    conn = db.init_db(":memory:")
    ingest.insert_edges(conn, [
        GrantEdge("NEG", "Negative Funder", "990PF", "X", "999", "", "CA", "grant", 1000, "PF-grant", 2023, None),
        GrantEdge("NEG", "Negative Funder", "990PF", "Y", "888", "", "CA", "return", -5000, "PF-grant", 2023, None),
    ])
    prospects = rank.rank_funders(_rows(conn))
    assert len(prospects) == 1
    assert prospects[0].funder_ein == "NEG"
    assert prospects[0].total_amount == -4000
    assert prospects[0].n_peers == 2
