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
