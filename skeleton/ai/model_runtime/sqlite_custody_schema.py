"""Verify the schema used by offline custody and one-use ledgers.

These checks reject accidental migration drift and hostile stored schema
objects. They do not provide rollback resistance, nor protect against a
compromised application process with access to the same keys.
"""
from __future__ import annotations

import re
import sqlite3

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,127}\Z")


class CustodySchemaError(ValueError):
    """The database no longer implements its required custody constraints."""


def _identifier(value: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise CustodySchemaError("invalid custody schema identity")
    return value


def assert_custody_schema(
    connection: sqlite3.Connection, *, table: str, columns: tuple[str, ...],
    primary_key: str | tuple[str, ...], replay_index: str | None = None,
    replay_columns: tuple[str, ...] = (),
    unique_keys: tuple[tuple[str, ...], ...] = (),
) -> None:
    """Validate the main table and reject temporary name shadowing and triggers.

    Call inside the writer reservation before changing authoritative state;
    call before reads as well. SQL identifiers are internal validated constants.
    """
    table = _identifier(table)
    rows = connection.execute(
        "SELECT type FROM main.sqlite_master WHERE name=? COLLATE NOCASE",
        (table,),
    ).fetchall()
    if len(rows) != 1 or rows[0][0] != "table":
        raise CustodySchemaError("canonical custody table missing")
    # Do not materialize TEMP merely to inspect it. SQLite identifies a
    # materialized temp schema in database_list even when it is empty.
    schemas = {row[1] for row in connection.execute("PRAGMA database_list")}
    if schemas - {"main", "temp"}:
        raise CustodySchemaError("unexpected attached custody database")
    if "temp" in schemas:
        if connection.execute(
            "SELECT 1 FROM temp.sqlite_master WHERE name=? COLLATE NOCASE LIMIT 1",
            (table,),
        ).fetchone() is not None:
            raise CustodySchemaError("temporary custody table shadow")
        if connection.execute(
            "SELECT 1 FROM temp.sqlite_master WHERE type='trigger' "
            "AND tbl_name=? COLLATE NOCASE LIMIT 1", (table,),
        ).fetchone() is not None:
            raise CustodySchemaError("untrusted custody table trigger")
    if connection.execute(
        "SELECT 1 FROM main.sqlite_master WHERE type='trigger' "
        "AND tbl_name=? COLLATE NOCASE LIMIT 1", (table,),
    ).fetchone() is not None:
        raise CustodySchemaError("untrusted custody table trigger")
    # An identity ledger is an independent authority, not a relational
    # dependent whose rows may disappear on a foreign-table cascade.
    if connection.execute("PRAGMA main.foreign_key_list(" + table + ")").fetchone() is not None:
        raise CustodySchemaError("untrusted custody foreign key dependency")
    keys = (primary_key,) if isinstance(primary_key, str) else primary_key
    if not keys or any(_identifier(key) != key for key in keys):
        raise CustodySchemaError("invalid custody primary key")
    info = connection.execute("PRAGMA main.table_xinfo(" + table + ")").fetchall()
    if (
        tuple(row[1] for row in info) != columns
        or any(row[6] != 0 for row in info)
        or tuple(row[1] for row in sorted((row for row in info if row[5]), key=lambda row: row[5])) != keys
        or any(row[3] != 1 for row in info if row[1] in keys)
    ):
        raise CustodySchemaError("untrusted custody table shape or primary key")
    # Inspect actual unique indexes, including implicit PRIMARY KEY and UNIQUE
    # autoindexes. Partial, expression, descending and nonbinary indexes
    # cannot substitute for the exact identity fences.
    all_indexes = connection.execute("PRAGMA main.index_list(" + table + ")").fetchall()
    def index_keys(row):
        # SQLite-generated names are not in the internal identifier alphabet:
        # bind the name as data to the table-valued PRAGMA instead.
        parts = connection.execute(
            "SELECT name, desc, coll FROM pragma_index_xinfo(?, 'main') WHERE key=1 ORDER BY seqno",
            (row[1],),
        ).fetchall()
        if row[2] != 1 or row[4] != 0 or any(p[0] is None or p[1] != 0 or p[2] != "BINARY" for p in parts):
            return ()
        return tuple(p[0] for p in parts)
    if not any(row[3] == "pk" and index_keys(row) == keys for row in all_indexes):
        raise CustodySchemaError("untrusted custody primary key index")
    for required in unique_keys:
        if (not required or any(key not in columns for key in required)
                or any(row[3] != 1 for row in info if row[1] in required)
                or not any(index_keys(row) == required for row in all_indexes)):
            raise CustodySchemaError("untrusted custody unique identity index")
    if replay_index is not None:
        replay_index = _identifier(replay_index)
        if (not replay_columns or any(key not in columns for key in replay_columns)
                or any(row[3] != 1 for row in info if row[1] in replay_columns)):
            raise CustodySchemaError("untrusted nullable custody replay identity")
        indexes = [
            row for row in connection.execute("PRAGMA main.index_list(" + table + ")")
            if row[1] == replay_index
        ]
        if len(indexes) != 1 or indexes[0][2] != 1 or indexes[0][4] != 0:
            raise CustodySchemaError("untrusted custody replay index")
        key_rows = [
            row for row in connection.execute("PRAGMA main.index_xinfo(" + replay_index + ")")
            if row[5] == 1
        ]
        if (tuple(row[2] for row in key_rows) != replay_columns
                or any(row[3] != 0 or row[4] != "BINARY" for row in key_rows)):
            raise CustodySchemaError("untrusted custody replay index columns")
