# Wave 32 — Original game-world tilemaps and tilesets

The canonical Dragon crawler now reads finite Tiled TMX map files,
Tiled TSX tile atlases, and Tiled JSON maps as inert structural evidence.

A common strict tilemap kernel validates finite tile/scene dimensions,
uint32 tile identifiers and flip flags, occupancy, layer count, object
count, image-layer count, external tileset declaration count, and
bounded infinite-map chunk coordinates and cell counts. No tile images,
textures, links, world scripts, game-engine physics or asset libraries are
loaded. Source-published object names, private properties, image paths
and external tileset URLs are excluded from the retained projection.

TMX XML rejects DTD and entity declarations, oversized or overdeep
trees, unsupported encoded/compressed tile data, tilecount mismatches,
overlarge group nesting and invalid chunk dimensions. TSX records
tile/animation metadata but never follows sources or renders animation.

Tiled JSON enforces unique keys, finite JSON numbers, bounded nested
layers, finite and chunked tile IDs, and rejects unknown world commands
instead of treating them as executable source instructions.

Every source is retained by the existing CrawlRun only after owner
consent, robots, public destination validation, byte reservations and
capture rights. New MIME parsers enter code digest and source CI.
Tests exercise direct negative cases and the real metered canonical
worker capture/replay without external tile/media requests.
