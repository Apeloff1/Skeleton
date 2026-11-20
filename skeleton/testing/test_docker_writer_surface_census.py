"""Host-portable proof that every KNOWN direct Mongo source write is classified.

These source tests never import the production backend service, open Mongo
connections, create epochs, or execute an actual write against user data.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.persistence import docker_writer_surface_census as census


def _fixture_tree(tmp_path: Path) -> Path:
    for relative in census._SOURCES:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((census.ROOT / relative).read_bytes())
    return tmp_path


def _alter(root: Path, relative: str, original: str, forged: str) -> None:
    path = root / relative
    data = path.read_text(encoding="utf-8")
    assert data.count(original) == 1, (relative, original)
    path.write_text(data.replace(original, forged), encoding="utf-8")


def test_existing_three_production_writer_classes_are_fully_classified():
    result = census.census_canonical_mongo_mutators()
    assert result["schema"] == census.SCHEMA
    assert result["class_count"] == 3
    assert result["direct_mutation_method_count"] == 22
    assert result["class_mutation_method_counts"] == {
        "MongoConversationAuthority": 12,
        "MongoMemoryRepository": 8,
        "MongoMementoAuthority": 2,
    }
    assert result["classifications"] == {
        "actor_decorated": 14,
        "actor_guarded_internal": 6,
        "protected_legacy_deletion_denied": 1,
        "projection_only_ack_unfenced": 1,
    }
    assert result["direct_mongo_call_count"] >= 22
    assert result["bounded_read_aggregate_call_count"] == 3
    assert result["write_capable_aggregate_pipelines_detected"] is False
    assert result["unclassified_known_source_mutators"] == 0
    assert result["source_files_modified"] is False
    assert result["database_read_or_written"] is False
    assert result["external_writer_registry_exhaustive"] is False
    assert result["migration_quiescence_verified"] is False
    assert result["protected_jeeves_chat_qualified"] is False
    assert result["release_authorized"] is False


def test_denies_new_undecorated_mongo_writer_even_inside_existing_class(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    relative = "backend/core/conversations.py"
    path = root / relative
    source = path.read_text()
    marker = "    @fence_conversation_write\n    async def create_thread("
    assert source.count(marker) == 1
    injected = (
        "    async def silently_update(self, doc):\n"
        "        await self.messages.update_one({'_id': doc}, {'$set': {'x': 1}})\n\n"
    )
    path.write_text(source.replace(marker, injected + marker))
    with pytest.raises(census.WriterCensusError, match="unclassified"):
        census.census_canonical_mongo_mutators(root)


def test_missing_public_writer_decorator_is_denied(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "backend/core/conversations.py",
        "    @fence_conversation_write\n    async def create_thread(",
        "    async def create_thread(",
    )
    with pytest.raises(census.WriterCensusError, match="fence"):
        census.census_canonical_mongo_mutators(root)


def test_internal_recovery_cannot_remove_required_actor_writer_guard(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "backend/core/conversations.py",
        "epoch.require_actor_writer(tenant_id=tenant_id, actor_id=owner_id)",
        "pass  # forged removal of actor custody",
    )
    with pytest.raises(census.WriterCensusError, match="actor writer"):
        census.census_canonical_mongo_mutators(root)


def test_legacy_governed_deletion_must_deny_when_protected_epoch_active(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "backend/core/conversations.py",
        'if getattr(self, "canonical_source_epoch", None) is not None:\n'
        '            raise ConversationStorageUnavailable(\n'
        '                "protected governed deletion requires a cross-owner retirement fence"\n'
        '            )',
        'if False:\n'
        '            raise ConversationStorageUnavailable(\n'
        '                "protected governed deletion requires a cross-owner retirement fence"\n'
        '            )',
    )
    with pytest.raises(census.WriterCensusError, match="legacy governed"):
        census.census_canonical_mongo_mutators(root)


def test_projection_ack_exception_cannot_write_canonical_memory_record(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        '''        await self.projection_outbox.update_one(
            {
                "repository_namespace": self.repository_namespace,
                "event_id": event_key,''',
        '''        await self.records.update_one(
            {
                "repository_namespace": self.repository_namespace,
                "event_id": event_key,''',
    )
    with pytest.raises(census.WriterCensusError, match="projection acknowledgement"):
        census.census_canonical_mongo_mutators(root)


def test_memento_publication_cannot_drop_epoch_fence(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/mongo_memento_repository.py",
        "    @fence_memento_write\n    async def publish(",
        "    async def publish(",
    )
    with pytest.raises(census.WriterCensusError, match="fence"):
        census.census_canonical_mongo_mutators(root)


def test_known_class_identity_replacement_is_denied(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/mongo_memento_repository.py",
        "class MongoMementoAuthority:",
        "class ForgedMementoAuthority:",
    )
    with pytest.raises(census.WriterCensusError, match="class changed"):
        census.census_canonical_mongo_mutators(root)


def test_source_file_symlink_is_denied(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    role = "backend/core/conversations.py"
    file = root / role
    file.unlink()
    file.symlink_to(census.ROOT / role)
    with pytest.raises(census.WriterCensusError, match="untrusted"):
        census.census_canonical_mongo_mutators(root)


def test_invalid_or_unbounded_utf8_source_is_denied(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    file = root / "skeleton/persistence/mongo_memento_repository.py"
    file.write_bytes(b"\xff" + b"x" * 32)
    with pytest.raises(census.WriterCensusError, match="unavailable"):
        census.census_canonical_mongo_mutators(root)
    file.write_bytes(b"x" * (census._MAX_FILE_BYTES + 1))
    with pytest.raises(census.WriterCensusError, match="budget"):
        census.census_canonical_mongo_mutators(root)


def test_source_reader_denies_unlisted_relative_path_without_file_access(
    tmp_path: Path,
):
    with pytest.raises(census.WriterCensusError, match="root"):
        census._file_tree(tmp_path, "../../.env")


def test_census_cli_emits_only_bounded_non_authoritative_counts(capsys):
    assert census.main() == 0
    out, err = capsys.readouterr()
    assert err == ""
    parsed = json.loads(out)
    assert parsed["unclassified_known_source_mutators"] == 0
    assert parsed["external_writer_registry_exhaustive"] is False
    assert parsed["release_authorized"] is False
    assert "password" not in out.lower()
    assert "mongodb://" not in out


def test_census_cli_denies_missing_source_instead_of_success(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise census.WriterCensusError("PRIVATE Mongo URL")
    monkeypatch.setattr(census, "census_canonical_mongo_mutators", fail)
    assert census.main() == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert "PRIVATE" not in err
    assert "DENIED" in err


def test_aggregate_out_write_stage_cannot_pass_as_conversation_read(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "backend/core/conversations.py",
        '{"$group": {"_id": None, "bytes":',
        '{"$out": {"_id": None, "bytes":',
    )
    with pytest.raises(census.WriterCensusError, match="write-capable"):
        census.census_canonical_mongo_mutators(root)


def test_dynamic_pipeline_cannot_replace_fixed_regeneration_query(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "backend/core/conversations.py",
        "rows = await self.messages.aggregate(pipeline).to_list(length=64)",
        "rows = await self.messages.aggregate(untrusted_pipeline).to_list(length=64)",
    )
    with pytest.raises(census.WriterCensusError, match="stage inventory"):
        census.census_canonical_mongo_mutators(root)


def test_fixed_aggregate_pipeline_cannot_gain_runtime_merge_append(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "backend/core/conversations.py",
        '        ]\n        try:\n            rows = await self.messages.aggregate(pipeline)',
        '        ]\n        pipeline.append({"$merge": "outside"})\n'
        '        try:\n            rows = await self.messages.aggregate(pipeline)',
    )
    with pytest.raises(census.WriterCensusError, match="pipeline mutator"):
        census.census_canonical_mongo_mutators(root)


def test_unregistered_aggregate_even_without_direct_update_is_denied(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    path = root / "backend/core/conversations.py"
    contents = path.read_text(encoding="utf-8")
    marker = "    @fence_conversation_write\n    async def create_thread("
    assert contents.count(marker) == 1
    forged = (
        "    async def unexpected_aggregate(self):\n"
        '        await self.messages.aggregate([{"$merge": "outside"}])\n\n'
    )
    path.write_text(contents.replace(marker, forged + marker))
    with pytest.raises(census.WriterCensusError, match="aggregate"):
        census.census_canonical_mongo_mutators(root)


def test_raw_database_command_cannot_bypass_named_mongo_mutation_census(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    path = root / "backend/core/conversations.py"
    contents = path.read_text(encoding="utf-8")
    marker = "    @fence_conversation_write\n    async def create_thread("
    assert contents.count(marker) == 1
    injected = (
        "    async def hidden_command(self):\n"
        '        return await self.database.command({"delete": "conversation_threads"})\n\n'
    )
    path.write_text(contents.replace(marker, injected + marker))
    with pytest.raises(census.WriterCensusError, match="raw or dynamically"):
        census.census_canonical_mongo_mutators(root)


def test_canonical_docker_operator_static_census_never_invokes_docker(
    monkeypatch, capsys,
):
    from scripts import local_ai_docker as host

    def refuse(*args, **kwargs):
        pytest.fail("static writer census accessed Docker or app runtime")
    monkeypatch.setattr(host, "_run", refuse)
    monkeypatch.setattr(host, "inspect_config", refuse)
    assert host.main(["--mode", "cpu", "source-writer-census"]) == 0
    out, err = capsys.readouterr()
    assert err == ""
    result = json.loads(out)
    assert result["schema"] == census.SCHEMA
    assert result["external_writer_registry_exhaustive"] is False
    assert result["release_authorized"] is False


def test_unreachable_guard_in_memory_helper_cannot_admit_source_write(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        '        self._require_canonical_writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id)\n        owner_token = str(uuid4())',
        '        if False:\n'
        '            self._require_canonical_writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id)\n'
        '        owner_token = str(uuid4())',
    )
    with pytest.raises(census.WriterCensusError, match="unconditional"):
        census.census_canonical_mongo_mutators(root)


def test_guard_after_first_mutation_cannot_create_source_custody(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        '        self._require_canonical_writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id)\n        result = await self.idempotency.update_one(',
        '        result = await self.idempotency.update_one(',
    )
    with pytest.raises(census.WriterCensusError, match="unconditional"):
        census.census_canonical_mongo_mutators(root)


def test_nested_local_function_with_fake_actor_guard_cannot_admit_write(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        '        self._require_canonical_writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id)\n        owner_token = str(uuid4())',
        '        def pretend_guard():\n'
        '            self._require_canonical_writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id)\n'
        '        owner_token = str(uuid4())',
    )
    with pytest.raises(census.WriterCensusError, match="unconditional"):
        census.census_canonical_mongo_mutators(root)


def test_legacy_recovery_guard_condition_must_match_exact_epoch(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "backend/core/conversations.py",
        '        if epoch is not None:\n            epoch.require_actor_writer(tenant_id=tenant_id, actor_id=owner_id)',
        '        if epoch is not None and False:\n'
        '            epoch.require_actor_writer(tenant_id=tenant_id, actor_id=owner_id)',
    )
    with pytest.raises(census.WriterCensusError, match="unconditional"):
        census.census_canonical_mongo_mutators(root)


def test_recovery_guard_must_use_correct_source_actor(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "backend/core/conversations.py",
        'epoch.require_actor_writer(tenant_id=tenant_id, actor_id=owner_id)',
        'epoch.require_actor_writer(tenant_id=tenant_id, actor_id=thread_id)',
    )
    with pytest.raises(census.WriterCensusError, match="unconditional"):
        census.census_canonical_mongo_mutators(root)


def test_recovery_guard_cannot_be_swallowed_by_try_except(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "backend/core/conversations.py",
        '        if epoch is not None:\n            epoch.require_actor_writer(tenant_id=tenant_id, actor_id=owner_id)',
        '        try:\n'
        '            if epoch is not None:\n'
        '                epoch.require_actor_writer(tenant_id=tenant_id, actor_id=owner_id)\n'
        '        except Exception:\n'
        '            pass',
    )
    with pytest.raises(census.WriterCensusError, match="unconditional"):
        census.census_canonical_mongo_mutators(root)


def test_memory_helper_cannot_assert_different_actor_custody(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        'self._require_canonical_writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id)\n        owner_token = str(uuid4())',
        'self._require_canonical_writer(tenant_id=proposal.tenant_id, actor_id=proposal.memory_id)\n        owner_token = str(uuid4())',
    )
    with pytest.raises(census.WriterCensusError, match="unconditional"):
        census.census_canonical_mongo_mutators(root)


def test_memory_helper_cannot_assert_different_tenant_custody(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        'self._require_canonical_writer(tenant_id=proposal.tenant_id, actor_id=proposal.subject_id)\n        owner_token = str(uuid4())',
        'self._require_canonical_writer(tenant_id=proposal.namespace, actor_id=proposal.subject_id)\n        owner_token = str(uuid4())',
    )
    with pytest.raises(census.WriterCensusError, match="unconditional"):
        census.census_canonical_mongo_mutators(root)


def test_record_internal_projection_revision_guard_requires_record_subject(
    tmp_path: Path,
):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        'self._require_canonical_writer(tenant_id=record.tenant_id, actor_id=record.subject_id)',
        'self._require_canonical_writer(tenant_id=record.tenant_id, actor_id=record.memory_id)',
    )
    with pytest.raises(census.WriterCensusError, match="unconditional"):
        census.census_canonical_mongo_mutators(root)


def test_projection_ack_must_not_drop_pending_state_predicate(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        '                "published_at": None,\n            },\n            {"$set": {"published_at": _iso(instant)}},',
        '                "published_at": {"$exists": True},\n            },\n            {"$set": {"published_at": _iso(instant)}},',
    )
    with pytest.raises(census.WriterCensusError, match="projection"):
        census.census_canonical_mongo_mutators(root)


def test_projection_ack_must_not_upsert_new_record(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        '            {"$set": {"published_at": _iso(instant)}},\n        )',
        '            {"$set": {"published_at": _iso(instant)}},\n'
        '            upsert=True,\n        )',
    )
    with pytest.raises(census.WriterCensusError, match="projection"):
        census.census_canonical_mongo_mutators(root)


def test_projection_ack_must_not_change_memory_source_version(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        '            {"$set": {"published_at": _iso(instant)}},',
        '            {"$set": {"published_at": _iso(instant)}, "$inc": {"version": 1}},',
    )
    with pytest.raises(census.WriterCensusError, match="projection"):
        census.census_canonical_mongo_mutators(root)


def test_projection_ack_must_not_accept_foreign_event_identity(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        '                "event_id": event_key,\n                "published_at": None,',
        '                "event_id": "other",\n                "published_at": None,',
    )
    with pytest.raises(census.WriterCensusError, match="projection"):
        census.census_canonical_mongo_mutators(root)


def test_projection_ack_must_not_accept_foreign_namespace(tmp_path: Path):
    root = _fixture_tree(tmp_path)
    _alter(
        root, "skeleton/persistence/memory_repository.py",
        '                "repository_namespace": self.repository_namespace,\n'
        '                "event_id": event_key,\n'
        '                "published_at": None,',
        '                "repository_namespace": "other",\n'
        '                "event_id": event_key,\n'
        '                "published_at": None,',
    )
    with pytest.raises(census.WriterCensusError, match="projection"):
        census.census_canonical_mongo_mutators(root)
