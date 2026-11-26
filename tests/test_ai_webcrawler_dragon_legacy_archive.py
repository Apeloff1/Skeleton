"""Legacy compatibility reads witnessed bytes; they never resume old code."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.dragon_legacy_archive import digest,inspect_terminal
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun,CrawlOperationError
from tests.test_ai_webcrawler_dragon_adaptive_instruction_guard import BASE,ROBOTS,GOOD,ScriptedFetcher,step

NOW=1_800_000_000.
SCOPE={"tenant_id":"tenant","owner_id":"owner"}
CONSENT={"consent_id":"a"*64,"capture_acknowledged":True,
         "source_rights_acknowledged":True,"expires_at":NOW+3600}


def captured():
    fetcher=ScriptedFetcher({
        BASE+"/robots.txt":(200,"text/plain",ROBOTS,{}),
        BASE+"/first":(200,"text/html",GOOD,{})})
    request=CrawlRequest(seed_urls=(BASE+"/first",),allowed_hosts=("example.com",),
        query="orbital",max_depth=0,max_requests=4,max_documents=1,
        max_response_bytes=4096,max_total_bytes=32768,min_host_delay_seconds=.25)
    runtime=CrawlRun.create(request,scope=SCOPE,consent=CONSENT,now=NOW,fetcher=fetcher)
    step(runtime,NOW+1)
    step(runtime,NOW+4)
    snap=runtime.snapshot()
    assert snap["state"] in {"completed","budget_exhausted"}
    assert len(snap["sources"])==1
    return snap


def inspect(snap,**kwargs):
    return inspect_terminal(snap,scope=kwargs.get("scope",SCOPE),
         request_digest=snap["binding"]["request_digest"],consent=CONSENT,now=NOW+86400)


def resign_test_fixture(snap):
    snap.pop("snapshot_digest",None)
    snap["snapshot_digest"]=digest(snap)
    return snap


class LegacyArchiveTests(unittest.TestCase):
    def test_actual_capture_read_only_after_simulated_runtime_change(self):
        snap=captured()
        original=copy.deepcopy(snap)
        with patch("skeleton.ai.webcrawler.operations.implementation_digest",return_value="f"*64):
            with self.assertRaises(CrawlOperationError):
                CrawlRun.from_snapshot(snap)
            proof=inspect(snap)
        self.assertEqual(proof["verified_source_ids"],sorted(snap["sources"]))
        self.assertFalse(proof["execution_authorized"])
        self.assertFalse(proof["network_authority_expanded"])
        self.assertFalse(proof["model_context_permission"])
        self.assertEqual(snap,original)

    def test_scope_digest_and_capture_identity_are_not_optional(self):
        snap=captured()
        with self.assertRaises(ValueError):
            inspect(snap,scope={**SCOPE,"owner_id":"other"})
        wrong=copy.deepcopy(snap)
        next(iter(wrong["sources"].values()))["text"]="altered evidence"
        with self.assertRaises(ValueError):
            inspect(wrong)
        wrong=copy.deepcopy(snap)
        next(iter(wrong["sources"].values()))["provenance"]["capture_sequence"]=1
        with self.assertRaises(ValueError):
            inspect(resign_test_fixture(wrong))

    def test_non_capture_measurement_cannot_reconstruct_compacted_event(self):
        snap=captured()
        modified=copy.deepcopy(snap)
        modified["events"]=[e for e in modified["events"] if e["kind"]!="captured"]
        receipt=next(m for m in modified["acquisition_measurements"] if m["source_id"])
        receipt["kind"]="rejected"
        with self.assertRaises(ValueError):
            inspect(resign_test_fixture(modified))
        compacted=copy.deepcopy(snap)
        compacted["events"]=[e for e in compacted["events"] if e["kind"]!="captured"]
        proof=inspect(resign_test_fixture(compacted))
        self.assertEqual(proof["verified_source_ids"],sorted(snap["sources"]))

    def test_pending_or_nonterminal_cannot_migrate_even_with_digest(self):
        snap=captured()
        snap["state"]="interrupted"
        with self.assertRaises(ValueError):
            inspect(resign_test_fixture(snap))


if __name__=="__main__":
    unittest.main()
