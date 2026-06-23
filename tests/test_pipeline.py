from pathlib import Path
from funder_prospector import db, bmf, ingest, pipeline
from funder_prospector.models import GrantEdge, OrgProfile, Peer

FIX = Path(__file__).parent / "fixtures"


def test_run_prospect_unions_peer_and_ntee_matches():
    conn = db.init_db(":memory:")
    bmf.load_bmf_csv(conn, str(FIX / "bmf_sample.csv"))
    # a second B92 (literacy) org that is NOT in the peer list
    conn.execute("INSERT INTO orgs (ein, name, ntee, state) VALUES ('222','OTHER LITERACY','B92','NY')")
    conn.commit()
    ingest.insert_edges(conn, [
        GrantEdge("F1", "Battin Foundation", "990PF", "READ ALLIANCE", "133957095",
                  "NEW YORK", "NY", "YOUTH LITERACY", 210000, "PF-grant", 2022, 95.0),
        GrantEdge("F2", "Other Funder", "990", "OTHER LITERACY", "222",
                  "NEW YORK", "NY", "READING", 5000, "SchedI", 2023, None),
    ])
    profile = OrgProfile("833401365", "Our Kids Read", "B90", "Laurel", "MD", 311838)
    peers = [Peer("133957095", "Read Alliance", "B92", "New York", "NY")]
    md = pipeline.run_prospect(conn, profile, peers)
    assert "Battin Foundation" in md and "$210,000" in md   # exact peer-EIN match
    assert "Other Funder" in md                              # NTEE-widened (B92), not a peer EIN
