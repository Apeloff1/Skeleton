"""Replacing a persona fact must not keep the old token charge."""

from skeleton.memory.cag import PersonaContext


def test_replacing_a_key_releases_the_previous_tokens() -> None:
    persona = PersonaContext("p", "Ada", "system", max_tokens=10_000)
    persona.add_knowledge("bio", ["a" * 400], importance=1.0)
    charged = persona.current_tokens
    persona.add_knowledge("bio", ["short"], importance=1.0)
    assert persona.current_tokens < charged
    assert persona.current_tokens == persona.estimate_tokens("short")
