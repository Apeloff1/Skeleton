# Graph semantics

The repository index uses a directed typed multigraph. Node IDs are stable strings. File nodes use `file:<path>`; symbols use `symbol:<path>:<qualified-name>`; subsystems use `subsystem:<id>`; capabilities use `capability:<id>`; batches use `batch:<Bxxx>`.

## Edge direction

Edges point from consumer/child to provider/parent unless the relation is intrinsically hierarchical.

- `imports`: source file → imported local file/module
- `references-module`: source file → candidate local module when resolution is conservative
- `tests`: test file → source file/subsystem under test
- `contains`: subsystem/file → child file/symbol
- `declares-dependency`: manifest → external dependency
- `workflow-uses`: workflow → action/script/build entrypoint
- `evidence-for`: test/benchmark/file → capability
- `owned-by`: file/subsystem → ownership zone

`reverse_edges` is materialized so change impact does not need to invert the graph at query time.

## Precision levels

Every semantic edge may carry a precision label:

- `compiler`: derived from compiler/SCIP data;
- `ast`: derived from a language AST;
- `manifest`: derived from structured dependency/build metadata;
- `lexical`: conservative text extraction;
- `structural`: path/config inference.

Impact analysis must preserve precision. A conservative lexical dependency can expand the candidate impact set but must never be presented as compiler-proven.

## Evidence levels

- `surface`: implementation-like path/symbol exists;
- `tested`: focused regression evidence exists;
- `benchmarked`: versioned performance/quality benchmark exists;
- `release-evidenced`: CI/release evidence validates the capability on a declared target matrix.

No SOTA claim is valid from `surface` evidence alone.
