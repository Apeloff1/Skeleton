"""Instance-level writer overrides must not bypass a valid class inventory."""
from __future__ import annotations

from types import MethodType
import unittest

from skeleton.persistence.mongo_source_epoch import (
    MongoSourceEpochError, _require_unshadowed_writer,
)


class Owner:
    async def mutate(self):
        return "protected"

    def require_writer(self):
        return True


class InstanceWriterFenceTests(unittest.TestCase):
    def test_original_class_binding_accepted(self):
        owner = Owner()
        _require_unshadowed_writer(owner, Owner.mutate, "mutate")
        _require_unshadowed_writer(owner, Owner.require_writer, "require_writer")

    def test_instance_callable_shadow_denied(self):
        owner = Owner()
        owner.mutate = lambda: "unguarded"
        with self.assertRaisesRegex(MongoSourceEpochError, "instance override"):
            _require_unshadowed_writer(owner, Owner.mutate, "mutate")

    def test_rebound_different_method_denied(self):
        owner = Owner()
        owner.mutate = MethodType(Owner.require_writer, owner)
        with self.assertRaises(MongoSourceEpochError):
            _require_unshadowed_writer(owner, Owner.mutate, "mutate")

    def test_bound_method_from_different_owner_denied(self):
        owner = Owner()
        other = Owner()
        owner.mutate = other.mutate
        with self.assertRaises(MongoSourceEpochError):
            _require_unshadowed_writer(owner, Owner.mutate, "mutate")

    def test_shadowed_internal_guard_denied(self):
        owner = Owner()
        owner.require_writer = lambda: True
        with self.assertRaises(MongoSourceEpochError):
            _require_unshadowed_writer(owner, Owner.require_writer, "require_writer")

    def test_missing_and_raising_descriptors_denied_without_leaking(self):
        owner = Owner()
        with self.assertRaises(MongoSourceEpochError):
            _require_unshadowed_writer(owner, Owner.mutate, "missing")
        class Raising:
            @property
            def mutate(self):
                raise RuntimeError("secret credential")
        with self.assertRaises(MongoSourceEpochError) as caught:
            _require_unshadowed_writer(Raising(), Owner.mutate, "mutate")
        self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
