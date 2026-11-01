# Descriptor-pinned long-context bucket identity

The long-context POSIX custody store now checks both the root path and each
selected digest bucket name against the original opened directory descriptor.
A bucket rename/replacement cannot produce a successful read or durable
publication acknowledgement merely because the old bucket descriptor is still
usable. Unknown or insecure bucket identities fail closed.

Read-only checkpoint/object reads no longer create missing digest buckets.
Explicit orphan recovery likewise refuses a missing bucket rather than
mutating inventory during an audit. Publication alone may create a bucket,
under the existing cooperative cross-process lock and bounded quota checks.

These fences do not certify a hostile same-UID filesystem writer, nor a
cross-device, cross-process transaction. Revalidate canonical tests and
required exact-head CI before promotion. Windows is not qualified for these
descriptor-relative protections.

Focused regression suite:
`python -m unittest tests.flgb.test_long_context_root_guard`
