# Defense-in-depth boundary matrix

| Input / event | Static source contract | Runtime primitive | Authoritative owner |
|---|---|---|---|
| Operator actor | actor | native preflight | authenticated local caller |
| GGUF installation | artifact, path, checkpoint | bounded stream hashing | descriptor-anchored installer |
| Tokenizer | tokenizer | model epoch fence | activated backend |
| Conversation history | conversation | alternating history adapter | OfflineChatStore |
| Sampling | sampling | pre-inference admission | backend/model gateway |
| Deadlines | admission, cancel | monotonic deadlines | local serving supervisor |
| Quotas | quota | reservation book | durable cost accounting |
| Streaming | stream | credit window and assembler | backend and authenticated HTTP |
| Tool invocation | grant, tool | intent custody | ToolExecutor, caller permissions |
| Long-lived context | memory, retrieval | HMAC consent and byte offsets | SealedMemoryStore |
| Audit | journal, replay | computed chain verifier | EventJournal and SQLite CAS |
| Model replacement | evaluation, promotion | staged rollout/rollback | operator + GitHub check evidence |
| Restart | checkpoint, journal, replay | ordered recovery plan | trusted operator |
| Transport | transport | loopback envelope | credential-checking HTTP listener |

Every stage must fail closed when its independent owner cannot supply proof.
There is no hosted fallback, implicit write authority, or model-generated
permission escalation. Tests exercise predicates and in-process state
machines; external proof requires independent native and security checks.
