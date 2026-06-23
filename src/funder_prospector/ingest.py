import glob
import os
import xml.etree.ElementTree as ET

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
