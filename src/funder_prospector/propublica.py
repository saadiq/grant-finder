import requests

from .models import OrgProfile, Peer

API = "https://projects.propublica.org/nonprofits/api/v2"


def _ein(x):
    return str(x).zfill(9)


def parse_org(d):
    o = d["organization"]
    rev = None
    fw = d.get("filings_with_data") or []
    if fw:
        rev = fw[0].get("totrevenue")
    return OrgProfile(_ein(o["ein"]), o.get("name", ""), o.get("ntee_code") or "",
                      o.get("city", ""), o.get("state", ""), rev or o.get("revenue_amount"))


def parse_search(d):
    return [Peer(_ein(o["ein"]), o.get("name", ""), o.get("raw_ntee_code") or "",
                 o.get("city", ""), o.get("state", "")) for o in d.get("organizations", [])]


def get_org(ein, fetch=requests.get):
    r = fetch(f"{API}/organizations/{int(ein)}.json", timeout=30)
    r.raise_for_status()
    return parse_org(r.json())


def search(q, ntee_id=None, state=None, page=0, fetch=requests.get):
    params = {"q": q, "page": page}
    if ntee_id:
        params["ntee[id]"] = ntee_id
    if state:
        params["state[id]"] = state
    r = fetch(f"{API}/search.json", params=params, timeout=30)
    r.raise_for_status()
    return parse_search(r.json())


def find_peers(profile, keywords=("reading", "literacy"), ntee_prefixes=("B",),
               cap=150, searcher=search):
    seen, peers = set(), []
    for kw in keywords:
        for p in searcher(kw, ntee_id=2):  # 2 = Education category
            if p.ein in seen or p.ein == profile.ein:
                continue
            if not any(p.ntee.startswith(pre) for pre in ntee_prefixes):
                continue
            seen.add(p.ein)
            peers.append(p)
            if len(peers) >= cap:
                return peers
    return peers
