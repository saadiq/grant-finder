from . import match, rank, report


def _dedupe(rows):
    seen, out = set(), []
    for r in rows:
        if r["rowid"] in seen:
            continue
        seen.add(r["rowid"])
        out.append(r)
    return out


def run_prospect(conn, profile, peers, ntee_prefixes=None):
    if ntee_prefixes is None:
        ntee_prefixes = sorted({p.ntee for p in peers if p.ntee})
    edges = list(match.find_funder_edges(conn, [p.ein for p in peers]))
    edges += match.find_edges_by_ntee(conn, ntee_prefixes)
    prospects = rank.rank_funders(_dedupe(edges))
    return report.render(prospects, profile)
