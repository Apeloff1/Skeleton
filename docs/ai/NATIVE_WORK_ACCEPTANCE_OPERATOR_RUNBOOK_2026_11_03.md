# Real source-bound GGUF + signed durable work-order acceptance

The work-order acceptance CLI operates on actual locally installed GGUF
bytes. It uses the preexisting installer receipt/rights check and isolated
native backend, and then enters the newly implemented signed job queue.

The operator must create three isolated mode-0700 directories (canonical
spine state, work queue state and capacity root) and install a trusted GGUF
checkpoint. The HMAC key is a random, externally provisioned 32-byte key,
provided through `SKELETON_OPERATOR_HMAC_KEY_HEX`; never commit or log it.

Example invocation after the real model and states are installed:

```bash
python scripts/run_ai_work_native_acceptance.py \
  --model-root /private/installed-gguf \
  --spine-state /private/spine-state \
  --work-state /private/work-state \
  --capacity-root /private/capacity \
  --tenant local --subject operator \
  --max-new-tokens 128 --context 2048 --threads 4 \
  --approve-real-model-test --prompt-stdin < /private/prompt.txt
```

The command: checks installed model bytes/license, activates the true
isolated native backend; creates a canonical session; HMAC-signs and atomically
consumes an operator-approved submit ticket; durably allocates tokens and
writes an unknown-effect dispatch fence; runs the actual SupervisedAI turn
once; proves committed receipt by canonical SQLite replay; atomically charges
tokens and appends full-hash journal/outbox; shuts down the model; cold-reopens
the job queue read-only and verifies its integrity head.

The command fails closed without a verified local model, key, private
directories, explicit operator approval or enough CPU/memory/IO resources.
Neither source tests nor a successful single-machine run establish target
Windows/WSL2 device qualification, high/low-memory performance, native
cancellation behavior, third-party model rights outside the installer
approval, or required exact-head CI/security success.
