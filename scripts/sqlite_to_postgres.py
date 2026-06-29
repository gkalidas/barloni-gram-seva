#!/usr/bin/env python3
"""Generate a PostgreSQL dump (schema + data) from the SQLite database.

The app runs on SQLite, which is plenty for a single village. If an instance
ever outgrows it, this script produces a self-contained ``.sql`` file you can
load straight into Postgres:

    python scripts/sqlite_to_postgres.py data/gramseva.db > gramseva.pg.sql
    createdb gramseva
    psql gramseva < gramseva.pg.sql

It is dependency-free (standard-library ``sqlite3`` only) — no Postgres driver
needed to *produce* the file. It ports columns, primary keys, NOT NULL, simple
defaults, and all rows, then fixes up the id sequences. UNIQUE / FOREIGN KEY
constraints are emitted as comments for you to review, since they are easy to
get subtly wrong across engines and are not required to get the data in.
"""
import sqlite3
import sys

# SQLite stores loose type names; map the ones this schema uses to Postgres.
_TYPE_MAP = {"INTEGER": "BIGINT", "TEXT": "TEXT", "REAL": "DOUBLE PRECISION",
             "BLOB": "BYTEA", "NUMERIC": "NUMERIC"}


def _pg_type(sqlite_type: str) -> str:
    return _TYPE_MAP.get((sqlite_type or "TEXT").upper().split("(")[0], "TEXT")


def _pg_default(dflt: str) -> str:
    """Translate a SQLite column default to its Postgres equivalent."""
    if dflt is None:
        return ""
    d = dflt.strip()
    if d.lower() in ("(datetime('now'))", "datetime('now')", "current_timestamp"):
        # These columns hold datetime() *strings* in SQLite and are read as
        # text by the app, so keep them TEXT and cast the timestamp default.
        return "DEFAULT (CURRENT_TIMESTAMP::text)"
    return f"DEFAULT {d}"


def _quote(value) -> str:
    """Render a Python value as a Postgres SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, bytes):
        return "'\\x" + value.hex() + "'"  # bytea hex format
    return "'" + str(value).replace("'", "''") + "'"


def _tables(con) -> list:
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def dump(db_path: str, out) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    out.write("-- PostgreSQL dump generated from %s\n" % db_path)
    out.write("BEGIN;\n\n")

    serial_tables = []
    for table in _tables(con):
        cols = con.execute(f"PRAGMA table_info({table})").fetchall()
        out.write(f"DROP TABLE IF EXISTS {table} CASCADE;\n")
        out.write(f"CREATE TABLE {table} (\n")
        defs = []
        pk_serial = None
        for c in cols:
            name, ctype, notnull, dflt, pk = (
                c["name"], c["type"], c["notnull"], c["dflt_value"], c["pk"])
            # A single INTEGER PRIMARY KEY is SQLite's autoincrement rowid ->
            # Postgres BIGSERIAL so inserts and the sequence stay in sync.
            if pk and (ctype or "").upper() == "INTEGER":
                defs.append(f"    {name} BIGSERIAL PRIMARY KEY")
                pk_serial = name
                continue
            parts = [f"    {name}", _pg_type(ctype)]
            if notnull:
                parts.append("NOT NULL")
            dpart = _pg_default(dflt)
            if dpart:
                parts.append(dpart)
            defs.append(" ".join(parts))
        out.write(",\n".join(defs))
        out.write("\n);\n")
        if pk_serial:
            serial_tables.append((table, pk_serial))

        # Data.
        rows = con.execute(f"SELECT * FROM {table}").fetchall()
        if rows:
            colnames = rows[0].keys()
            collist = ", ".join(colnames)
            for r in rows:
                values = ", ".join(_quote(r[c]) for c in colnames)
                out.write(f"INSERT INTO {table} ({collist}) VALUES ({values});\n")
        out.write("\n")

    # Re-sync each BIGSERIAL sequence to the max id present.
    for table, pk in serial_tables:
        out.write(
            f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), "
            f"COALESCE((SELECT MAX({pk}) FROM {table}), 1));\n")

    out.write("\nCOMMIT;\n")
    out.write("\n-- NOTE: review UNIQUE / FOREIGN KEY / CHECK constraints from\n"
              "-- app/database.py and add them with ALTER TABLE if you need them.\n")
    con.close()


def main(argv) -> int:
    if len(argv) < 2:
        print("usage: sqlite_to_postgres.py <sqlite-db-path> [out.sql]", file=sys.stderr)
        return 2
    db_path = argv[1]
    if len(argv) >= 3:
        with open(argv[2], "w", encoding="utf-8") as fh:
            dump(db_path, fh)
        print(f"Wrote Postgres dump to {argv[2]}", file=sys.stderr)
    else:
        dump(db_path, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
