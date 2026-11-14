# Ordered guarded AI ingress — large-source batch 2026-11-03

Build order: contracts -> authenticated principal -> model/tokenizer pins ->
resource budgets -> source and private memory evidence -> explicit grants ->
bounded scheduling -> native inference service -> durable chat commit ->
effect receipts -> recovery inspection -> offline evaluation.

384 executable policy cases, organized into 16 independently reviewed
control domains, cover permissive boundaries and deliberate denials.
No fixture claims generation from a real checkpoint. Run
python -m skeleton.ai.runtime.operational_ai.guarded_request.cli
and python -m unittest discover -s skeleton/testing -p 'test_guarded_request*.py' -v
only against the completed source tree.

The dispatch wrapper accepts a *preexisting* native OfflineAIService and
does not create any competing model, authoritative chat state, training
claims, model weights, install package or public-facing server.
Do not mark these checks passed if the real native model, token counter,
clean-install, cross-process custody, exact-head CI or device evidence
has not been executed and independently verified.
