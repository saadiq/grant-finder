# Grant Funder Prospector (Pilot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python pipeline + CLI that, given a nonprofit's name, finds funders who give to similar organizations by reconstructing the recipient→funder view from IRS 990 grant records, validated on Our Kids Read.

**Architecture:** A small Python package (`funder_prospector`) over a local SQLite index. ProPublica supplies the org profile and peer list; IRS XML bundles supply grant edges; the IRS BMF resolves grant recipients to EIN/NTEE. The testable core (parsers, fuzzy resolver, match, rank, report) is built TDD with fixtures; network I/O (HTTP GET, bundle download) is thin and injected so it stays out of unit tests.

**Tech Stack:** Python 3.11+, `uv` for env/deps, stdlib `sqlite3` + `xml.etree.ElementTree`, `requests` (HTTP), `rapidfuzz` (fuzzy matching), `pytest`.

## Global Constraints

- Python `>=3.11`. Manage env/deps with `uv` only — never `pip`. Run tests with `uv run pytest`.
- Max 300 lines per file, max 100 lines per function (project rule).
- SQLite via stdlib `sqlite3`; `conn.row_factory = sqlite3.Row` everywhere.
- Network functions take an injectable `fetch`/`searcher` param defaulting to the real client, so unit tests never hit the network.
- The canonical grant `GrantEdge` field order and the `grants`/`orgs` table column order defined in Task 1 are fixed — every later task depends on them.
- End every git commit message with a footer line:
  `Claude-Session: https://claude.ai/code/session_01RuecCescvhqYoX1HXaVp5Z`
- IRS bundle base URL: `https://apps.irs.gov/pub/epostcard/990/xml/{year}/{filename}`. ProPublica API base: `https://projects.propublica.org/nonprofits/api/v2`.

---

## File Structure

```
pyproject.toml                         # uv project + deps + pytest config
src/funder_prospector/
  __init__.py
  models.py            # dataclasses: OrgProfile, Peer, GrantEdge, FunderProspect
  db.py                # schema, connect(), init_db(), create_indexes()
  ingest.py            # parse_filing(), insert_edges(), load_bundle(), download_bundle()
  bmf.py               # load_bmf_csv(), download_bmf(), resolve(), resolve_pf_recipients()
  match.py             # find_funder_edges(), find_edges_by_ntee()
  rank.py              # rank_funders()
  report.py            # render()
  propublica.py        # parse_org(), parse_search(), get_org(), search(), find_peers()
  pipeline.py          # run_prospect()
  cli.py               # `prospect setup` / `prospect run`
tests/
  fixtures/990pf.xml, 990schedi.xml, org.json, search.json, bmf_sample.csv
  test_db.py test_ingest.py test_bmf.py test_match.py test_rank.py
  test_report.py test_propublica.py test_pipeline.py
scripts/build_index.py                 # existing single-bundle PoC (reference only)
```

---

### Task 1: Project scaffold, models, DB schema

**Files:**
- Create: `pyproject.toml`, `src/funder_prospector/__init__.py`, `src/funder_prospector/models.py`, `src/funder_prospector/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: dataclasses `OrgProfile`, `Peer`, `GrantEdge`, `FunderProspect`; `db.connect(path)->Connection`, `db.init_db(path)->Connection`, `db.create_indexes(conn)->None`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "funder-prospector"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.31", "rapidfuzz>=3.6"]

[project.scripts]
prospect = "funder_prospector.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/funder_prospector"]

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

The `[project.scripts]` entry point references `cli.py`, which is created in Task 11; the
reference is metadata only and does not need to resolve until the CLI is invoked, so
declaring it here is safe.

- [ ] **Step 2: Create the package + models**

`src/funder_prospector/__init__.py`: empty file.

`src/funder_prospector/models.py`:
```python
from dataclasses import dataclass


@dataclass
class OrgProfile:
    ein: str
    name: str
    ntee: str
    city: str
    state: str
    revenue: int | None


@dataclass
class Peer:
    ein: str
    name: str
    ntee: str
    city: str
    state: str


@dataclass
class GrantEdge:
    funder_ein: str
    funder_name: str
    funder_type: str          # '990PF' | '990' | '990EZ'
    recipient_name: str
    recipient_ein: str        # '' when unknown (always '' at parse time for 990-PF)
    recipient_city: str
    recipient_state: str
    purpose: str
    amount: int | None
    source: str               # 'PF-grant' | 'SchedI'
    tax_year: int | None
    resolved_score: float | None


@dataclass
class FunderProspect:
    funder_ein: str
    funder_name: str
    funder_type: str
    n_peers: int
    total_amount: int
    recent_year: int | None
    purposes: list[str]
    score: float
```

- [ ] **Step 3: Create `db.py`**

```python
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS grants(
  funder_ein TEXT, funder_name TEXT, funder_type TEXT,
  recipient_name TEXT, recipient_ein TEXT, recipient_city TEXT, recipient_state TEXT,
  purpose TEXT, amount INTEGER, source TEXT, tax_year INTEGER, resolved_score REAL
);
CREATE TABLE IF NOT EXISTS orgs(
  ein TEXT PRIMARY KEY, name TEXT, ntee TEXT, city TEXT, state TEXT,
  asset_amt INTEGER, income_amt INTEGER, revenue_amt INTEGER,
  foundation_code TEXT, subsection TEXT
);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def create_indexes(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_grants_rein ON grants(recipient_ein)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orgs_state_name ON orgs(state, name)")
    conn.commit()
```

- [ ] **Step 4: Write the failing test** — `tests/test_db.py`

```python
from funder_prospector import db


def test_init_db_creates_tables_and_roundtrips():
    conn = db.init_db(":memory:")
    conn.execute("INSERT INTO grants (funder_ein, amount) VALUES ('1', 5)")
    conn.execute("INSERT INTO orgs (ein, name) VALUES ('9', 'X')")
    conn.commit()
    db.create_indexes(conn)
    g = conn.execute("SELECT amount FROM grants").fetchone()
    o = conn.execute("SELECT name FROM orgs").fetchone()
    assert g["amount"] == 5 and o["name"] == "X"
```

- [ ] **Step 5: Run it** — `uv run pytest tests/test_db.py -v` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/funder_prospector tests/test_db.py
git commit -m "feat: scaffold package, models, and sqlite schema"
```

---

### Task 2: Ingest — parse a single filing

**Files:**
- Create: `src/funder_prospector/ingest.py`, `tests/fixtures/990pf.xml`, `tests/fixtures/990schedi.xml`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `GrantEdge` (Task 1).
- Produces: `ingest.parse_filing(path)->list[GrantEdge]`. 990-PF edges have `recipient_ein=''`, `source='PF-grant'`; 990/990EZ edges have `source='SchedI'` and amount = cash+noncash.

- [ ] **Step 1: Create fixtures**

`tests/fixtures/990pf.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<Return xmlns="http://www.irs.gov/efile">
  <ReturnHeader>
    <TaxPeriodEndDt>2022-11-30</TaxPeriodEndDt>
    <ReturnTypeCd>990PF</ReturnTypeCd>
    <Filer><EIN>386571896</EIN>
      <BusinessName><BusinessNameLine1Txt>TEST TRUST</BusinessNameLine1Txt></BusinessName></Filer>
  </ReturnHeader>
  <ReturnData><IRS990PF><SupplementaryInformationGrp>
    <GrantOrContributionPdDurYrGrp>
      <RecipientBusinessName><BusinessNameLine1Txt>READ ALLIANCE</BusinessNameLine1Txt></RecipientBusinessName>
      <RecipientUSAddress><CityNm>NEW YORK</CityNm><StateAbbreviationCd>NY</StateAbbreviationCd></RecipientUSAddress>
      <GrantOrContributionPurposeTxt>YOUTH LITERACY</GrantOrContributionPurposeTxt>
      <Amt>5000</Amt>
    </GrantOrContributionPdDurYrGrp>
  </SupplementaryInformationGrp></IRS990PF></ReturnData>
</Return>
```

`tests/fixtures/990schedi.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<Return xmlns="http://www.irs.gov/efile">
  <ReturnHeader>
    <TaxPeriodEndDt>2023-06-30</TaxPeriodEndDt>
    <ReturnTypeCd>990</ReturnTypeCd>
    <Filer><EIN>592116568</EIN>
      <BusinessName><BusinessNameLine1Txt>TEST CHARITY</BusinessNameLine1Txt></BusinessName></Filer>
  </ReturnHeader>
  <ReturnData><IRS990ScheduleI>
    <RecipientTable>
      <RecipientBusinessName><BusinessNameLine1Txt>FOOTHILLS INDUSTRIES</BusinessNameLine1Txt></RecipientBusinessName>
      <RecipientEIN>581309309</RecipientEIN>
      <USAddress><CityNm>MARION</CityNm><StateAbbreviationCd>NC</StateAbbreviationCd></USAddress>
      <PurposeOfGrantTxt>PRODUCTION EQUIPMENT</PurposeOfGrantTxt>
      <CashGrantAmt>47459</CashGrantAmt>
      <NonCashAssistanceAmt>580600</NonCashAssistanceAmt>
    </RecipientTable>
  </IRS990ScheduleI></ReturnData>
</Return>
```

- [ ] **Step 2: Write the failing test** — `tests/test_ingest.py`

```python
from pathlib import Path
from funder_prospector import ingest

FIX = Path(__file__).parent / "fixtures"


def test_parse_990pf_grant():
    edges = ingest.parse_filing(str(FIX / "990pf.xml"))
    assert len(edges) == 1
    e = edges[0]
    assert e.funder_ein == "386571896" and e.funder_type == "990PF"
    assert e.recipient_name == "READ ALLIANCE" and e.recipient_ein == ""
    assert e.recipient_state == "NY" and e.amount == 5000
    assert e.source == "PF-grant" and e.tax_year == 2022


def test_parse_990_schedule_i_grant():
    edges = ingest.parse_filing(str(FIX / "990schedi.xml"))
    assert len(edges) == 1
    e = edges[0]
    assert e.recipient_ein == "581309309" and e.source == "SchedI"
    assert e.amount == 47459 + 580600 and e.tax_year == 2023
```

- [ ] **Step 3: Run it** — `uv run pytest tests/test_ingest.py -v` — Expected: FAIL (`module ... has no attribute 'parse_filing'`).

- [ ] **Step 4: Implement `parse_filing` in `ingest.py`**

```python
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
```

- [ ] **Step 5: Run it** — `uv run pytest tests/test_ingest.py -v` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/funder_prospector/ingest.py tests/test_ingest.py tests/fixtures/990pf.xml tests/fixtures/990schedi.xml
git commit -m "feat: parse 990-PF and Schedule I grant records into GrantEdge"
```

---

### Task 3: Ingest — load a bundle into SQLite + download wrapper

**Files:**
- Modify: `src/funder_prospector/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `parse_filing` (Task 2), `db` (Task 1).
- Produces: `ingest.insert_edges(conn, edges)->None`; `ingest.load_bundle(conn, directory)->int` (returns edges inserted, skips unparseable files); `ingest.download_bundle(year, filename, dest, fetch=requests.get)->str`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_ingest.py`

```python
import shutil
from funder_prospector import db


def test_load_bundle_inserts_edges(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    shutil.copy(FIX / "990pf.xml", bundle / "a_public.xml")
    shutil.copy(FIX / "990schedi.xml", bundle / "b_public.xml")
    (bundle / "junk_public.xml").write_text("not xml")
    conn = db.init_db(":memory:")
    n = ingest.load_bundle(conn, str(bundle))
    assert n == 2
    rows = conn.execute("SELECT source FROM grants ORDER BY source").fetchall()
    assert [r["source"] for r in rows] == ["PF-grant", "SchedI"]
```

- [ ] **Step 2: Run it** — `uv run pytest tests/test_ingest.py::test_load_bundle_inserts_edges -v` — Expected: FAIL.

- [ ] **Step 3: Implement in `ingest.py`** (append; add `import requests` at top)

```python
import requests

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
```

- [ ] **Step 4: Run it** — `uv run pytest tests/test_ingest.py -v` — Expected: PASS (all ingest tests).

- [ ] **Step 5: Commit**

```bash
git add src/funder_prospector/ingest.py tests/test_ingest.py
git commit -m "feat: load a bundle directory into the grants table"
```

---

### Task 4: BMF loader

**Files:**
- Create: `src/funder_prospector/bmf.py`, `tests/fixtures/bmf_sample.csv`
- Test: `tests/test_bmf.py`

**Interfaces:**
- Consumes: `db` (Task 1).
- Produces: `bmf.load_bmf_csv(conn, csv_path)->int`; `bmf.download_bmf(dest, fetch=requests.get)->list[str]`.

- [ ] **Step 1: Create `tests/fixtures/bmf_sample.csv`** (real BMF header subset)

```csv
EIN,NAME,CITY,STATE,FOUNDATION,SUBSECTION,ASSET_AMT,INCOME_AMT,REVENUE_AMT,NTEE_CD
133957095,READ ALLIANCE,NEW YORK,NY,15,03,250000,400000,400000,B92
581309309,FOOTHILLS INDUSTRIES INC,MARION,NC,16,03,1200000,900000,900000,P70
000000001,UNRELATED ORG,DALLAS,TX,04,03,50,50,50,T20
```

- [ ] **Step 2: Write the failing test** — `tests/test_bmf.py`

```python
from pathlib import Path
from funder_prospector import bmf, db

FIX = Path(__file__).parent / "fixtures"


def test_load_bmf_csv():
    conn = db.init_db(":memory:")
    n = bmf.load_bmf_csv(conn, str(FIX / "bmf_sample.csv"))
    assert n == 3
    row = conn.execute("SELECT ntee, city FROM orgs WHERE ein='133957095'").fetchone()
    assert row["ntee"] == "B92" and row["city"] == "NEW YORK"
```

- [ ] **Step 3: Run it** — `uv run pytest tests/test_bmf.py -v` — Expected: FAIL.

- [ ] **Step 4: Implement loader in `bmf.py`**

```python
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
```

- [ ] **Step 5: Run it** — `uv run pytest tests/test_bmf.py -v` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/funder_prospector/bmf.py tests/test_bmf.py tests/fixtures/bmf_sample.csv
git commit -m "feat: load IRS BMF extracts into orgs table"
```

---

### Task 5: BMF resolver + 990-PF recipient resolution

**Files:**
- Modify: `src/funder_prospector/bmf.py`
- Test: `tests/test_bmf.py`

**Interfaces:**
- Consumes: `orgs` table (Task 4), `grants` table (Task 1), `rapidfuzz`.
- Produces: `bmf.resolve(conn, name, city, state, threshold=88)->tuple[str|None, float]` (returns `(ein, score)` if best fuzzy score ≥ threshold, else `(None, best_score)`); `bmf.resolve_pf_recipients(conn, threshold=88)->int` (fills `recipient_ein`/`resolved_score` for `source='PF-grant'` rows with empty EIN; returns count resolved).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_bmf.py`

```python
from funder_prospector.models import GrantEdge
from funder_prospector import ingest


def _seed_orgs(conn):
    bmf.load_bmf_csv(conn, str(FIX / "bmf_sample.csv"))


def test_resolve_matches_despite_name_variation():
    conn = db.init_db(":memory:")
    _seed_orgs(conn)
    ein, score = bmf.resolve(conn, "READ ALLIANCE", "NEW YORK", "NY")
    assert ein == "133957095" and score >= 88


def test_resolve_returns_none_below_threshold():
    conn = db.init_db(":memory:")
    _seed_orgs(conn)
    ein, _ = bmf.resolve(conn, "COMPLETELY DIFFERENT THING", "NEW YORK", "NY")
    assert ein is None


def test_resolve_pf_recipients_fills_ein():
    conn = db.init_db(":memory:")
    _seed_orgs(conn)
    ingest.insert_edges(conn, [GrantEdge(
        "999", "F", "990PF", "READ ALLIANCE", "", "NEW YORK", "NY",
        "LITERACY", 5000, "PF-grant", 2022, None)])
    assert bmf.resolve_pf_recipients(conn) == 1
    row = conn.execute("SELECT recipient_ein FROM grants").fetchone()
    assert row["recipient_ein"] == "133957095"
```

- [ ] **Step 2: Run it** — `uv run pytest tests/test_bmf.py -k resolve -v` — Expected: FAIL.

- [ ] **Step 3: Implement in `bmf.py`** (append; add `from rapidfuzz import fuzz` at top)

```python
from rapidfuzz import fuzz


def _block_token(name):
    parts = name.upper().replace("THE ", "", 1).split()
    return parts[0] if parts else ""


def resolve(conn, name, city, state, threshold=88):
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
```

- [ ] **Step 4: Run it** — `uv run pytest tests/test_bmf.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/funder_prospector/bmf.py tests/test_bmf.py
git commit -m "feat: fuzzy-resolve 990-PF recipients to EIN via BMF"
```

---

### Task 6: Match — find funder edges for a peer set

**Files:**
- Create: `src/funder_prospector/match.py`
- Test: `tests/test_match.py`

**Interfaces:**
- Consumes: `grants` + `orgs` tables.
- Produces: `match.find_funder_edges(conn, peer_eins: list[str])->list[sqlite3.Row]` (grant rows whose `recipient_ein` is in `peer_eins` and `amount` is not null); `match.find_edges_by_ntee(conn, ntee_prefixes: list[str])->list[sqlite3.Row]` (grant rows whose resolved recipient's BMF NTEE starts with any prefix). Both result sets include a `rowid` column so the pipeline (Task 10) can union them and drop duplicates (a grant that is both a peer match and an NTEE match).

- [ ] **Step 1: Write the failing test** — `tests/test_match.py`

```python
from funder_prospector import db, match, bmf, ingest
from funder_prospector.models import GrantEdge
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def _seed(conn):
    bmf.load_bmf_csv(conn, str(FIX / "bmf_sample.csv"))
    ingest.insert_edges(conn, [
        GrantEdge("F1", "Funder One", "990", "Read Alliance", "133957095",
                  "NEW YORK", "NY", "literacy", 10000, "SchedI", 2023, None),
        GrantEdge("F2", "Funder Two", "990PF", "Unrelated Org", "000000001",
                  "DALLAS", "TX", "general", 2000, "PF-grant", 2022, 95.0),
    ])


def test_find_funder_edges_by_ein():
    conn = db.init_db(":memory:")
    _seed(conn)
    rows = match.find_funder_edges(conn, ["133957095"])
    assert len(rows) == 1 and rows[0]["funder_ein"] == "F1"


def test_find_edges_by_ntee_prefix():
    conn = db.init_db(":memory:")
    _seed(conn)
    rows = match.find_edges_by_ntee(conn, ["B"])  # education
    assert [r["funder_ein"] for r in rows] == ["F1"]
```

- [ ] **Step 2: Run it** — `uv run pytest tests/test_match.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement `match.py`**

```python
def find_funder_edges(conn, peer_eins):
    if not peer_eins:
        return []
    placeholders = ",".join("?" * len(peer_eins))
    q = (f"SELECT rowid, * FROM grants WHERE recipient_ein IN ({placeholders}) "
         "AND amount IS NOT NULL")
    return conn.execute(q, peer_eins).fetchall()


def find_edges_by_ntee(conn, ntee_prefixes):
    if not ntee_prefixes:
        return []
    clause = " OR ".join("o.ntee LIKE ?" for _ in ntee_prefixes)
    q = ("SELECT g.rowid AS rowid, g.* FROM grants g JOIN orgs o ON g.recipient_ein = o.ein "
         f"WHERE g.amount IS NOT NULL AND ({clause})")
    return conn.execute(q, [p + "%" for p in ntee_prefixes]).fetchall()
```

- [ ] **Step 4: Run it** — `uv run pytest tests/test_match.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/funder_prospector/match.py tests/test_match.py
git commit -m "feat: match funders by peer EIN and by recipient NTEE"
```

---

### Task 7: Rank — aggregate edges into scored prospects

**Files:**
- Create: `src/funder_prospector/rank.py`
- Test: `tests/test_rank.py`

**Interfaces:**
- Consumes: grant rows (Task 6 output, `sqlite3.Row` with keys `funder_ein, funder_name, funder_type, recipient_ein, amount, tax_year, purpose`), `FunderProspect` (Task 1).
- Produces: `rank.rank_funders(edges)->list[FunderProspect]`, sorted by `score` descending. `n_peers` = distinct `recipient_ein`; `score = n_peers*10 + log10(total+1)*2 + (recent_year or 0)*0.01`.

- [ ] **Step 1: Write the failing test** — `tests/test_rank.py`

```python
from funder_prospector import db, rank, ingest
from funder_prospector.models import GrantEdge


def _rows(conn):
    return conn.execute("SELECT * FROM grants").fetchall()


def test_rank_orders_more_peers_first():
    conn = db.init_db(":memory:")
    ingest.insert_edges(conn, [
        GrantEdge("BIG", "Big Funder", "990", "A", "111", "", "NY", "x", 1000, "SchedI", 2023, None),
        GrantEdge("BIG", "Big Funder", "990", "B", "222", "", "NY", "y", 1000, "SchedI", 2022, None),
        GrantEdge("SMALL", "Small Funder", "990PF", "A", "111", "", "NY", "z", 9000, "PF-grant", 2021, None),
    ])
    prospects = rank.rank_funders(_rows(conn))
    assert prospects[0].funder_ein == "BIG"
    assert prospects[0].n_peers == 2 and prospects[0].total_amount == 2000
    assert prospects[0].recent_year == 2023
```

- [ ] **Step 2: Run it** — `uv run pytest tests/test_rank.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement `rank.py`**

```python
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
```

- [ ] **Step 4: Run it** — `uv run pytest tests/test_rank.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/funder_prospector/rank.py tests/test_rank.py
git commit -m "feat: aggregate grant edges into ranked funder prospects"
```

---

### Task 8: Report — render the prospect list

**Files:**
- Create: `src/funder_prospector/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `list[FunderProspect]` (Task 7), `OrgProfile` (Task 1).
- Produces: `report.render(prospects, applicant)->str` (markdown). Each prospect block includes funder name, type, EIN, peer count, total `$`, recent year, purposes, and a ProPublica link.

- [ ] **Step 1: Write the failing test** — `tests/test_report.py`

```python
from funder_prospector import report
from funder_prospector.models import FunderProspect, OrgProfile


def test_render_contains_funder_and_amount():
    applicant = OrgProfile("833401365", "Our Kids Read", "B90", "Laurel", "MD", 311838)
    prospects = [FunderProspect("F1", "Battin Foundation", "990PF", 2, 210000,
                                2022, ["YOUTH LITERACY"], 24.3)]
    md = report.render(prospects, applicant)
    assert "Our Kids Read" in md
    assert "Battin Foundation" in md
    assert "$210,000" in md
    assert "F1" in md and "YOUTH LITERACY" in md
```

- [ ] **Step 2: Run it** — `uv run pytest tests/test_report.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement `report.py`**

```python
PP = "https://projects.propublica.org/nonprofits/organizations"


def render(prospects, applicant):
    lines = [
        f"# Funder prospects for {applicant.name}",
        f"_{applicant.ntee} · {applicant.city}, {applicant.state}_",
        "",
        f"{len(prospects)} funders gave to organizations like this one.",
        "",
    ]
    for p in prospects:
        lines.append(f"## {p.funder_name} ({p.funder_type}, EIN {p.funder_ein})")
        lines.append(f"- funded **{p.n_peers}** peer org(s); total **${p.total_amount:,}**; "
                     f"most recent tax year {p.recent_year or 'n/a'}")
        if p.purposes:
            lines.append(f"- purposes: {'; '.join(p.purposes)}")
        lines.append(f"- {PP}/{p.funder_ein}")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run it** — `uv run pytest tests/test_report.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/funder_prospector/report.py tests/test_report.py
git commit -m "feat: render ranked prospects as markdown"
```

---

### Task 9: ProPublica client — profile + peer discovery

**Files:**
- Create: `src/funder_prospector/propublica.py`, `tests/fixtures/org.json`, `tests/fixtures/search.json`
- Test: `tests/test_propublica.py`

**Interfaces:**
- Consumes: `OrgProfile`, `Peer` (Task 1).
- Produces: `propublica.parse_org(d)->OrgProfile`; `propublica.parse_search(d)->list[Peer]`; `propublica.get_org(ein, fetch=requests.get)->OrgProfile`; `propublica.search(q, ntee_id=None, state=None, page=0, fetch=requests.get)->list[Peer]`; `propublica.find_peers(profile, keywords=("reading","literacy"), ntee_prefixes=("B",), cap=150, searcher=search)->list[Peer]` (deduped by EIN, excludes the applicant, keeps only NTEE codes starting with a given prefix).

- [ ] **Step 1: Create fixtures** (trimmed real shapes)

`tests/fixtures/org.json`:
```json
{"organization": {"ein": 833401365, "name": "Our Kids Read Association",
  "ntee_code": "B90", "city": "Laurel", "state": "MD", "revenue_amount": 656402},
 "filings_with_data": [{"tax_prd_yr": 2023, "totrevenue": 311838}]}
```

`tests/fixtures/search.json`:
```json
{"total_results": 3, "organizations": [
  {"ein": 133957095, "name": "Read Alliance", "raw_ntee_code": "B92", "city": "New York", "state": "NY"},
  {"ein": 591234567, "name": "Some Food Bank", "raw_ntee_code": "K31", "city": "Miami", "state": "FL"},
  {"ein": 833401365, "name": "Our Kids Read Association", "raw_ntee_code": "B90", "city": "Laurel", "state": "MD"}
]}
```

- [ ] **Step 2: Write the failing test** — `tests/test_propublica.py`

```python
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
```

- [ ] **Step 3: Run it** — `uv run pytest tests/test_propublica.py -v` — Expected: FAIL.

- [ ] **Step 4: Implement `propublica.py`**

```python
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
```

- [ ] **Step 5: Run it** — `uv run pytest tests/test_propublica.py -v` — Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/funder_prospector/propublica.py tests/test_propublica.py tests/fixtures/org.json tests/fixtures/search.json
git commit -m "feat: ProPublica client for org profile and peer discovery"
```

---

### Task 10: Pipeline orchestration

**Files:**
- Create: `src/funder_prospector/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `match`, `rank`, `report` (Tasks 6–8), `OrgProfile`, `Peer`.
- Produces: `pipeline.run_prospect(conn, profile, peers, ntee_prefixes=None)->str` — unions exact peer-EIN matches (`find_funder_edges`) with NTEE-widened matches (`find_edges_by_ntee`), dedups by `rowid`, ranks, and renders. When `ntee_prefixes` is None it defaults to the distinct NTEE codes of the peers, so widening targets the peers' specific literacy/education codes (e.g. B92), not all of Education. Pure given a built `conn` (no network).

- [ ] **Step 1: Write the failing test** — `tests/test_pipeline.py`

```python
from pathlib import Path
from funder_prospector import db, bmf, ingest, pipeline
from funder_prospector.models import GrantEdge, OrgProfile, Peer

FIX = Path(__file__).parent / "fixtures"


def test_run_prospect_unions_peer_and_ntee_matches():
    conn = db.init_db(":memory:")
    bmf.load_bmf_csv(conn, str(FIX / "bmf_sample.csv"))
    # a second B92 (literacy) org that is NOT in the peer list
    conn.execute("INSERT INTO orgs (ein, name, ntee, state) VALUES ('222','OTHER LITERACY','B92','NY')")
    conn.commit()
    ingest.insert_edges(conn, [
        GrantEdge("F1", "Battin Foundation", "990PF", "READ ALLIANCE", "133957095",
                  "NEW YORK", "NY", "YOUTH LITERACY", 210000, "PF-grant", 2022, 95.0),
        GrantEdge("F2", "Other Funder", "990", "OTHER LITERACY", "222",
                  "NEW YORK", "NY", "READING", 5000, "SchedI", 2023, None),
    ])
    profile = OrgProfile("833401365", "Our Kids Read", "B90", "Laurel", "MD", 311838)
    peers = [Peer("133957095", "Read Alliance", "B92", "New York", "NY")]
    md = pipeline.run_prospect(conn, profile, peers)
    assert "Battin Foundation" in md and "$210,000" in md   # exact peer-EIN match
    assert "Other Funder" in md                              # NTEE-widened (B92), not a peer EIN
```

- [ ] **Step 2: Run it** — `uv run pytest tests/test_pipeline.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement `pipeline.py`**

```python
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
```

- [ ] **Step 4: Run it** — `uv run pytest tests/test_pipeline.py -v` — Expected: PASS.

- [ ] **Step 5: Run the full suite** — `uv run pytest -v` — Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/funder_prospector/pipeline.py tests/test_pipeline.py
git commit -m "feat: orchestrate match->rank->report pipeline"
```

---

### Task 11: CLI — `setup` and `run`

**Files:**
- Create: `src/funder_prospector/cli.py`

**Interfaces:**
- Consumes: `db`, `ingest`, `bmf`, `propublica`, `pipeline`. The `prospect` console script entry point (`funder_prospector.cli:main`) was already declared in `pyproject.toml` in Task 1.
- Produces: `prospect setup --db PATH --bmf-dir DIR --bundle-dir DIR` (load BMF dir + bundle dir already on disk → build index + resolve + index); `prospect run --db PATH "Org Name" [--state XX]` (profile + peers via ProPublica → prints report).

This task wraps already-tested functions in argparse; it is verified by the manual run in Task 12 rather than a unit test (it is pure I/O glue).

- [ ] **Step 1: Implement `cli.py`**

```python
import argparse
import glob
import os

from . import bmf, db, ingest, pipeline, propublica


def _setup(args):
    conn = db.init_db(args.db)
    for csv_path in sorted(glob.glob(os.path.join(args.bmf_dir, "*.csv"))):
        print("BMF:", csv_path, bmf.load_bmf_csv(conn, csv_path))
    n = ingest.load_bundle(conn, args.bundle_dir)
    print("grant edges:", n)
    print("resolved PF recipients:", bmf.resolve_pf_recipients(conn))
    db.create_indexes(conn)


def _run(args):
    conn = db.connect(args.db)
    peers = propublica.search(args.name, state=args.state)
    profile = peers[0] if peers else None
    if profile is None:
        raise SystemExit(f"no org found for {args.name!r}")
    prof = propublica.get_org(profile.ein)
    peer_list = propublica.find_peers(prof)
    print(pipeline.run_prospect(conn, prof, peer_list))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="prospect")
    sub = ap.add_subparsers(required=True)
    s = sub.add_parser("setup")
    s.add_argument("--db", required=True)
    s.add_argument("--bmf-dir", required=True)
    s.add_argument("--bundle-dir", required=True)
    s.set_defaults(func=_setup)
    r = sub.add_parser("run")
    r.add_argument("--db", required=True)
    r.add_argument("name")
    r.add_argument("--state", default=None)
    r.set_defaults(func=_run)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test the console script**

Run: `uv run prospect --help`
Expected: argparse help text listing `setup` and `run`, exit code 0. (Installs the
package into the uv env on first run.)

- [ ] **Step 3: Commit**

```bash
git add src/funder_prospector/cli.py
git commit -m "feat: CLI for index setup and prospect run"
```

---

### Task 12: Pilot data build + Our Kids Read validation

**Files:**
- Create: `docs/pilot-run.md` (record of the run + evaluation), `SKILL.md` (how to invoke from Claude Code)
- Uses: a working data directory `data/` (git-ignored).

This task downloads the pilot slice, builds the index, runs on Our Kids Read, and records whether the success criterion is met. No unit test — this is the verification step.

- [ ] **Step 1: Fetch the pilot slice**

```bash
mkdir -p data/bundles data/bmf
# discover available bundle names for a recent year, take the first ~5
curl -s "https://www.irs.gov/charities-non-profits/form-990-series-downloads" \
  | grep -oE "[0-9]{4}_TEOS_XML_[0-9]{2}[A-Z]?\.zip" | sort -u | head
# download ~5 bundles + unzip into data/bundles (substitute real names/year)
# e.g.: curl -s -o data/b01.zip "https://apps.irs.gov/pub/epostcard/990/xml/2024/2024_TEOS_XML_01A.zip" && unzip -q data/b01.zip -d data/bundles
# download the 4 BMF regional extracts:
for u in eo1 eo2 eo3 eo4; do curl -s -o "data/bmf/$u.csv" "https://www.irs.gov/pub/irs-soi/$u.csv"; done
```

- [ ] **Step 2: Build the pilot index**

Run: `uv run prospect setup --db data/grants.db --bmf-dir data/bmf --bundle-dir "$(find data/bundles -maxdepth 1 -type d | tail -1)"`
Expected: prints BMF load counts, a grant-edge count in the tens of thousands per bundle, and a resolved-PF-recipients count > 0.

- [ ] **Step 3: Run on Our Kids Read**

Run: `uv run prospect run --db data/grants.db "Our Kids Read" --state MD`
Expected: a markdown prospect list prints, naming funders that gave to literacy/education peers.

- [ ] **Step 4: Evaluate against the spec's success criterion**

In `docs/pilot-run.md`, record: the peer list size, the top ~15 prospects, and a judgment — **is the list dominated by plausible youth-literacy / education funders with verifiable evidence (not name-match noise)?** Note the fuzzy `threshold` used and any obvious false positives. State whether it is worth scaling to a national / multi-year build.

- [ ] **Step 5: Write `SKILL.md`** documenting: prerequisites (`uv sync`), the two-step `setup` then `run` flow, the data caveats from the spec (1–2 yr lag, 990-PF fuzzy matching, "warm leads not application instructions"), and that re-running `setup` with more bundles widens coverage.

- [ ] **Step 6: Commit**

```bash
git add docs/pilot-run.md SKILL.md
git commit -m "docs: pilot run results and skill usage"
```

---

## Notes for the implementer

- The reference PoC `scripts/build_index.py` already proved the parser logic against a real bundle (21,513 filings → 42,917 edges). Use it to sanity-check `parse_filing` output on real data if a fixture-based test passes but real data looks off.
- The fuzzy `threshold` (default 88) and the peer NTEE net (`ntee_prefixes`, `keywords`) are the pilot's tuning knobs — expect to adjust them in Task 12 and record what you chose.
- Known pilot limitations (documented, not bugs): first-token blocking in `resolve` can miss recipients whose BMF name starts with a different word; `find_peers` uses keyword search rather than a pure NTEE-code scan; size-band filtering is not yet applied to peers.
