# Dragon Wave 19 — Deterministic source declaration intelligence

The actual canonical Dragon source extractor gains a bounded, inert
structural annotation layer for existing Python, JavaScript, TypeScript,
Rust, Go, Java, C and C++ source MIME types.

Python uses a finite iterative AST walk, reporting class/function/async
function symbols, scoped declaration names, declared argument slots and
import module labels. The parser *never imports, compiles, evaluates or
executes* the source. Malformed source stays plain unreviewed source text;
it cannot be misrepresented as syntactically confirmed.

Other languages use a finite comment/literal scrubber and conservative
anchored declaration patterns. Results explicitly say they are lexical
candidates rather than compiler-verified symbols. No import is resolved.
All symbol/line and module labels are bounded, with no extracted function
bodies, literal values or remote URLs in the annotations.

Annotations are added to the same canonical captured source, are subject to
the original response/text caps, and retain the original content hash,
provenance, consent, source-rights, robots and reviewed-status boundaries.
The implementation-digest input includes all four new modules.

The source CI runs direct Python AST, lexical-language, syntax-failure,
resource-limit and literal-redaction tests and actual scripted run_slice
capture/replay regressions. None of this establishes code correctness,
quality, security or authorization for downstream use. No provider SDK,
network client, scheduler, new store or execution grant is introduced.
