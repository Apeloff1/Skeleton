# Wave 31 — AI-model artifact intelligence without inference or loading

Native bounded source inspection now supports safetensors tensor headers,
GGUF v3 model directories, and ONNX protobuf model/graph envelopes through
the original canonical Dragon CrawlRun capture.

Safetensors validates strict UTF-8 JSON headers, exact data offsets,
non-overlapping segments, element dtype/shape byte size consistency,
total finite tensor count and available source payload framing.
Model names, raw metadata, tensor values and secret-like identifiers are
never projected.

GGUF v3 reads finite little-endian typed metadata, tensor count,
alignment, shape dimensions, offset declarations and encoded element
type class counts. No weights, vocabularies, tokenizer internals,
metadata values or source-declared provider actions are loaded.
This bounded source directory is not proof of model weight integrity.

ONNX uses a finite protobuf wire scanner over the top-level ModelProto,
GraphProto and NodeProto envelopes only. It counts operator declarations,
initializer envelopes, inputs and outputs without reading raw tensor data,
opening external_data references or creating an ONNX inference session.

Every admitted MIME type remains subject to original host scope,
current consent, robots, public-IP/DNS and redirect policy, metered request
and byte reservation, capture rights, source hashing, and Mongo custody.
All model source observations stay unreviewed external evidence, never
training-authorized, unqualified for deployment and not a license grant.

Source CI compiles all four modules and verifies structural negative tests,
invalid/truncated/bomb headers, fabricated GraphProto wires, credential
omission, real scripted run_slice capture and exact snapshot replay.
