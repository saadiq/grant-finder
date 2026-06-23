from grant_finder import db


def test_init_db_creates_tables_and_roundtrips():
    conn = db.init_db(":memory:")
    conn.execute("INSERT INTO grants (funder_ein, amount) VALUES ('1', 5)")
    conn.execute("INSERT INTO orgs (ein, name) VALUES ('9', 'X')")
    conn.commit()
    db.create_indexes(conn)
    g = conn.execute("SELECT amount FROM grants").fetchone()
    o = conn.execute("SELECT name FROM orgs").fetchone()
    assert g["amount"] == 5 and o["name"] == "X"
