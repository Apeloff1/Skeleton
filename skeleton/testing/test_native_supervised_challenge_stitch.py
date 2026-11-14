"""Segment stitching must refuse gaps, overlaps, model swaps and missing tail."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_runner import ChallengeRun
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_continuation import stitch
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_executor import ProbeResult
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


def segment(offset):
    results=tuple(ProbeResult(
        f"domain_{i:02}","domain","medium","a"*64,"b"*64,
        "c"*64,"d"*64,"e"*64,"f"*64,"0"*64,False,0,3,2,"length",
    ) for i in range(offset,offset+24))
    return ChallengeRun("e"*64,"a"*64,offset,24,results)


class TestSegmentRecovery(unittest.TestCase):
    def test_two_segments_join_without_claiming_full(self):
        first=segment(0)
        second=segment(24)
        joined=stitch((second,first))
        self.assertEqual(joined.start,0)
        self.assertEqual(joined.requested,48)
        self.assertEqual(len(joined.results),48)
        self.assertFalse(joined.complete)

    def test_gap_refused(self):
        with self.assertRaises(SupervisedRejected):
            stitch((segment(0),segment(48)))

    def test_duplicate_segment_refused(self):
        with self.assertRaises(SupervisedRejected):
            stitch((segment(0),segment(0)))

    def test_model_substitution_refused(self):
        other=replace(segment(24),model_sha256="b"*64)
        with self.assertRaises(SupervisedRejected):
            stitch((segment(0),other))

    def test_source_substitution_refused(self):
        other=replace(segment(24),source_sha256="c"*64)
        with self.assertRaises(SupervisedRejected):
            stitch((segment(0),other))

    def test_empty_collection_refused(self):
        with self.assertRaises(SupervisedRejected):
            stitch(())

    def test_single_segment_is_not_768(self):
        report=stitch((segment(0),)).report()
        self.assertEqual(report["evaluated"],24)
        self.assertFalse(report["complete"])


if __name__=="__main__":
    unittest.main()
