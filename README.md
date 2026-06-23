# Grant Finder

Find grant funders for a nonprofit by answering **"who funds organizations like me?"**
from IRS Form 990 e-file data.

The hard part: the source data is **funder-keyed** — each filing is one funder's list of
grants going *out*, which is the inverse of the question you actually want answered. Grant
Finder reconstructs a **recipient → funder** view, then matches it against a nonprofit's
peers (by EIN) and cause (by NTEE code) to surface funders who already give to organizations
like it.

> **Status: pilot.** Validated end-to-end on real data, but the default ranking is not yet
> user-ready (donor-advised-fund pass-throughs and over-broad NTEE matching dominate the top
> of the list). Treat the ranked output as a rough draft. See [`docs/pilot-run.md`](docs/pilot-run.md)
> for evidence and the planned refinements.

## How it works

Three external data sources feed a local SQLite index:

- **ProPublica Nonprofit Explorer API** — org profile + peer discovery (free, no key).
- **IRS 990 XML bundles** — the grant edges (who gave to whom).
- **IRS Business Master File (BMF)** — recipient identity / NTEE / size; used to resolve
  990-PF grant recipients to EINs.

Grants come from two universes that are matched differently:

- **Schedule I** (grantmaking public charities) — records carry the recipient **EIN**, so
  joins are exact.
- **990-PF** (private foundations) — records have **name + city only, no EIN**, so they are
  fuzzy-resolved against the BMF before matching (~43% resolution rate).

The index is the reusable asset: **build it once, query any nonprofit.**

## Requirements

- Python ≥ 3.11
- [`uv`](https://docs.astral.sh/uv/) (used exclusively — no `pip`)

## Installation

From the repo root:

```bash
uv sync
```

This installs dependencies and the `grant-finder` CLI into `.venv`. Run commands with
`uv run grant-finder …` (or activate the venv and call `grant-finder` directly).

## Usage

The CLI is a two-step flow: build the index once (slow), then query it (fast).

### 1. Download the data

The downloads are large and multi-GB, so `data/` is git-ignored — fetch the data yourself:

- **990 XML bundles** — IRS 990 e-file ZIPs from
  `https://apps.irs.gov/pub/epostcard/990/xml/{year}/` (e.g. `2023_TEOS_XML_01A.zip`).
  Unzip the XML files (flattened) into one directory, e.g. `data/bundles`.
- **Business Master File** — the four EO BMF extracts
  `https://www.irs.gov/pub/irs-soi/eo{1,2,3,4}.csv` into a directory, e.g. `data/bmf`.

### 2. Build the index (one-time, slow)

```bash
uv run grant-finder setup \
  --db data/grants.db \
  --bmf-dir data/bmf \
  --bundle-dir data/bundles
```

This loads the BMF (org identity / NTEE / size), parses every filing's grant records into
the `grants` table, creates indexes, and fuzzy-resolves 990-PF recipients to EINs. Expect
minutes per bundle (hours for national coverage). **Re-running `setup` with more bundles
widens coverage.**

### 3. Query for a nonprofit (fast)

```bash
uv run grant-finder run --db data/grants.db "Our Kids Read" --state MD
```

| Argument | Required | Description |
|----------|----------|-------------|
| `name` (positional) | yes | The nonprofit's name to look up on ProPublica. |
| `--db` | yes | Path to the SQLite index built in step 2. |
| `--state` | no | Two-letter state code to disambiguate the org lookup. |

It looks the org up on ProPublica (profile + peers), queries the local index, and prints a
ranked **markdown prospect list** to stdout with evidence and filing links. The resolved org
(name, EIN, NTEE, location) is echoed to stderr, so you can redirect just the report:

```bash
uv run grant-finder run --db data/grants.db "Our Kids Read" --state MD > prospects.md
```

## Using it from Claude Code (Agent Skill)

This repo ships an [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) at
[`.claude/skills/grant-finder/SKILL.md`](.claude/skills/grant-finder/SKILL.md) so you can
drive the tool in natural language instead of remembering CLI flags.

**How it works.** A skill is markdown with a `name` + `description` in its frontmatter.
Claude Code loads only that metadata at startup; when your request matches the description,
it pulls in the full skill body and follows it — here, that body tells Claude how to build
the index and run `grant-finder`. So once the index exists, you can just ask:

> *"Who funds Our Kids Read in MD?"*

and Claude runs the right `uv run grant-finder run …` for you.

### Project skill (already set up)

Because the skill lives under `.claude/skills/` in this repo, it **auto-activates whenever
Claude Code is working inside this clone** — no install step. Just `uv sync`, build the index
once, and ask. This is the recommended way to use it (the skill assumes repo-relative paths
like `data/grants.db`).

### Installing it as a personal skill

To make the skill available in *all* your projects (not just this repo), copy it into your
personal skills directory:

```bash
mkdir -p ~/.claude/skills/grant-finder
cp .claude/skills/grant-finder/SKILL.md ~/.claude/skills/grant-finder/SKILL.md
```

Claude Code discovers skills from two locations:

| Scope | Path | Availability |
|-------|------|-------------|
| **Project** | `<repo>/.claude/skills/<name>/SKILL.md` | Auto-loads when working in that repo; committed, so it travels with the clone |
| **Personal** | `~/.claude/skills/<name>/SKILL.md` | Available across all your projects |

Note that the skill body uses **repo-relative paths**, so even when installed personally
you'll want Claude to be working from a `grant-finder` checkout with the index already built.
Verify either install with `/help` → skills, or just make a request that matches the skill's
description and watch Claude invoke it.

## Caveats

- **Warm leads, not application instructions.** Output means "funders who demonstrably give
  to orgs like you." Whether a funder accepts *unsolicited* proposals is not in this data —
  verify on the funder's site before applying.
- **Donor-advised funds (DAFs) are noise.** Pass-through sponsors (Fidelity / Schwab /
  Vanguard Charitable, etc.) appear to fund thousands of orgs because individual donors
  direct them. They are not targetable.
- **NTEE-widening can over-broaden.** Matching on broad codes (e.g. B90 education) pulls in
  unrelated orgs; cause-specific codes (e.g. B92 literacy) are far cleaner.
- **990-PF matching is fuzzy (~43% resolved).** Foundation grants carry no recipient EIN, so
  coverage is partial. Schedule I joins are exact.
- **1–2 year data lag.** Filings appear well after the tax year.

## Development

```bash
uv run pytest -q                 # all tests (fully offline, sub-second)
uv run pytest tests/test_match.py::test_find_funder_edges_by_ein -v   # a single test
```

Network I/O is kept behind injectable `fetch` / `searcher` params so the test suite runs
fully offline with no build step.

See [`CLAUDE.md`](CLAUDE.md) for architecture and contributor notes, and
[`docs/pilot-run.md`](docs/pilot-run.md) for validated results and current limitations.
