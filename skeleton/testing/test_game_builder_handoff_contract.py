from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_ai_generator_route_queues_artifact_before_factory_navigation() -> None:
    source = _source("frontend/app/ai-game-generator.tsx")

    queue_call = "queueGameBuilderArtifact(data, type);"
    navigation = "router.replace('/game-factory');"
    assert queue_call in source
    assert navigation in source
    assert source.index(queue_call) < source.index(navigation)
    assert "onGenerated={handleGenerated}" in source


def test_game_factory_route_consumes_seed_and_uses_existing_create_contract() -> None:
    route = _source("frontend/app/game-factory.tsx")
    shell = _source("frontend/features/GameFactory/GameFactoryRouteModal.tsx")

    assert "GameFactoryRouteModal" in route
    assert "consumeGameBuilderArtifact()" in shell
    assert "formatGameBuilderDescription(artifact, 2000)" in shell
    assert "${API_BASE}/api/game-factory/create" in shell
    assert "JSON.stringify({ description: trimmed })" in shell
    assert "<GameFactoryModal visible={visible} onClose={onClose} colors={colors} />" in shell


def test_builder_handoff_is_bounded_ephemeral_and_not_url_serialized() -> None:
    handoff = _source("frontend/features/GameFactory/gameBuilderHandoff.ts")
    generator_route = _source("frontend/app/ai-game-generator.tsx")

    assert "DEFAULT_MAX_AGE_MS = 30 * 60 * 1000" in handoff
    assert "DEFAULT_DESCRIPTION_LIMIT = 1800" in handoff
    assert "DEFAULT_HANDOFF_PAYLOAD_LIMIT = 32 * 1024" in handoff
    assert "data: string;" in handoff
    assert "data: boundedPayload(data)" in handoff
    assert "serialized.slice(0, limit - 1)" in handoff
    assert "pendingArtifact" in handoff
    assert "pendingArtifact = null" in handoff
    assert "localStorage" not in handoff
    assert "sessionStorage" not in handoff
    assert "AsyncStorage" not in handoff
    assert "JSON.stringify(data" not in generator_route
    assert "params" not in generator_route.lower()
