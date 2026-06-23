def find_funder_edges(conn, peer_eins):
    """Find grants to a peer set by exact recipient EIN.

    Args:
        conn: SQLite connection
        peer_eins: list of recipient EINs to match

    Returns:
        list of sqlite3.Row with rowid column (for dedup in Task 10)
    """
    if not peer_eins:
        return []
    placeholders = ",".join("?" * len(peer_eins))
    q = (f"SELECT rowid, * FROM grants WHERE recipient_ein IN ({placeholders}) "
         "AND amount IS NOT NULL")
    return conn.execute(q, peer_eins).fetchall()


def find_edges_by_ntee(conn, ntee_prefixes):
    """Find grants to orgs matching NTEE code prefixes.

    Args:
        conn: SQLite connection
        ntee_prefixes: list of NTEE code prefixes (e.g. ["B", "E"])

    Returns:
        list of sqlite3.Row with rowid column (for dedup in Task 10)
    """
    if not ntee_prefixes:
        return []
    clause = " OR ".join("o.ntee LIKE ?" for _ in ntee_prefixes)
    q = ("SELECT g.rowid AS rowid, g.* FROM grants g JOIN orgs o ON g.recipient_ein = o.ein "
         f"WHERE g.amount IS NOT NULL AND ({clause})")
    return conn.execute(q, [p + "%" for p in ntee_prefixes]).fetchall()
