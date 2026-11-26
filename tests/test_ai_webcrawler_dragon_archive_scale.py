from __future__ import annotations
import unittest
from skeleton.ai.webcrawler import dragon_archive_scale as a
S={"tenant_id":"test","owner_id":"owner"}

class ScaleTests(unittest.TestCase):
    def test_distribution_and_finite_bound(self):
        slots=[a.partition(S,f"session-{i}")[0] for i in range(16384)]
        self.assertEqual(a.MAX_EXPEDITIONS,1048576)
        self.assertGreater(len(set(slots)),1000)
        self.assertNotEqual(a.partition(S,"session"),a.partition({**S,"owner_id":"other"},"session"))
    def test_marker_scope_and_cursor(self):
        m=a.marker(S,"session","a"*64,"b"*64,"c"*64,100)
        for bad in ({**m,"released":True},{**m,"partition":1024},{**m,"snapshot_digest":"bad"}):
            with self.assertRaises(ValueError):
                a.validate_marker(bad,S,"session")
        key=a.cursor(S,"optical","session")
        self.assertEqual(a.decode_cursor(S,"optical",key),"session")
        with self.assertRaises(ValueError):
            a.decode_cursor(S,"different",key)
    def test_scope_bound_query_tokens(self):
        terms,tokens=a.query_terms(S,"Optical magnetometer optical")
        self.assertEqual(len(terms),2)
        self.assertEqual(len(set(tokens)),2)
        self.assertNotEqual(tokens,a.query_terms({**S,"owner_id":"other"},"Optical magnetometer optical")[1])
        with self.assertRaises(ValueError):
            a.query_terms(S,"!")
