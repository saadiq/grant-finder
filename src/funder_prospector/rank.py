import math
from collections import defaultdict

from .models import FunderProspect


def rank_funders(edges):
    by = defaultdict(list)
    for e in edges:
        by[e["funder_ein"]].append(e)
    out = []
    for ein, rows in by.items():
        peers = {r["recipient_ein"] for r in rows}
        total = sum(r["amount"] or 0 for r in rows)
        years = [r["tax_year"] for r in rows if r["tax_year"]]
        recent = max(years) if years else None
        purposes = sorted({(r["purpose"] or "").strip()
                           for r in rows if (r["purpose"] or "").strip()})[:5]
        score = len(peers) * 10 + math.log10(total + 1) * 2 + (recent or 0) * 0.01
        out.append(FunderProspect(ein, rows[0]["funder_name"], rows[0]["funder_type"],
                                  len(peers), total, recent, purposes, round(score, 2)))
    out.sort(key=lambda p: p.score, reverse=True)
    return out
