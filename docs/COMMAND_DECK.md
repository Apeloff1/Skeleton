# Command deck

The organism over HTTP and `python -m skeleton deck`.

```
GET  /api/v1/cortex/status
GET  /api/v1/cortex/deck
GET  /api/v1/cortex/laws
GET  /api/v1/cortex/refs
GET  /api/v1/cortex/dodeca
POST /api/v1/cortex/think    {"stimulus":"..."}
POST /api/v1/cortex/speak    {"stimulus":"like Elden Ring"}
POST /api/v1/cortex/refer    {"stimulus":"elden ring","live":false}
POST /api/v1/cortex/improve  {"stimulus":"like Elden Ring","rounds":6}
POST /api/v1/cortex/ascend   {"stimulus":"like Elden Ring","rounds":6}
POST /api/v1/cortex/plan     {"vision":"like Elden Ring"}
POST /api/v1/cortex/genos    {"stimulus":"plan tensor ttk"}
POST /api/v1/cortex/dodeca/walk {"steps":3}
POST /api/v1/cortex/dodeca/pick {"index":7}
POST /api/v1/cortex/cut     {"stimulus":"like Elden Ring","rounds":3}
```

`like <title>` cites the Steam pointer, trains house mouths, pulses G.
Tenfold is the heading. Source prose is never stored.

```
python -m skeleton deck
python -m skeleton deck "like Elden Ring"
python -m skeleton deck --walk 3
python -m skeleton cut "like Elden Ring"
```
