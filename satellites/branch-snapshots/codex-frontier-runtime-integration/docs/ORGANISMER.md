# Organismer — 10× path + social SOTA

Organism = cortex mouths + Hoag galaxy + Genos gene + social pointers.
Organismer = one clipped step that compounds all four toward `G = 10`.

```
G' = G * (1 + η * M * H * C * S * (1 - ε))
```

`S` is source density (lab / arXiv / X / ArchiveX handles bound this step).
Per-step growth clipped to `[1.00, 1.22]`.

## Social layer (no prose)

- `skeleton/social/sources.py` — reputable houses (arXiv, Xarchive, Wayback,
  X status, xAI, Anthropic, OpenAI, DeepMind, Meta, Stanford CRFM, HF papers).
- `archivex.py` — status URL → xarchive + CDX + wayback pointers. No GET.
- `ingest.py` — regex URLs out of a stimulus.
- Seeded field pointers include Recuris, MindMemOS, O-Mem, MemGen,
  proactive memory, Context Codec, x-archive-rag, xf, Xarchive about.

Xarchive fact: it searches Wayback CDX and stores no post copies.
House copies that contract.

## CLI / HTTP

```
python -m skeleton organismer "like Elden Ring https://arxiv.org/abs/2608.24876"
python -m skeleton social "https://x.com/user/status/123"
GET/POST /cortex/organismer
GET/POST /cortex/social
```
