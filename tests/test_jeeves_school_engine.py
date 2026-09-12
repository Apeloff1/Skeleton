from skeleton.intelligence.collaboration import (
    CollaborationContext,
    CollaborationRole,
    collaboration_prompt,
    suggestion_window,
)
from skeleton.intelligence.narrative import (
    DialogueChoice,
    DialogueGraph,
    DialogueNode,
    DialogueState,
    NpcRelationship,
)
from skeleton.intelligence.quests import QuestObjective, QuestProgress, QuestTemplate, rank_quest_candidates


def test_dialogue_graph_enforces_requirements_and_persists_effects():
    graph = DialogueGraph({
        "start": DialogueNode("start", "Hello", (
            DialogueChoice("open", "Open up", "bond", {"trust:marina": 20, "rep:merchants": 5}),
            DialogueChoice("locked", "Reveal secret", "secret", requirements={"item": "key"}),
        )),
        "bond": DialogueNode("bond", "Trusted"),
        "secret": DialogueNode("secret", "Secret"),
    })
    state = DialogueState("start", inventory=frozenset())
    assert [c.id for c in graph.available_choices(state)] == ["open"]
    next_state = graph.advance(state, "open")
    assert next_state.node_id == "bond"
    assert next_state.trust["marina"] == 20
    assert next_state.reputation["merchants"] == 5


def test_relationship_signal_and_bounds():
    relationship = NpcRelationship("bill").adjust(disposition=100, trust=90, memory="helped_in_storm")
    assert relationship.social_signal() == "bonded"
    assert relationship.disposition == 100
    assert "helped_in_storm" in relationship.memory_tags


def test_quest_readiness_and_adaptive_ranking():
    intro = QuestTemplate("intro", "main_story", (QuestObjective("catch", "fish", 1),), tags=frozenset({"fishing"}))
    side = QuestTemplate("side", "side", (QuestObjective("talk", "marina", 1),), prerequisites=("intro",), tags=frozenset({"fishing", "social"}))
    progress = QuestProgress(completed=frozenset({"intro"}), objective_counts={"marina": 1})
    assert progress.ready_to_turn_in(side)
    ranked = rank_quest_candidates((intro, side), progress, preferred_tags=frozenset({"social"}))
    assert ranked[0].id == "side"


def test_collaboration_roles_and_bounded_context():
    ctx = CollaborationContext(CollaborationRole.NAVIGATOR, recent_changes=("fix parser", "add test", "rename symbol", "latest"))
    assert "navigator" in collaboration_prompt(ctx, "teach recursion")
    assert suggestion_window(20, 30) == (10, 25)
