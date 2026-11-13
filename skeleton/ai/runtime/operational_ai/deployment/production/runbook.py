"""Non-executable runbook data for first install, recovery and release holds."""
from __future__ import annotations
BUILD_STAGES=(
 ('MBW-00','canonical identity and contracts'),
 ('MBW-01','durable state, receipts, outbox and crash fencing'),
 ('MBW-02','approved local model, tokenizer, context and memory'),
 ('MBW-03','independent effect authorizations'),
 ('MBW-04','durable AI orchestration and no-retry recovery'),
 ('MBW-05','private client API and committed event replay'),
 ('MBW-06','actual native canary and regression evidence'),
 ('MBW-07','first install, device checks and release gate'),
)
RELEASE_HOLDS=('model-rights','device-hardware','native-checkpoint-e2e',
 'first-install','recovery-drill','integration-ci','security','malware','artifact-policy')
