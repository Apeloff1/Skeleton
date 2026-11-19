# Native execution custody: authenticated whole-request policy

The native grant, sealed vault and journal authorize a single generation per
request. Generic scheduler clients retain slice planning. Native composition
instead selects the whole-request policy at store construction, authenticates
it in the v3 checkpoint and binds the exact queued request to its process-keyed
prompt authorization. Legacy checkpoints cannot be switched to whole-request
mode by passing a different planning or acknowledgement argument.

A native request is deferred when the complete output reservation cannot fit
live headroom. The signed v1 execution receipt records actual token consumption
and the result digest. Early EOS retires the remainder only under the already
authenticated whole-request checkpoint policy; no unsigned terminal flag or
invented consumed count changes the policy. Generic requests retain partial
slice accounting.

A resource-pressure deferral before invoking the execution owner can resume
only the same current-process issued permit at the original planning ceiling.
The fresh probe and prompt grant must still pass. Restart-lost or uncertain
execution cannot replay. Existing sealed output, cancelled intent, or a
quiescent no-output retirement each require their own exact operator recovery
approval. External anchor divergence requires separate forward recovery.

This is not resumable KV-cache decoding, parallel GPU execution, automatic
archive rotation, device qualification or physical memory reservation.
Exact-head CI is required; this document is a source contract, not evidence
of passing tests or installer readiness.
