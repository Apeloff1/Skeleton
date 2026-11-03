"""Exact text and source separation between challenge, train and other fixtures."""
from __future__ import annotations
from .challenge_catalog import iter_challenges
from .canonical import digest
from .errors import reject
from ..native_candidate.catalog import iter_examples
from ..native_candidate.dedup import text_digest


def scan()->dict:
    challenges=tuple(iter_challenges())
    training=tuple(iter_examples())
    prompt_hashes={text_digest(x.prompt):x.case_id for x in challenges}
    expected_hashes={digest([text_digest(x.prompt),text_digest(x.expected)]):x.case_id
                     for x in challenges}
    if len(prompt_hashes)!=len(challenges) or len(expected_hashes)!=len(challenges):
        reject("challenge-internal-overlap")
    train_prompts={text_digest(x.prompt) for x in training}
    exact_train=tuple(sorted(set(prompt_hashes)&train_prompts))
    from ..native_qualification.corpus import iter_cases
    native_prompt_hashes=set()
    for case in iter_cases():
        for step in case.steps:
            native_prompt_hashes.add(text_digest(step.prompt))
    exact_external=tuple(sorted(set(prompt_hashes)&native_prompt_hashes))
    return {
        "challenge_cases":len(challenges),"train_cases":len(training),
        "native_other_benchmark_prompts":len(native_prompt_hashes),
        "exact_training_overlap":len(exact_train),
        "exact_other_benchmark_overlap":len(exact_external),
        "independent_near_duplicate_review_complete":False,
        "exact_clear":not exact_train and not exact_external,
        "source_sha256":digest([c.sha256 for c in challenges]),
        "model_trained":False,
    }


def require_clear(proof:dict)->None:
    if type(proof) is not dict or proof.get("exact_clear") is not True:
        reject("challenge-exact-contamination")
