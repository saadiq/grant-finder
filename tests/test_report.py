from grant_finder import report
from grant_finder.models import FunderProspect, OrgProfile


def test_render_contains_funder_and_amount():
    applicant = OrgProfile("833401365", "Our Kids Read", "B90", "Laurel", "MD", 311838)
    prospects = [FunderProspect("F1", "Battin Foundation", "990PF", 2, 210000,
                                2022, ["YOUTH LITERACY"], 24.3)]
    md = report.render(prospects, applicant)
    assert "Our Kids Read" in md
    assert "Battin Foundation" in md
    assert "$210,000" in md
    assert "F1" in md and "YOUTH LITERACY" in md
