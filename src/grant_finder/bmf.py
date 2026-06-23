import csv
import requests
from rapidfuzz import fuzz

# Regional EO BMF extracts (national coverage).
BMF_URLS = [
    "https://www.irs.gov/pub/irs-soi/eo1.csv",
    "https://www.irs.gov/pub/irs-soi/eo2.csv",
    "https://www.irs.gov/pub/irs-soi/eo3.csv",
    "https://www.irs.gov/pub/irs-soi/eo4.csv",
]


def _int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def load_bmf_csv(conn, csv_path):
    n = 0
    with open(csv_path, newline="", encoding="latin-1") as fh:
        for row in csv.DictReader(fh):
            conn.execute(
                "INSERT OR REPLACE INTO orgs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (row["EIN"], row.get("NAME", ""), row.get("NTEE_CD", ""),
                 row.get("CITY", ""), row.get("STATE", ""),
                 _int(row.get("ASSET_AMT")), _int(row.get("INCOME_AMT")),
                 _int(row.get("REVENUE_AMT")), row.get("FOUNDATION", ""),
                 row.get("SUBSECTION", "")))
            n += 1
    conn.commit()
    return n


def download_bmf(dest, fetch=requests.get):
    import os
    paths = []
    for url in BMF_URLS:
        p = os.path.join(dest, url.rsplit("/", 1)[-1])
        r = fetch(url, timeout=300)
        r.raise_for_status()
        with open(p, "wb") as fh:
            fh.write(r.content)
        paths.append(p)
    return paths


def _block_token(name):
    """Extract first token for blocking candidates by name prefix."""
    parts = name.upper().replace("THE ", "", 1).split()
    return parts[0] if parts else ""


def resolve(conn, name, city, state, threshold=88):
    """Fuzzy-match name to org EIN by state + first-token block.

    Returns (ein, score) if best score >= threshold, else (None, best_score).
    """
    if not name or not state:
        return (None, 0.0)
    token = _block_token(name)
    rows = conn.execute(
        "SELECT ein, name FROM orgs WHERE state=? AND name LIKE ?",
        (state, token + "%")).fetchall()
    best_ein, best = None, 0.0
    for r in rows:
        s = fuzz.token_sort_ratio(name.upper(), (r["name"] or "").upper())
        if s > best:
            best_ein, best = r["ein"], s
    return (best_ein, best) if best >= threshold else (None, best)


def resolve_pf_recipients(conn, threshold=88):
    """Update recipient_ein for unresolved PF grant rows.

    Returns count of rows resolved.
    """
    rows = conn.execute(
        "SELECT rowid, recipient_name, recipient_city, recipient_state FROM grants "
        "WHERE source='PF-grant' AND (recipient_ein='' OR recipient_ein IS NULL)"
    ).fetchall()
    n = 0
    for r in rows:
        ein, score = resolve(conn, r["recipient_name"], r["recipient_city"],
                             r["recipient_state"], threshold)
        if ein:
            conn.execute("UPDATE grants SET recipient_ein=?, resolved_score=? WHERE rowid=?",
                         (ein, score, r["rowid"]))
            n += 1
    conn.commit()
    return n
