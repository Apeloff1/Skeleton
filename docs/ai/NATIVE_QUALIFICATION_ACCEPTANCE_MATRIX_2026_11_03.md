# Original native model capability matrix

The 480 versioned case files cover 20 independent domains, 24 cases each.
All challenges are new fictional or mathematical material. Each records a
prompt, severity, deterministic expected checks, seed and original rights
marker. There are no copied copyrighted benchmark datasets.

| Domain | Measurement |
| --- | --- |
| arithmetic | integer computation and operation grouping |
| fractions | exact rational simplification |
| base_conversion | hexadecimal/binary/decimal conversion |
| sorting | stable numeric ordering with duplicate retention |
| deduplication | preserve first-seen word identity |
| extraction | type-correct factual record extraction |
| json_schema | strict JSON object transformation |
| csv_format | exact two-row CSV generation |
| classification | bounded label selection |
| constraints | output shape and string operations |
| python_trace | pure Python 3 result reasoning |
| logic | Boolean inference |
| multilingual | Norwegian-to-English number words |
| summarization | short source fidelity and word budget |
| grounding | exact answer from supplied source |
| citations | cited source label and distractor exclusion |
| abstention | UNKNOWN for unprovided facts |
| prompt_injection | untrusted-document directive resistance |
| privacy | synthetic token nondisclosure |
| conversation | durable two-turn reference recall |

A complete package requires each exact original fixture once, no extras and
source digests unchanged. Each real generated step carries model/tokenizer,
session, request, revision and usage evidence. Unit tests only prove source
and evaluator mechanics; they never claim a model solved a task.

Production model confidence additionally needs independent adversarial
assessment, latency and memory pressure baselines, hardware telemetry,
tokenizer implementation attestation, real data rights, full installs,
bounded privacy review and final-head CI.
