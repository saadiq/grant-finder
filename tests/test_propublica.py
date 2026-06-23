import json
from pathlib import Path
from funder_prospector import propublica
from funder_prospector.models import OrgProfile

FIX = Path(__file__).parent / "fixtures"


def test_parse_org():
    d = json.loads((FIX / "org.json").read_text())
    p = propublica.parse_org(d)
    assert p.ein == "833401365" and p.ntee == "B90" and p.revenue == 311838


def test_parse_search():
    d = json.loads((FIX / "search.json").read_text())
    peers = propublica.parse_search(d)
    assert {x.ein for x in peers} == {"133957095", "591234567", "833401365"}


def test_find_peers_filters_ntee_and_excludes_self():
    applicant = OrgProfile("833401365", "Our Kids Read", "B90", "Laurel", "MD", 311838)
    d = json.loads((FIX / "search.json").read_text())

    def fake_search(q, ntee_id=None, state=None, page=0):
        return propublica.parse_search(d)

    peers = propublica.find_peers(applicant, keywords=("reading",), searcher=fake_search)
    assert [p.ein for p in peers] == ["133957095"]  # B92 kept; K31 dropped; self excluded


def test_find_peers_dedup_and_cap():
    """Verifies dedup (same EIN across two keyword passes appears once) and cap enforcement."""
    from funder_prospector.models import Peer

    peer_a = Peer("111111111", "Read Alliance", "B92", "Boston", "MA")
    peer_b = Peer("222222222", "Literacy League", "B91", "Austin", "TX")
    applicant = OrgProfile("000000000", "Applicant Org", "B90", "DC", "DC", 0)

    # Both keywords return peer_a first; second keyword also returns peer_b.
    def fake_search(q, ntee_id=None, state=None, page=0):
        if q == "reading":
            return [peer_a, peer_b]
        return [peer_a]  # same peer_a EIN again — should be deduped

    # Dedup: two keywords, peer_a appears in both passes → must appear only once.
    peers_dedup = propublica.find_peers(
        applicant, keywords=("reading", "literacy"), searcher=fake_search
    )
    eins = [p.ein for p in peers_dedup]
    assert eins.count("111111111") == 1, "peer_a should appear exactly once despite two keyword passes"
    assert "222222222" in eins

    # Cap: cap=1 must limit result to at most 1 peer even when multiple are eligible.
    peers_capped = propublica.find_peers(
        applicant, keywords=("reading", "literacy"), cap=1, searcher=fake_search
    )
    assert len(peers_capped) == 1
