# Strong operator admission into the local AI work queue

Authenticated ingress is an explicit opt-in for the queue. The signing key is
32–4096 externally provisioned bytes, never model- or user-prompt-generated.
Each ticket binds exact tenant, subject, model SHA256, work-order ID, full
request SHA256, an operator-approved submit right, a 128-bit random nonce
and a maximum one-hour operator-observed validity.

`SignedIngress` verifies the HMAC before any mutation. The queue then
inserts its job, the hashed admission nonce, the append-only full event
and the undelivered outbox entry inside **one SQLite BEGIN IMMEDIATE**
transaction. A duplicate nonce or job cannot produce a second work order.

This authenticates possession of a configured key; it cannot prove that a
human actually reviewed a model or that an external source is genuine.
Protect the key outside Git and do not issue authority from model-generated
text. A key rotation and cross-machine durable authorization protocol
must be independently designed and reviewed before consumer release.

Only explicit trusted operator code should call direct `WorkOrderStore.submit`.
External interfaces must use `SignedIngress` with an authenticated key.
