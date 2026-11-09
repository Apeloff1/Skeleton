"""Regression coverage for versioned Canvas runtime hook compatibility."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from skeleton.ai.webcrawler.game_scale_campaign_hub import _level_with_completion
from skeleton.ai.webcrawler.game_scale_feedback import instrument_playable_telemetry


def test_telemetry_accepts_current_damage_guard_and_instruments_once() -> None:
    html = (
        '<script>const state={paused:false,won:false};'
        'function physicsStep(dt){const p=state.player;}'
        'function restart(){}'
        'function loseLife(){const p=state.player;'
        'if(!p.alive||p.invincible>0) return;state.lives--;}'
        'function updateGameState(){state.won=true;state.score+=250}'
        'requestAnimationFrame(frame);</script>'
    )
    result = instrument_playable_telemetry(
        html, SimpleNamespace(fingerprint="a" * 64)
    )
    assert 'if(!p.alive||p.invincible>0) return;_gameTelemetryPush("damage");' in result
    assert result.count('const gameTelemetry=') == 1
    assert result.count('gameTelemetryPush("victory")') == 1
    with pytest.raises(ValueError, match="unrecognized game engine telemetry hooks"):
        instrument_playable_telemetry(html.replace("function physicsStep(dt){", "function physicsStep(x){"), SimpleNamespace(fingerprint="a" * 64))


def test_campaign_completion_instruments_unique_earned_goal_statement() -> None:
    html = (
        '<script>if(state.player.alive&&intersects(state.player,state.goal)){'
        'const locked=scene.genre==="puzzle" && state.pickups.some(item=>item.active);'
        'if(!locked){state.won=true;state.score+=250}}'
        'requestAnimationFrame(frame);</script>'
    )
    result = _level_with_completion(html, "campaign-1", "chapter-01")
    assert 'state.won=true;state.score+=250;window.parent.postMessage(' in result
    assert result.count("skeleton.game.campaign.completed.v1") == 1
    assert 'if(!locked){state.won=true;' in result
    with pytest.raises(ValueError, match="unique goal event"):
        _level_with_completion(html.replace("state.won=true;", "state.won=false;"), "campaign-1", "chapter-01")
    with pytest.raises(ValueError, match="unique goal event"):
        _level_with_completion(html + html, "campaign-1", "chapter-01")
