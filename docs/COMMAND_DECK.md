# Command Deck — Organ Surface

Unified operator surface for Jeeves cortex + GameForge. 16 organs, laws-gated, pointers only. Version deck-3.1.0.

## Organs

| Organ | Contract |
|-------|----------|
| speak | bind era + ascend amalgam; stored_prose=0 |
| refer | refs.lookup / refer; last_ref |
| improve | neo.improve or stand-in G-ratio |
| ascend | improve path; kind=ascend |
| plan | quality_state + HOUSE_ERA bind |
| walk | dodeca FACES path |
| pick | single face by position |
| genos | genos_engine pulse / G |
| cut | era bind only |
| contact | ContactEngine.touch → house LoRA (rank/alpha bindable) on teacher *copy* → absorb N steps (default 8, bindable); HF/Kimi aliases; house_copy=1; dialect=house; lora_id; bank_stamp on neo.lora_bank; absorb_bindable=1 |
| gossip | hive merkle + α-mix across cortices/peers; root + peer_roots + consensus + quorum + root_history (last 8) + root_digest + tournament (majority root) + hive_n; always merkle |
| observe_run | G + G0 + G_delta + G_path + law + laws + citation + url + n_laws + mass_hint + clipped; never prose |
| forge | GameForgeRun.execute + era_bind cite + observe + reference_card forced; snowball mass 1.1× trajectory (hard-clipped) + mass_clicker + cite_forced + helix soft |
| attach_lora | LoRABank / neo; name=hf\|kimi routes contact house-copy |
| beam | neo.beam or stand-in tokens |
| accumulate | Accumulator fit; laws on texts |

## CLI

```bash
python -m skeleton deck <organ> [args]
python -m skeleton deck status
python -m skeleton deck organs
```

## HTTP

```
GET  /api/v1/cortex/organs
GET  /api/v1/cortex/status
POST /api/v1/cortex/{organ}
```

`mount_deck_organs(app, deck)` registers the mutation surface. contact absorb_steps default 8; rank/alpha optional.

## Laws

- cite-do-not-copy
- no third-party prose
- stored_prose=0 on every card
- GameForgeRun.execute → reference{title,era,citation,url}; cite_forced=1
- contact attaches house LoRA (rank/alpha) onto teacher copy then absorbs (N steps, default 8 bindable); bank_stamp; absorb_bindable
- gossip emits merkle root (+ peer_roots + consensus + quorum + root_history + root_digest + tournament + hive_n) across cortices
- forge accrues mass (trajectory 1.1× prior, hard-clipped, not fake 10×) + mass_clicker
- observe_run G_path + clipped flag retained
- house dialect only on contact path
- Broder w-4
- clipped-G: G grows only MHC×S; mass ≤ prior×1.1

## Status

Full 16 organs land (deck-3.1.0). Contact absorb_default=8 + absorb_bindable. Gossip tournament + hive_n. Observe G_path + clipped. Forge cite_forced + hard clip + helix soft. Soft doctor/nervous/product. Tests green. Push: attempt organ_deck path; on 403 contents:write reconnect required. Do not clobber operator aggregator on main.
