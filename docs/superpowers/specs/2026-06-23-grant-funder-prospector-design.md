# Grant Funder Prospector — Design

**Date:** 2026-06-23
**Status:** Approved for pilot build
**First user:** Our Kids Read Association (EIN 83-3401365) — youth literacy, Laurel MD, NTEE B90

## Problem

A nonprofit wants to streamline grant writing by finding **funders who already give
to organizations like them**. The IRS 990 e-file data contains every grant made by
private foundations (990-PF) and grantmaking public charities (990 Schedule I), but it
is keyed by *funder* ("who did this foundation give to"), which is the inverse of the
question we need to answer ("who funds orgs like me"). The tool reconstructs the
recipient→funder view and ranks funders as prospects.

Solve it for one nonprofit; the pipeline is org-agnostic, so it serves any nonprofit by
changing only the input name.

## Key findings from data exploration (validated, not assumed)

These shaped the design and are the reason it looks the way it does:

1. **No free reverse index exists.** ProPublica's API exposes org profiles and
   financial totals but **no grant-level recipient data**. Commercial tools (Candid,
   Instrumentl) *are* the paid reverse index. To do this for free we parse grant records
   ourselves.
2. **You cannot find a org's funders from its own return.** Schedule B (donor list) is
   **redacted** in public data. Funders are only discoverable from the *funders'* grant
   records. This rules out every "just read the peer's 990" shortcut.
3. **EIN asymmetry is the central matching problem.** Schedule I grants carry the
   recipient **EIN** (clean join). 990-PF grants carry **name + city only, no EIN** —
   and that's where many small/regional literacy funders live. 990-PF recipients must be
   resolved to an EIN/NTEE via the BMF before they can be filtered.
4. **Never match on recipient name strings.** A demo `LIKE '%READ%'` query matched
   `B-R-E-A-D` (food banks: "Bread for the World", "Bread of Life") and the city
   "Reading, PA". Matching must be on **resolved identity (EIN → NTEE)**, never on name
   keywords.
5. **It is tractable.** One 123 MB bundle (21,513 filings) parsed to **42,917
   funder→recipient edges in ~10 seconds** → a 7 MB SQLite. A full year (~60 bundles) is
   ~2.5M edges / a few hundred MB / a few hours of local compute. **No servers** — the
   index is a local SQLite file, and it is the reusable asset across all future
   nonprofits.
6. **The signal is real.** That single random bundle already surfaced true peers of Our
   Kids Read being funded: *Reading Partners* and *Catch Up & Read* (Communities
   Foundation of Texas, 10 literacy recipients), *Read Alliance* (Battin Foundation,
   $210K), *Literacy Outreach of Garfield County* (Gardener Foundation).

## Data sources

| Source | Role | Access |
|---|---|---|
| ProPublica Nonprofit Explorer API | Org profile + peer discovery | Free, no auth |
| IRS 990 e-file XML bundles | The grant edges (990-PF line 3, 990 Schedule I) | `apps.irs.gov/pub/epostcard/990/xml/{year}/` ZIPs + `index_{year}.csv` |
| IRS EO Business Master File (BMF) | Recipient identity, NTEE, geo, size; resolves 990-PF recipients | `irs.gov/.../eo-bmf` monthly CSVs |

The old AWS `s3://irs-form-990` bucket is **empty/deprecated** — do not use it. There is
no per-filing HTTP endpoint; data comes only as year/month ZIP bundles.

## Architecture

Deliverable: a **Claude Code skill** that orchestrates small, single-purpose modules
over a **local SQLite** index.

Modules (each independently understandable/testable):

- **`propublica`** — org lookup by name → profile (EIN, NTEE, geo, size, mission text);
  peer search by NTEE + keywords + size band → peer list with EINs.
- **`ingest`** — download bundles + `index_{year}.csv`; parse 990-PF
  `GrantOrContributionPdDurYrGrp` and Schedule I `RecipientTable` → `grants` table.
  (Reference parser already written and validated: `scripts/build_index.py`.)
- **`bmf`** — load BMF → `orgs` table; expose a resolver `(name, city, state) → best EIN`
  (blocking on state + name token, fuzzy on name via rapidfuzz).
- **`match`** — given peer EINs + peer NTEE set, find funders: exact EIN join on
  Schedule I rows; resolver-backed join on 990-PF rows; optional widen to "any funder of
  this NTEE class."
- **`rank`** — aggregate by funder, score prospects.
- **`report`** — render a ranked markdown prospect list with evidence + links.

### Data model (SQLite)

```
grants(funder_ein, funder_name, funder_type,        -- funder_type: 990PF | 990 | 990EZ
       recipient_name, recipient_ein, recipient_city, recipient_state,
       purpose, amount, source, tax_year)            -- source: PF-grant | SchedI
orgs(ein, name, ntee, city, state,                   -- from BMF
     asset_amt, income_amt, revenue_amt, foundation_code, subsection)
```

### Pipeline (what the skill runs)

```
org name
  │  propublica.lookup
  ▼
profile {EIN, NTEE=B90, geo, size, mission}
  │  propublica.peers  (NTEE B90/B92 + literacy/reading keywords + size band)
  ▼
~50–200 peers [{name, EIN, NTEE, geo}]
  │  match
  ├─ Schedule I:  grants.recipient_ein ∈ peer EINs            (exact)
  └─ 990-PF:      bmf.resolve(recipient_name,city,state)→EIN, ∈ peers / peer NTEE (fuzzy)
  ▼
funder→peer edges
  │  rank + report
  ▼
ranked prospect list  [funder, type, location, #peers funded, $ range, recency,
                       purpose alignment, geo overlap, evidence rows, filing links]
```

### Ranking signals

Distinct peers (or same-NTEE orgs) funded · total/median grant size · most recent year ·
purpose keyword alignment (literacy/reading/education/youth) · geographic overlap with
the applicant · funder type · typical grant size vs. applicant's budget.

## Scope

**Pilot first (decided).** Ingest a small slice — ~5–10 bundles of one recent year —
load the national BMF, and run the **full** pipeline (including 990-PF→BMF fuzzy
resolution) on Our Kids Read. Judge whether the surfaced funders are genuinely useful
and tune the fuzzy-match threshold **before** committing to a multi-year national build.
Same code scales up by ingesting more bundles.

**Success criterion for the pilot:** the prospect list for Our Kids Read is dominated by
plausible youth-literacy / education funders (not name-match noise), with verifiable
evidence rows, and the operator judges it worth scaling.

## Non-goals (v1)

- Determining whether a funder accepts **unsolicited** proposals (not in the data; later
  enrichment from funder sites / Candid).
- Grants to **individuals** (never name recipients — unusable for prospecting).
- **Semantic** mission similarity via embeddings (v1 uses NTEE + keywords + size).
- Schedule F (foreign grants) and real-time data (filings lag 1–2 years).

## Risks / open questions

- **Fuzzy-match precision/recall** on 990-PF recipient→BMF is the main unknown — exactly
  what the pilot tests.
- **BMF NTEE coverage** is imperfect (blanks/stale); may need NCCS-enhanced BMF later.
- Which year for the pilot slice (most recent complete IRS release).
- Defining the peer **size band** and how wide to cast the NTEE net (B90 only vs. all
  B-education vs. literacy-specific B92).

## Validation evidence

- ProPublica lookup + profile of Our Kids Read: succeeded (EIN 83-3401365, B90, ~$312K
  TY2023 revenue).
- `scripts/build_index.py` on one 2023 bundle: 21,513 filings → 42,917 edges in ~10s,
  7 MB DB.
- Step-4 query surfaced real literacy funders/peers (above), and demonstrated the
  name-match failure mode that drives the EIN/NTEE-resolution requirement.
