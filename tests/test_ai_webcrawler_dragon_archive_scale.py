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

    def test_filtered_sorted_cursor_binds_every_dimension(self):
        options=a.search_options(partition_id=513,order="archive_newest",match="all")
        key=a.search_cursor(S,"optical",options,identifier="chamber-42",accepted_at=1842938471.125)
        self.assertEqual(a.search_boundary(S,"optical",options,key),("chamber-42",1842938471.125))
        for changed in (a.search_options(partition_id=514,order="archive_newest",match="all"),
                        a.search_options(partition_id=513,order="archive_oldest",match="all"),
                        a.search_options(partition_id=513,order="archive_newest",match="any")):
            with self.assertRaises(ValueError):
                a.search_boundary(S,"optical",changed,key)
        with self.assertRaises(ValueError):
            a.search_boundary({**S,"owner_id":"another"},"optical",options,key)
        _,terms=a.query_terms(S,"optical magnetometer")
        query,sort=a.search_predicate(S,terms,100,options,("chamber-42",1842938471.125))
        self.assertEqual(query["deep_index.tokens"],{"$all":terms})
        self.assertEqual(query["deep_archive.partition"],513)
        self.assertEqual(query["$or"][0],{"deep_archive.accepted_at":{"$lt":1842938471.125}})
        self.assertEqual(sort,[("deep_archive.accepted_at",-1),("_id",1)])

    def test_current_wiki_binding_exact_passage_and_expiry(self):
        from skeleton.ai.webcrawler.dragon_hoag_catalog import current_catalog,validate_current_binding
        citation="dragon-crawl://chamber/"+"a"*64
        doc={"source_id":"a"*64,"source_ref":citation,"authority":"external_evidence_only",
             "source_use_version":2,"content_digest":"b"*64,"valid_until":200,"text":"not stored"}
        projection={"documents":[doc],"references":[{"source_id":"a"*64,"session_id":"chamber","source_use_version":2}]}
        receipt=current_catalog(projection,now=100)
        self.assertNotIn("text",receipt["pointers"][0])
        self.assertEqual(validate_current_binding({**projection,"hoag_wiki":receipt},now=101),{citation:"b"*64})
        with self.assertRaises(ValueError):
            validate_current_binding({**projection,"hoag_wiki":receipt},now=160)
        with self.assertRaises(ValueError):
            validate_current_binding({**projection,"documents":[{**doc,"content_digest":"c"*64}],"hoag_wiki":receipt},now=101)
