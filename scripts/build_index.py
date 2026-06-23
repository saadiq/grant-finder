import os, glob, sqlite3, sys
import xml.etree.ElementTree as ET

NS = {'i': 'http://www.irs.gov/efile'}
SRC = sys.argv[1]
DB = sys.argv[2]

def gt(el, path):
    x = el.find(path, NS)
    return (x.text or '').strip() if x is not None else ''

def num(s):
    try:
        return int(float(s))
    except Exception:
        return None

con = sqlite3.connect(DB)
con.execute("DROP TABLE IF EXISTS grants")
con.execute("""CREATE TABLE grants(
  funder_ein TEXT, funder_name TEXT, funder_type TEXT,
  recipient_name TEXT, recipient_ein TEXT, recipient_city TEXT, recipient_state TEXT,
  purpose TEXT, amount INTEGER, source TEXT)""")

rows = []
files = glob.glob(os.path.join(SRC, '*.xml'))
for i, f in enumerate(files):
    try:
        r = ET.parse(f).getroot()
    except Exception:
        continue
    rtype = gt(r, './/i:ReturnTypeCd')
    fein = gt(r, './/i:Filer/i:EIN')
    fname = gt(r, './/i:Filer/i:BusinessName/i:BusinessNameLine1Txt')
    if rtype == '990PF':
        for g in r.findall('.//i:GrantOrContributionPdDurYrGrp', NS):
            name = gt(g, 'i:RecipientBusinessName/i:BusinessNameLine1Txt') or gt(g, 'i:RecipientPersonNm')
            rows.append((fein, fname, '990PF', name, '',
                         gt(g, 'i:RecipientUSAddress/i:CityNm'),
                         gt(g, 'i:RecipientUSAddress/i:StateAbbreviationCd'),
                         gt(g, 'i:GrantOrContributionPurposeTxt'),
                         num(gt(g, 'i:Amt')), 'PF-grant'))
    elif rtype in ('990', '990EZ'):
        for g in r.findall('.//i:RecipientTable', NS):
            cash = num(gt(g, 'i:CashGrantAmt')) or 0
            noncash = num(gt(g, 'i:NonCashAssistanceAmt')) or 0
            rows.append((fein, fname, rtype, gt(g, 'i:RecipientBusinessName/i:BusinessNameLine1Txt'),
                         gt(g, 'i:RecipientEIN'),
                         gt(g, 'i:USAddress/i:CityNm'),
                         gt(g, 'i:USAddress/i:StateAbbreviationCd'),
                         gt(g, 'i:PurposeOfGrantTxt') or gt(g, 'i:GrantOrAssistanceDesc'),
                         cash + noncash, 'SchedI'))

con.executemany("INSERT INTO grants VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
con.execute("CREATE INDEX idx_rein ON grants(recipient_ein)")
con.commit()
print(f"parsed {len(files)} filings -> {len(rows)} grant edges")
print("by source:", dict(con.execute("SELECT source, count(*) FROM grants GROUP BY source")))
con.close()
