---
name: funder-prospector
description: Find foundations and grantmaking charities that give to organizations like a given nonprofit, by reconstructing a recipient→funder view from IRS 990 e-file grant records. Use when a nonprofit wants a prospect list of likely funders. Requires a one-time local data build.
---

# Funder Prospector

Given a nonprofit's name, find funders who already give to **organizations like it** —
by parsing IRS 990 grant records (990-PF + Schedule I) into a local SQLite index, then
matching funders against the nonprofit's peers (by EIN) and cause (by NTEE code).

## Prerequisites

- Python ≥ 3.11 and `uv`.
- From the repo root: `uv sync` (installs deps + the `grant-finder` CLI into `.venv`).

## Two-step usage

### 1. Build the index (one-time, slow — hours for national coverage)

Download the data first (these are large; `data/` is git-ignored):

- **Bundles:** IRS 990 XML ZIPs from `https://apps.irs.gov/pub/epostcard/990/xml/{year}/`
  (e.g. `2023_TEOS_XML_01A.zip`). Unzip the XML files (flattened) into one directory.
- **BMF:** the four EO Business Master File extracts
  `https://www.irs.gov/pub/irs-soi/eo{1,2,3,4}.csv` into a directory.

Then build:

```bash
uv run grant-finder setup --db data/grants.db --bmf-dir data/bmf --bundle-dir data/bundles
```

This loads the BMF (org identity/NTEE/size), parses every filing's grant records into the
`grants` table, creates indexes, and fuzzy-resolves 990-PF recipients to EINs. The index
is the reusable asset — build once, query for any nonprofit. **Re-running `setup` with
more bundles widens coverage.**

### 2. Run a prospect search (fast)

```bash
uv run grant-finder run --db data/grants.db "Our Kids Read" --state MD
```

Looks the org up on ProPublica (profile + peers), queries the local index, and prints a
ranked markdown prospect list with evidence and filing links.

## Important caveats

- **Warm leads, not application instructions.** The output is "funders who demonstrably
  give to orgs like you." Whether a funder accepts *unsolicited* proposals is **not** in
  this data — verify on the funder's site before applying.
- **Donor-advised funds (DAFs) are noise.** Pass-through sponsors (Fidelity/Schwab/
  Vanguard Charitable, American Online Giving, Charities Aid Foundation, Jewish Communal
  Fund, Blackbaud Giving Fund, …) appear to "fund" thousands of orgs because individual
  donors direct them — they are not targetable and should be filtered/ignored.
- **NTEE-widening can over-broaden.** Matching on broad education codes (B90) pulls in
  unrelated orgs; cause-specific codes (B92 literacy) are far cleaner. See
  `docs/pilot-run.md`.
- **990-PF matching is fuzzy (~43% resolved).** Foundation grants carry no recipient EIN;
  they are name+city matched to the BMF, so coverage is partial. Schedule I joins are
  exact.
- **1–2 year data lag.** Filings appear well after the tax year.

## Status

Pilot validated end-to-end on real data (see `docs/pilot-run.md`). Three matching
refinements are recommended before relying on the ranked output: tighter cause-specific
NTEE targeting, DAF exclusion, and fit-based ranking (purpose relevance, grant-size fit,
geography) instead of raw breadth.
