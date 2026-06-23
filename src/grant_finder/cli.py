import argparse
import glob
import os
import sys

from . import bmf, db, ingest, pipeline, propublica


def _setup(args):
    conn = db.init_db(args.db)
    for csv_path in sorted(glob.glob(os.path.join(args.bmf_dir, "*.csv"))):
        print("BMF:", csv_path, bmf.load_bmf_csv(conn, csv_path))
    n = ingest.load_bundle(conn, args.bundle_dir)
    print("grant edges:", n)
    # Indexes (esp. idx_orgs_state_name) must exist BEFORE resolve_pf_recipients,
    # which does one blocked fuzzy lookup per PF grant against the ~2M-row orgs
    # table — without the index each lookup full-scans and the build never finishes.
    db.create_indexes(conn)
    print("resolved PF recipients:", bmf.resolve_pf_recipients(conn))


def _run(args):
    conn = db.connect(args.db)
    peers = propublica.search(args.name, state=args.state)
    profile = peers[0] if peers else None
    if profile is None:
        raise SystemExit(f"no org found for {args.name!r}")
    prof = propublica.get_org(profile.ein)
    print(f"Resolved org: {prof.name} (EIN {prof.ein}, NTEE {prof.ntee}, {prof.city} {prof.state})", file=sys.stderr)
    peer_list = propublica.find_peers(prof)
    print(pipeline.run_prospect(conn, prof, peer_list))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="grant-finder")
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
