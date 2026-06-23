import glob
import os
import xml.etree.ElementTree as ET
import requests

from .models import GrantEdge

NS = {"i": "http://www.irs.gov/efile"}


def _t(el, path):
    x = el.find(path, NS)
    return (x.text or "").strip() if x is not None else ""


def _num(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def parse_filing(path):
    root = ET.parse(path).getroot()
    rtype = _t(root, ".//i:ReturnTypeCd")
    fein = _t(root, ".//i:Filer/i:EIN")
    fname = _t(root, ".//i:Filer/i:BusinessName/i:BusinessNameLine1Txt")
    end = _t(root, ".//i:TaxPeriodEndDt")
    year = int(end[:4]) if end[:4].isdigit() else None
    edges = []
    if rtype == "990PF":
        for g in root.findall(".//i:GrantOrContributionPdDurYrGrp", NS):
            name = (_t(g, "i:RecipientBusinessName/i:BusinessNameLine1Txt")
                    or _t(g, "i:RecipientPersonNm"))
            edges.append(GrantEdge(
                fein, fname, "990PF", name, "",
                _t(g, "i:RecipientUSAddress/i:CityNm"),
                _t(g, "i:RecipientUSAddress/i:StateAbbreviationCd"),
                _t(g, "i:GrantOrContributionPurposeTxt"),
                _num(_t(g, "i:Amt")), "PF-grant", year, None))
    elif rtype in ("990", "990EZ"):
        for g in root.findall(".//i:RecipientTable", NS):
            amt = (_num(_t(g, "i:CashGrantAmt")) or 0) + (_num(_t(g, "i:NonCashAssistanceAmt")) or 0)
            edges.append(GrantEdge(
                fein, fname, rtype,
                _t(g, "i:RecipientBusinessName/i:BusinessNameLine1Txt"),
                _t(g, "i:RecipientEIN"),
                _t(g, "i:USAddress/i:CityNm"),
                _t(g, "i:USAddress/i:StateAbbreviationCd"),
                _t(g, "i:PurposeOfGrantTxt") or _t(g, "i:GrantOrAssistanceDesc"),
                amt, "SchedI", year, None))
    return edges


BUNDLE_BASE = "https://apps.irs.gov/pub/epostcard/990/xml"


def insert_edges(conn, edges):
    conn.executemany(
        "INSERT INTO grants VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(e.funder_ein, e.funder_name, e.funder_type, e.recipient_name,
          e.recipient_ein, e.recipient_city, e.recipient_state, e.purpose,
          e.amount, e.source, e.tax_year, e.resolved_score) for e in edges])
    conn.commit()


def load_bundle(conn, directory):
    total = 0
    for path in sorted(glob.glob(os.path.join(directory, "*.xml"))):
        try:
            edges = parse_filing(path)
        except ET.ParseError:
            continue
        if edges:
            insert_edges(conn, edges)
            total += len(edges)
    return total


def download_bundle(year, filename, dest, fetch=requests.get):
    r = fetch(f"{BUNDLE_BASE}/{year}/{filename}", stream=True, timeout=300)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(1 << 20):
            fh.write(chunk)
    return dest
