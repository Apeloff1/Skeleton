"""Capacity ledger adversarial and concurrency regression suite."""
import threading
import unittest

from skeleton.ai.model_serving.capacity import (
    CapacityDenied, CapacityLedger, CapacityLimits, Reservation,
)


class Clock:
    def __init__(self):
        self.value = 10

    def __call__(self):
        return self.value


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.ledger = CapacityLedger(CapacityLimits(2, 12, 100), clock_ns=self.clock)

    def test_idempotency_and_capacity(self):
        first = self.ledger.acquire("a", "digest-a", 7)
        self.assertEqual(first, self.ledger.acquire("a", "digest-a", 7))
        self.assertEqual(self.ledger.snapshot(), (1, 7))
        for fingerprint, tokens in (("different", 7), ("digest-a", 8)):
            with self.assertRaises(CapacityDenied):
                self.ledger.acquire("a", fingerprint, tokens)
        with self.assertRaises(CapacityDenied):
            self.ledger.acquire("b", "digest-b", 6)
        second = self.ledger.acquire("b", "digest-b", 5)
        with self.assertRaises(CapacityDenied):
            self.ledger.acquire("c", "digest-c", 1)
        self.assertEqual(self.ledger.snapshot(), (2, 12))
        self.assertTrue(self.ledger.release(first))
        self.assertFalse(self.ledger.release(first))
        self.assertTrue(self.ledger.release(second))
        self.assertEqual(self.ledger.snapshot(), (0, 0))

    def test_expiry_and_aba_release(self):
        old = self.ledger.acquire("a", "digest", 3)
        self.clock.value = 110
        self.assertFalse(self.ledger.is_active(old))
        new = self.ledger.acquire("a", "digest", 3)
        self.assertNotEqual(old, new)
        self.assertFalse(self.ledger.release(old))
        self.assertTrue(self.ledger.is_active(new))
        self.assertTrue(self.ledger.release(new))

    def test_invalid_inputs(self):
        for args in (("", "f", 1), ("a", "", 1), ("a", "f", 0),
                     ("a", "f", True), ("a", "f", 1.0)):
            with self.subTest(args=args), self.assertRaises(CapacityDenied):
                self.ledger.acquire(*args)
        for limits in ((0, 1, 1), (1, False, 1), (1, 1, -1)):
            with self.assertRaises(ValueError):
                CapacityLimits(*limits)
        self.clock.value = -1
        with self.assertRaises(CapacityDenied):
            self.ledger.acquire("a", "f", 1)

    def test_concurrent_acquisition_never_overbooks(self):
        ledger = CapacityLedger(CapacityLimits(3, 30, 10**12))
        barrier = threading.Barrier(12)
        successes = []
        failures = []
        lock = threading.Lock()

        def worker(i):
            barrier.wait()
            try:
                lease = ledger.acquire(str(i), "fingerprint", 10)
                with lock:
                    successes.append(lease)
            except CapacityDenied:
                with lock:
                    failures.append(i)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(successes), 3)
        self.assertEqual(len(failures), 9)
        self.assertEqual(ledger.snapshot(), (3, 30))


if __name__ == "__main__":
    unittest.main()
