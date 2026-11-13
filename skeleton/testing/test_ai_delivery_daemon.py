"""Bounded operator process delivery loop: restart, hold and no model calls."""
from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from skeleton.testing.test_ai_delivery_custody import CustodyTests
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.daemon import (
    LocalSpoolDaemon,SpoolDaemonPolicy)
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.contracts import DeliveryHeld
from skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.doctor import inspect

class DaemonTests(CustodyTests):
    def test_exact_three_ticks_and_no_inference(self):
        daemon=LocalSpoolDaemon(self.pump,SpoolDaemonPolicy(maximum_ticks=3,tick_ms=20))
        report=daemon.run()
        self.assertEqual(report['ticks'],3)
        self.assertEqual(report['exported'],1)
        self.assertEqual(report['status'],'stopped')
        self.assertEqual(report['model_calls'],0)
        self.assertRaises(DeliveryHeld,daemon.run)
    def test_failure_stops_and_does_not_ack(self):
        with patch.object(self.sink,'append',side_effect=DeliveryHeld('disk full')):
            daemon=LocalSpoolDaemon(self.pump)
            self.assertRaises(DeliveryHeld,daemon.step)
            self.assertEqual(daemon.state,'held')
            self.assertRaises(DeliveryHeld,daemon.step)
    def test_explicit_stop_before_tick(self):
        daemon=LocalSpoolDaemon(self.pump,SpoolDaemonPolicy(maximum_ticks=100,tick_ms=20))
        daemon.request_stop()
        self.assertEqual(daemon.run()['ticks'],0)
    def test_read_only_doctor(self):
        self.pump.drain();proof=inspect(self.ledger,self.sink)
        self.assertEqual(proof['custody']['acknowledged'],1)
        self.assertFalse(proof['release_accepted'])
    def test_bad_policy_refused(self):
        for args in ({'tick_ms':0},{'batch':0},{'maximum_ticks':True}):
            with self.subTest(args=args),self.assertRaises(DeliveryHeld):
                SpoolDaemonPolicy(**args)

if __name__=='__main__':unittest.main()
