import csv
import requests

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
