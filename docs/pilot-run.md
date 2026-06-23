# Pilot Run — Our Kids Read (2026-06-23)

First end-to-end run of the funder prospector on real IRS data, for **Our Kids Read
Association** (EIN 83-3401365, NTEE B90, Laurel MD, youth literacy).

## What was built

- **Data slice:** 3 IRS 2023 e-file bundles (`2023_TEOS_XML_01A/02A/03A`) = 98,041
  filings → **256,259 grant edges** (142,392 from 990-PF, 113,867 from Schedule I).
- **BMF:** national EO Business Master File, **1,974,830 orgs**.
- **990-PF recipient resolution:** 60,748 of 142,392 PF grants resolved to a BMF EIN via
  fuzzy match = **43%**. (Schedule I grants carry EINs natively.)
- Index build time: ~11 min one-time (dominated by the ~140k fuzzy PF lookups).
- All 18 unit tests green.

## Result against the success criterion

**Criterion:** "the prospect list for Our Kids Read is dominated by plausible
youth-literacy / education funders (not name-match noise), with verifiable evidence."

**Verdict: NOT met by the naive pipeline — but the fix direction is validated.** The
pipeline runs cleanly end-to-end and the signal is present, but the default ranking
surfaces the wrong funders first.

### Raw top of list (broken)

The naive run returned **2,570 funders**, topped by donor-advised-fund (DAF)
pass-through sponsors, not targetable literacy funders:

| Funder | "peers" funded | total | reality |
|---|---|---|---|
| American Online Giving Foundation | **1,945** | $103.9M | Meta/Facebook DAF — funds everything |
| Charities Aid Foundation America | 382 | $19.3M | DAF |
| Jewish Communal Fund | 209 | $76.0M | DAF |
| The Blackbaud Giving Fund | 125 | $24.1M | DAF |
| Raymond James Charitable Endowment | 86 | $4.5M | DAF |

These are **not prospects you can apply to** — individual donors direct them.

## Root causes (diagnosed)

1. **NTEE-widening is far too broad.** `find_peers` returned 50 peers spanning **15
   different NTEE codes** — only B92/B92Z (21 peers) are literacy-specific; the rest
   include **B90 "Educational Services" (22,849 BMF orgs!)**, B60 (adult ed), B80
   (student services), and infrastructure codes B01/B03/B05. Widening on that whole set
   matched **9,589 edges** vs only **33** exact peer-EIN edges — the over-broad widening
   does ~99% of the matching, dragging in every education grant.
   - B90* = 22,849 BMF orgs; **B92\* (literacy) = 1,666** — narrowing cuts noise ~14×.
2. **DAFs dominate and the ranking rewards them.** Score = `n_peers*10 + …`, so the
   broadest funders (DAFs that give to thousands of orgs) float to the top — exactly
   backwards for finding targeted funders.

## Fix direction (validated)

Restricting recipients to literacy-specific NTEE (B92\*) and dropping mega-breadth
funders produced a genuinely useful list:

| peers | total | type | funder | purpose |
|---|---|---|---|---|
| 6 | $83,400 | 990 | **Reading Is Fundamental** | TO FOSTER LITERACY |
| 5 | $381,381 | 990 | **Greater Washington Community Foundation** | GENERAL SUPPORT |
| 4 | $231,458 | 990 | Arizona Community Foundation | PROGRAM SUPPORT |
| 3 | $39,000 | 990 | Rochester Area Community Foundation | RX FOR EARLY LITERACY |
| 3 | $35,000 | 990 | National Book Foundation | LITERARY ARTS |
| 2 | $135,000 | 990PF | The McKnight Foundation | equip parents as educational advocates |
| 2 | $27,132 | 990 | Coaching for Literacy | LITERACY INTERVENTION |
| 2 | $26,601 | 990 | United Way of the National Capital Area | DC-area, near OKR |

These are real, targetable youth-literacy funders — **Greater Washington Community
Foundation** is especially notable (OKR is in MD, in its service area). (Charities Aid
Foundation still slipped in at 14 — confirming a breadth cutoff alone is insufficient;
DAF exclusion needs a maintained list.)

## Recommended changes before scaling to national / multi-year

1. **Tighten NTEE-widening to cause-specific codes** (e.g. B92 literacy), not the full
   scatter of peer codes — drop broad catch-alls (B90, B99) and infrastructure codes
   (B01/B03/B05). Best: pick the dominant *specific* code among peers, not "any B".
2. **Exclude DAF / pass-through sponsors** via a maintained EIN/name list (Fidelity/
   Schwab/Vanguard Charitable, American Online Giving, Charities Aid Foundation, Jewish
   Communal Fund, Blackbaud Giving Fund, National Philanthropic Trust, Raymond James
   Charitable, community-foundation DAF arms, …). Breadth cutoff alone is not enough.
3. **Rank by fit, not breadth.** Weight purpose-keyword relevance (literacy/reading/
   early-childhood), grant-size fit to the applicant's budget (~$300k → $5–50k grants,
   not $100M DAFs), and geographic proximity. De-emphasize raw `n_peers`.

## Data caveats observed

- 990-PF fuzzy resolution is ~43% — many foundation grants never resolve to an EIN
  (name variations beyond first-token blocking, recipients absent from BMF, individuals).
  Improving the resolver (city tie-break, better blocking) would raise recall.
- 1–2 year data lag: this slice's filings are mostly tax years 2021–2022.
- Only a 3-bundle slice (~1/20th of a year); national coverage would surface more
  per-funder evidence and more local funders.

## Bottom line

The architecture is sound and worth scaling **once the three matching refinements above
are in**. The pilot did its job: it proved the pipeline on real data and converted "find
my funders" from a hypothesis into a concrete, evidence-backed tuning problem.
