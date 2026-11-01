# Accessible combat campaign captions

The `combat-campaign-captions` command converts canonical, deterministic
combat campaign journals into screen-reader-friendly offline narration. The
canonical turn-combat engine still determines every action, damage event,
knockout, win, and reward. Captions are never a source of game authority.

## End-user workflow

```bash
python -m skeleton combat-campaign-captions demo
python -m skeleton combat-campaign-captions build --session-json "$CAMPAIGN_SAVE"
python -m skeleton combat-campaign-captions verify --transcript-json "$TRANSCRIPT"
python -m skeleton combat-campaign-captions page --transcript-json "$TRANSCRIPT" --offset 0 --limit 24
```

Use `combat-campaign demo` or `combat-campaign advance` to produce canonical
terminal or partial checkpoints. The `build` command replays the entire
checkpoint before generating a transcript. Each caption records a stable
sequence number, encounter identity, turn, actor, target, action, damage,
healing, knockout flag, replay-derived after-state digest, and turn receipt.
A manifest records the source and session digests, completed encounters,
earned currency, and aggregate effects. JSON output is deterministic.

The `verify` command reconstructs all captions from the saved canonical
campaign; editing text, damage, turn ordering, rewards, or source is rejected.
The `page` command verifies the complete transcript before exposing a bounded
slice. Pages carry the parent transcript receipt and source manifest so a UI
can request successive slices without confusing campaigns.

## Boundaries

Maximum 128 canonical combat turns across four authored encounters, at most
64 captions per page, and a 128 KiB serialized output bound. Malformed JSON,
unknown fields, incompatible saves, noncanonical combat, or excessive payloads
fail closed with exit status 2. No file paths, network calls, scripts, or
provider models are evaluated. SHA-256 receipts establish local integrity and
replay consistency, **not** authenticity, provenance, or author permission.
The wider application's authorization and signed distribution controls remain
mandatory for consumer release.
