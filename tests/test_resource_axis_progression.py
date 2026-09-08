"""resource-axis campaigns must be able to advance.

WorldKit.advance_progression and level_for were correct and unreachable — award_xp
is hardcoded to the xp-levels threshold path, so a kit declaring
{"model": "resource-axis", "resource": "years"} could not gain a single year.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from lib.player_manager import PlayerManager

ROOT = Path(__file__).resolve().parent.parent

RULESET = {
    "name": "The Slow Heart",
    "kit": "custom",
    "stat_schema": {"attributes": ["strength"], "vitals": ["hp", "blood"]},
    "progression": {"model": "resource-axis", "resource": "years",
                    "tiers": [1, 20, 100, 500],
                    "tier_names": ["Newborn", "Young", "Settled", "Elder", "Ancient"]},
    "resolution": {"model": "d20-vs-dc"},
}


@pytest.fixture
def years_world(dcc_world):
    cdir = Path(dcc_world) / "campaigns" / "dungeon-crawler-carl"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "ruleset.json").write_text(json.dumps(RULESET, indent=2), encoding="utf-8")
    (cdir / "character.json").write_text(json.dumps({
        "name": "Rhiannon", "level": 0, "years": 0,
        "hp": {"current": 30, "max": 30}, "stats": {"strength": 4},
    }, indent=2), encoding="utf-8")
    return dcc_world


def test_advancing_adds_to_the_declared_resource(years_world):
    out = PlayerManager(years_world).advance_resource("Rhiannon", 10)
    assert out["success"] is True
    assert out["resource"] == "years"
    assert out["before"] == 0
    assert out["after"] == 10


def test_advancing_persists(years_world):
    PlayerManager(years_world).advance_resource("Rhiannon", 10)
    assert PlayerManager(years_world).advance_resource("Rhiannon", 5)["after"] == 15


def test_crossing_a_tier_raises_the_level_and_names_it(years_world):
    m = PlayerManager(years_world)
    out = m.advance_resource("Rhiannon", 25)
    assert out["level_before"] == 0
    assert out["level_after"] == 2          # past 1 and 20
    assert out["tier"] == "Settled"
    assert out["tier_changed"] is True


def test_staying_inside_a_tier_does_not_change_level(years_world):
    m = PlayerManager(years_world)
    m.advance_resource("Rhiannon", 25)
    out = m.advance_resource("Rhiannon", 5)
    assert out["level_after"] == 2
    assert out["tier_changed"] is False


def test_fails_cleanly_when_there_is_no_character(years_world):
    """_load_character ignores the name and loads the active PC, so the only
    failure mode is having no character.json at all."""
    (Path(years_world) / "campaigns" / "dungeon-crawler-carl" / "character.json").unlink()
    assert PlayerManager(years_world).advance_resource(None, 1)["success"] is False


def _advance(world, *args):
    """Drive the real wrapper (not the manager directly) against a hermetic
    world-state tree. The wrapper is a literal `case "$ACTION"` dispatcher, not
    a "$@" pass-through — a missing arm falls to `*)`, prints the usage banner,
    and exits 0, silently no-opping. Only a subprocess call through the wrapper
    itself can catch that; calling PlayerManager directly cannot."""
    return subprocess.run(
        ["bash", str(ROOT / "tools" / "gm-player.sh"), "advance", *args],
        capture_output=True, text=True,
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world)},
    )


def test_wrapper_advance_dispatches_to_the_python_manager(years_world):
    """gm-player.sh had no "advance" arm: `bash tools/gm-player.sh advance
    --amount 10` reported success (exit 0) and changed nothing. Assert both the
    JSON envelope AND the on-disk effect, so a wrapper that merely echoes the
    usage banner (also exit 0) cannot pass this test."""
    r = _advance(years_world, "Rhiannon", "--amount", "10", "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)          # banner text is not valid JSON — fails pre-fix
    assert d["ok"] is True
    assert d["data"]["resource"] == "years"
    assert d["data"]["before"] == 0
    assert d["data"]["after"] == 10

    saved = json.loads(
        (Path(years_world) / "campaigns" / "dungeon-crawler-carl" / "character.json")
        .read_text(encoding="utf-8")
    )
    assert saved["years"] == 10


def test_wrapper_advance_human_mode(years_world):
    r = _advance(years_world, "Rhiannon", "--amount", "25")
    assert r.returncode == 0, r.stderr
    assert "years: 0 -> 25" in r.stdout
    assert "TIER CHANGE" in r.stdout


def test_wrapper_advance_is_discoverable_in_usage(years_world):
    """Added to the `*)` usage block so the new verb is discoverable."""
    r2 = subprocess.run(
        ["bash", str(ROOT / "tools" / "gm-player.sh"), "bogus-action"],
        capture_output=True, text=True,
        env={**os.environ, "GM_WORLD_STATE_BASE": str(years_world)},
    )
    assert "advance" in r2.stdout
