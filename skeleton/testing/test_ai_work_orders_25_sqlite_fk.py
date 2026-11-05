"""Exact work-order schema must preserve real SQLite referential constraints."""
import sqlite3
import unittest
from skeleton.testing.work_orders_test_support import QueueCase

class SchemaForeignKeys(QueueCase):
    def test_event_hash_is_a_unique_fk_parent(self):
        with self.store.db.snapshot() as conn:
            rows=conn.execute("PRAGMA index_list(events)").fetchall()
            unique=[entry for entry in rows if entry[2]]
            self.assertTrue(unique)
            columns=set()
            for row in unique:
                name=row[1]
                for detail in conn.execute("PRAGMA index_info('"+name+"')"):
                    columns.add(detail[2])
            self.assertIn("event_sha",columns)
            fks=conn.execute("PRAGMA foreign_key_list(outbox)").fetchall()
            self.assertTrue(any(row[2]=="events" and row[3]=="event_sha"
                                and row[4]=="event_sha" for row in fks))
    def test_real_event_insert_honors_foreign_key_check(self):
        self.store.submit(self.order)
        with self.store.db.snapshot() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0],1)
    def test_unauthorized_child_event_digest_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.db.transaction() as conn:
                conn.execute("INSERT INTO outbox(event_sha,job_id) VALUES (?,?)",
                             ("e"*64,"missing"))

if __name__=="__main__":unittest.main()
