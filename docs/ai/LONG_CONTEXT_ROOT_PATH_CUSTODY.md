# Long-context root and ancestor custody

The POSIX long-context spool opens the authorized root through descriptor-relative,
no-follow directory traversal. Descriptor pinning alone is insufficient: after
an ancestor or the root is renamed, a valid descriptor can still point at an
orphaned directory, allowing a misleading durable publication acknowledgement.

The runtime now reopens the **visible absolute root path** and compares its
device/inode with the original root descriptor, including owner and 0700 mode.
This guard is checked before bucket access and publication locks, after
publication, after bounded reads, during recovery and capacity observations,
and at entry/exit of the durable stream-head lock. A replaced or missing root
fails closed rather than claiming a checkpoint was durably published at the
operator-selected path. A selected source sequence similarly reopens its
visible parent chain after the bounded descriptor read and verifies that the
pinned parent is still the visible one.

These checks are **not** a claim of atomic pathname custody against an
adversarial same-UID writer racing after the final check. The supported
boundary remains cooperative, operator-owned POSIX directories. Do not treat
Windows path fallback as qualified for ancestor-replacement resistance.
Do not disable existing disk quota, lock, content digest, tokenizer or
checkpoint ancestry validation. Never infer GPU qualification from this work.

Focused regression suite:
`python -m unittest tests.flgb.test_long_context_root_guard`
Existing long-context spool and durable-head tests must also pass before
promoting this WIP branch. Exact-head CI and independent release qualification
remain mandatory.
