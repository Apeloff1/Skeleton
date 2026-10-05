from __future__ import annotations

import hashlib
import pytest

from skeleton.documentation.runtime import (
    CheckStatus, DocumentationError, DocumentationSource, GeneratedDocument,
    GeneratedSection, GeneratorIdentity, SourceDigestSet, SourceKind,
    assert_clean_regeneration, generated_manifest, markers,
    render_generated_document, replace_generated_section, validate_links,
    validate_owned_sections, validate_references,
    validate_version_relationships,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def source_set(reverse=False):
    items = (
        DocumentationSource("source.plan", SourceKind.MACHINE, "machine/ai_master_plan.json", sha("plan")),
        DocumentationSource("source.rationale", SourceKind.HUMAN, "docs/plan/MASTER_PLAN.md", sha("rationale")),
    )
    return SourceDigestSet(tuple(reversed(items)) if reverse else items)


def generator(version="1.0.0"):
    return GeneratorIdentity("skeleton.docs", version, sha("generator-code"))


def section(body="generated content", *, sources=None, gen=None):
    sources = sources or source_set()
    gen = gen or generator()
    return GeneratedSection("capabilities", sources.digest, gen.digest, body)


def test_source_digest_set_is_deterministic():
    assert source_set().digest == source_set(reverse=True).digest


def test_duplicate_source_identity_rejected():
    item = DocumentationSource("source.plan", SourceKind.MACHINE, "machine/plan.json", sha("x"))
    with pytest.raises(DocumentationError, match="duplicate source"):
        SourceDigestSet((item, item))


def test_generated_document_rejects_stale_source_digest():
    sources = source_set()
    stale = GeneratedSection("capabilities", sha("old"), generator().digest, "body")
    with pytest.raises(DocumentationError, match="source digest is stale"):
        GeneratedDocument("docs/generated/capabilities.md", generator(), sources, (stale,))


def test_generated_document_rejects_stale_generator():
    sources = source_set()
    stale = GeneratedSection("capabilities", sources.digest, generator("0.9.0").digest, "body")
    with pytest.raises(DocumentationError, match="generator identity is stale"):
        GeneratedDocument("docs/generated/capabilities.md", generator(), sources, (stale,))


def test_replacement_preserves_human_authored_bytes():
    begin, end = markers("capabilities")
    original = "# Human rationale\nDO NOT CHANGE\n\n" + begin + "\nold\n" + end + "\n\n## Warning\nkeep me\n"
    updated = replace_generated_section(original, section("new\nordered"))
    assert updated.startswith("# Human rationale\nDO NOT CHANGE\n\n")
    assert updated.endswith("\n\n## Warning\nkeep me\n")
    assert "old" not in updated
    assert "new\nordered" in updated


def test_missing_marker_fails_closed_instead_of_appending():
    with pytest.raises(DocumentationError, match="exactly once"):
        replace_generated_section("# human only\n", section())


def test_duplicate_markers_fail_closed():
    begin, end = markers("capabilities")
    doc = f"{begin}\na\n{end}\n{begin}\nb\n{end}"
    with pytest.raises(DocumentationError, match="exactly once"):
        replace_generated_section(doc, section())


def test_reversed_markers_fail_closed():
    begin, end = markers("capabilities")
    with pytest.raises(DocumentationError, match="malformed"):
        replace_generated_section(end + "\nbody\n" + begin, section())


def test_generated_body_cannot_inject_ownership_markers():
    begin, _ = markers("capabilities")
    with pytest.raises(DocumentationError, match="ownership markers"):
        section("payload\n" + begin)


def test_owned_section_validation_reports_failure_not_silent_success():
    checks = validate_owned_sections("# docs", ["capabilities"])
    assert checks[0].status is CheckStatus.FAIL


def test_reference_validation_is_explicit_and_deterministic():
    doc = "See [[ref:VOL-088]] and [[ref:CTRL.MISSING]]."
    checks = validate_references(doc, {"VOL-088"})
    by_id = {c.check_id: c.status for c in checks}
    assert by_id["reference:VOL-088"] is CheckStatus.PASS
    assert by_id["reference:CTRL.MISSING"] is CheckStatus.FAIL


def test_clean_regeneration_rejects_any_drift():
    assert_clean_regeneration("same\n", "same\n")
    with pytest.raises(DocumentationError, match="drift"):
        assert_clean_regeneration("old\n", "new\n")


def test_manifest_binds_generator_sources_sections_and_policy():
    sources = source_set()
    gen = generator()
    doc = GeneratedDocument("docs/generated/capabilities.md", gen, sources, (section(sources=sources, gen=gen),))
    manifest = generated_manifest(doc)
    assert manifest["source_digest_set"] == sources.digest
    assert manifest["generator"]["digest"] == gen.digest
    assert manifest["manifest_digest"] == doc.manifest_digest
    assert manifest["editing_policy"] == "regenerate-derived-sections-do-not-hand-edit"


def test_manifest_changes_when_generator_version_changes():
    sources = source_set()
    first_gen = generator("1.0.0")
    second_gen = generator("1.0.1")
    first = GeneratedDocument("docs/generated/capabilities.md", first_gen, sources, (section(sources=sources, gen=first_gen),))
    second = GeneratedDocument("docs/generated/capabilities.md", second_gen, sources, (section(sources=sources, gen=second_gen),))
    assert first.manifest_digest != second.manifest_digest


def test_manifest_changes_when_source_changes():
    gen = generator()
    first_sources = source_set()
    second_sources = SourceDigestSet((
        DocumentationSource("source.plan", SourceKind.MACHINE, "machine/ai_master_plan.json", sha("changed")),
        DocumentationSource("source.rationale", SourceKind.HUMAN, "docs/plan/MASTER_PLAN.md", sha("rationale")),
    ))
    first = GeneratedDocument("docs/generated/capabilities.md", gen, first_sources, (section(sources=first_sources, gen=gen),))
    second = GeneratedDocument("docs/generated/capabilities.md", gen, second_sources, (section(sources=second_sources, gen=gen),))
    assert first.manifest_digest != second.manifest_digest


def test_reference_validation_rejects_malformed_reference_syntax():
    checks = validate_references("See [[ref:../escape]] and [[ref:VOL-089]].", {"VOL-089"})
    assert [check.status for check in checks] == [CheckStatus.PASS, CheckStatus.FAIL]
    assert any(check.check_id.startswith("reference-invalid:") for check in checks)


def test_markdown_link_validation_covers_local_external_and_unsafe_paths():
    document = (
        "[plan](machine/ai_master_plan.json) "
        "[missing](docs/missing.md) "
        "[escape](../secret.md) "
        "[secure](https://example.invalid/docs) "
        "[unsafe](http://example.invalid/docs) "
        "[anchor](#scope)"
    )
    checks = validate_links(document, {"machine/ai_master_plan.json"})
    statuses = [check.status for check in checks]
    assert statuses.count(CheckStatus.PASS) == 3
    assert statuses.count(CheckStatus.FAIL) == 3


def test_image_targets_are_not_misclassified_as_document_links():
    assert validate_links("![diagram](docs/generated/diagram.svg)", set()) == ()


def test_version_relationship_validation_detects_stale_missing_and_extra_values():
    checks = validate_version_relationships(
        {"schema": "2", "generator": "1.0.0", "extra": "1"},
        {"schema": "2", "generator": "1.0.1", "required": "7"},
    )
    by_id = {check.check_id: check.status for check in checks}
    assert by_id["version:schema"] is CheckStatus.PASS
    assert by_id["version:generator"] is CheckStatus.FAIL
    assert by_id["version:required"] is CheckStatus.FAIL
    assert by_id["version:extra"] is CheckStatus.FAIL


def test_source_set_is_nonempty_bounded_and_typed():
    with pytest.raises(DocumentationError, match="non-empty"):
        SourceDigestSet(())
    with pytest.raises(DocumentationError, match="invalid source"):
        SourceDigestSet(("not-a-source",))


def test_document_requires_nonempty_typed_sections():
    sources = source_set()
    gen = generator()
    with pytest.raises(DocumentationError, match="requires sections"):
        GeneratedDocument("docs/generated/empty.md", gen, sources, ())
    with pytest.raises(DocumentationError, match="section set"):
        GeneratedDocument("docs/generated/bad.md", gen, sources, ("not-a-section",))


def test_source_kind_must_be_typed_not_free_form():
    with pytest.raises(DocumentationError, match="SourceKind"):
        DocumentationSource("source.plan", "machine", "machine/plan.json", sha("x"))


def test_unterminated_reference_marker_is_reported_as_failure():
    checks = validate_references(
        "See [[ref:VOL-089 and [[ref:VOL-090]].",
        {"VOL-089", "VOL-090"},
    )
    assert any(
        check.status is CheckStatus.FAIL
        and check.check_id.startswith("reference-invalid-framing:")
        for check in checks
    )


def test_repository_paths_reject_traversal_segments():
    with pytest.raises(DocumentationError, match="repository-relative"):
        DocumentationSource(
            "source.escape",
            SourceKind.MACHINE,
            "docs/../secret.md",
            sha("x"),
        )
    sources = source_set()
    gen = generator()
    with pytest.raises(DocumentationError, match="repository-relative"):
        GeneratedDocument(
            "docs/../generated.md",
            gen,
            sources,
            (section(sources=sources, gen=gen),),
        )


def test_multi_section_materialization_is_deterministic_and_preserves_human_bytes():
    sources = source_set()
    gen = generator()
    first = GeneratedSection("alpha", sources.digest, gen.digest, "A")
    second = GeneratedSection("beta", sources.digest, gen.digest, "B")
    document = GeneratedDocument(
        "docs/generated/example.md",
        gen,
        sources,
        (second, first),
    )
    alpha_begin, alpha_end = markers("alpha")
    beta_begin, beta_end = markers("beta")
    template = (
        "# Human rationale\nKEEP\n"
        + beta_begin + "\nold-b\n" + beta_end
        + "\nwarning\n"
        + alpha_begin + "\nold-a\n" + alpha_end
        + "\nTAIL\n"
    )

    rendered = render_generated_document(template, document)

    assert rendered.startswith("# Human rationale\nKEEP\n")
    assert rendered.endswith("\nTAIL\n")
    assert "\nwarning\n" in rendered
    assert "old-a" not in rendered and "old-b" not in rendered
    assert alpha_begin + "\nA\n" + alpha_end in rendered
    assert beta_begin + "\nB\n" + beta_end in rendered
    assert render_generated_document(rendered, document) == rendered

def test_generated_body_cannot_inject_other_section_ownership_markers():
    other_begin, other_end = markers("earlier-section")
    with pytest.raises(DocumentationError, match="ownership markers"):
        GeneratedSection(
            "later-section",
            source_set().digest,
            generator().digest,
            "payload\n" + other_begin + "\nforged\n" + other_end,
        )
