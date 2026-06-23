# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`grant_finder` finds grant funders for a nonprofit by answering "who funds
organizations like me?" from IRS Form 990 e-file data. The hard part is that the source
data is **funder-keyed** (each filing is one funder's list of grants *out*), which is the
inverse of the question. The tool reconstructs a **recipient→funder** view and matches it
against a nonprofit's peers. See `docs/superpowers/specs/` for the design and
`docs/pilot-run.md` for validated results and current limitations.

## Commands

- Install / env: `uv sync` (uses `uv` exclusively — never `pip`). The `grant-finder` console
  script installs into `.venv`.
- All tests: `uv run pytest -q`
- Single test: `uv run pytest tests/test_match.py::test_find_funder_edges_by_ein -v`
- Tests are fully offline (network calls are behind injectable `fetch`/`searcher` params);
  they run in well under a second. No build step.

The CLI is a two-step flow (see the `README.md` for the data download details):

```bash
# 1. one-time index build (SLOW — minutes per bundle; download data into data/ first)
uv run grant-finder setup --db data/grants.db --bmf-dir data/bmf --bundle-dir data/bundles
# 2. query (fast); prints a markdown prospect list, echoes the resolved org to stderr
uv run grant-finder run --db data/grants.db "Our Kids Read" --state MD
```

`data/` is git-ignored (multi-GB downloads + the built SQLite). The index is the reusable
asset — build once, query any nonprofit.

## Architecture

Three external data sources feed a local SQLite index:
- **ProPublica Nonprofit Explorer API** (`propublica.py`) — org profile + peer discovery (free).
- **IRS 990 XML bundles** (`ingest.py`) — the grant edges.
- **IRS Business Master File** (`bmf.py`) — recipient identity/NTEE/size; resolves 990-PF
  recipients to EINs.

Pipeline (`pipeline.run_prospect`): profile → peers (ProPublica) → match against the local
index → rank → render markdown. `cli.py` is thin glue over the modules; `db.py` owns the
schema.

### The two grant universes (this drives most of the design)

- **Schedule I** (grantmaking public charities): grant records carry the recipient **EIN** →
  exact joins. Parsed from `RecipientTable`.
- **990-PF** (private foundations): grant records have **name + city only, no EIN** → must be
  fuzzy-resolved to a BMF EIN before they can be matched (`bmf.resolve` /
  `resolve_pf_recipients`, ~43% resolution rate). Parsed from `GrantOrContributionPdDurYrGrp`.

`match.py` therefore matches two ways, and `pipeline._dedupe` UNIONs them and dedupes by
`grants.rowid` (a grant can match both the peer-EIN path and the NTEE-widened path):
- `find_funder_edges` — grants whose `recipient_ein` is in the peer set (exact).
- `find_edges_by_ntee` — grants whose resolved recipient's BMF NTEE matches the peers' codes
  (widening, to catch funders ProPublica's keyword peer-search missed).

### Fixed contracts (don't reorder)

- The `GrantEdge` dataclass field order (`models.py`) and the `grants`/`orgs` table column
  order (`db.py`) are paired positional contracts — `ingest.insert_edges` and
  `bmf.load_bmf_csv` insert by position. Changing one without the other silently corrupts data.
- `match` queries `SELECT rowid, *` specifically so `pipeline._dedupe` can key on it.

### Build-ordering gotcha

In `cli._setup`, `db.create_indexes` MUST run before `bmf.resolve_pf_recipients`. The
resolver does one blocked fuzzy lookup per 990-PF grant against the ~2M-row `orgs` table; with
no `idx_orgs_state_name` index each lookup full-scans and the build never finishes.

## Known limitations / next work

The pipeline is validated end-to-end, but the **default ranking is not yet user-ready**:
donor-advised-fund pass-throughs and over-broad NTEE matching dominate the top of the list.
`docs/pilot-run.md` documents the evidence and the three agreed refinements before this is
relied on or scaled nationally: (1) cause-specific NTEE targeting, (2) DAF/pass-through
exclusion, (3) fit-based ranking (purpose relevance + grant-size fit + geography) instead of
raw breadth. Treat the current ranked output as a rough draft, not a finished prospect list.

## Conventions

- `scripts/build_index.py` is a standalone single-bundle proof-of-concept, kept as a reference
  — it predates and is independent of the `grant_finder` package; don't wire it in.
- Keep network I/O behind injectable params so tests stay offline.
