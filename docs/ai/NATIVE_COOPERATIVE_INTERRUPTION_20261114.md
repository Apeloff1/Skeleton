# Cooperative active native interruption

The authenticated application can signal an active CPU model through
interrupt_authenticated_native_cpu_prompt. Exact tenant and request identity are
required. The independent interrupt lock never waits behind inference or accesses
SQLite on the signalling thread. A successful signal is a request, not proof
that generation has stopped. The native token callback and postflight fence
check the event before permitting result publication. Completion closes the
signal window atomically. An interrupted or uncertain invocation leaves its
running journal and pending lease intact, and is never retried automatically.

This does not implement hard process preemption, an HTTP cancellation endpoint,
or an automatic repair for running journal entries. These remain separate work.
