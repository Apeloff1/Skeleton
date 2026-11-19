# Native execution custody: whole-request mode

The native grant, sealed vault, and journal intentionally authorize one generation per request.
Generic scheduler clients retain slice planning and v1 receipt semantics. Native composition
uses whole-request planning: a request is deferred when the complete output-token reservation
does not fit live headroom. It receives one lease, one native generation and one encrypted result.
The v2 HMAC receipt authenticates actual token usage and terminal completion independently.
Early EOS does not pretend unused tokens were consumed. Only an entire-request lease may be
retired by a terminal receipt. A v1 receipt remains verifiable and retains its original accounting.

Pressure deferral before invoking the execution owner can continue the same issued permit in
the same process after another live observation. A restart or uncertain execution cannot replay.
Previously stranded v1 partial requests are not migrated automatically; operator reconciliation
must resolve legacy durable state without rerunning already committed inference.

This is not resumable KV-cache decoding, parallel GPU execution, operator model qualification,
or proof of real-device resource reservations. Native tests must qualify the exact final SHA.
