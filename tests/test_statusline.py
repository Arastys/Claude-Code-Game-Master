"""Tests for the always-on HUD.

`tools/gm-statusline.sh` had no coverage at all, which is how it stayed a
hardcoded 5e template through three plans that made every other character
surface kit-driven. It runs after every assistant message, so it is the most
visible renderer in the system and was the last one inventing placeholders.
"""

import json
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _run(world):
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / "gm-statusline.sh")],
        input="{}", capture_output=True, text=True,
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world)},
        cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    return ANSI.sub("", proc.stdout)


def _world(tmp_path, slug, ruleset, character, overview=None):
    world = tmp_path / "world-state"
    campaign = world / "campaigns" / slug
    campaign.mkdir(parents=True)
    (world / "active-campaign.txt").write_text(slug, encoding="utf-8")
    (campaign / "ruleset.json").write_text(json.dumps(ruleset), encoding="utf-8")
    (campaign / "character.json").write_text(json.dumps(character), encoding="utf-8")
    (campaign / "campaign-overview.json").write_text(
        json.dumps(overview or {"player_position": {"current_location": "Cwm Bychan"}}),
        encoding="utf-8")
    return world


CUSTOM = {
    "name": "custom",
    "stat_schema": {"attributes": ["might"], "vitals": ["hp", "blood"],
                    "traits": ["generation"]},
    "progression": {"model": "milestone"},
}
DND5E = {
    "name": "dnd5e",
    "stat_schema": {"attributes": ["str", "dex", "con", "int", "wis", "cha"],
                    "vitals": ["hp"]},
    "progression": {"model": "xp-levels"},
}


def test_the_hud_honours_gm_world_state_base(tmp_path):
    """Without this the HUD reads the developer's live campaign during tests."""
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Rhiannon", "level": 0,
                       "hp": {"current": 30, "max": 30}}))
    assert "Rhiannon" in out


def test_the_hud_invents_no_placeholders_on_a_custom_kit(tmp_path):
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Rhiannon", "level": 0,
                       "hp": {"current": 30, "max": 30}, "blood": 7,
                       "generation": 5}))
    assert "?" not in out
    assert "AC" not in out
    assert "gp" not in out
    assert "XP" not in out


def test_the_hud_shows_declared_vitals_and_traits(tmp_path):
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Rhiannon", "level": 0,
                       "hp": {"current": 30, "max": 30}, "blood": 7,
                       "generation": 5}))
    assert "Blood 7" in out
    assert "Generation 5" in out


def test_the_hud_keeps_the_5e_furniture_for_a_5e_sheet(tmp_path):
    out = _run(_world(tmp_path, "realms", DND5E,
                      {"name": "Bram", "level": 3, "race": "Dwarf",
                       "class": "Cleric", "ac": 16, "gold": 12,
                       "hp": {"current": 20, "max": 24},
                       "xp": {"current": 900, "next_level": 2700}}))
    assert "Dwarf" in out and "Cleric" in out
    assert "AC 16" in out
    assert "12gp" in out
    assert "900/2700" in out
    assert "20/24" in out


def test_the_hud_survives_a_scalar_hp_sheet(tmp_path):
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Nomad", "level": 1, "hp": 6}))
    assert "Nomad" in out
    assert "6" in out


def test_the_hud_still_reports_no_campaign_and_no_character(tmp_path):
    empty = tmp_path / "world-state"
    (empty / "campaigns").mkdir(parents=True)
    (empty / "active-campaign.txt").write_text("", encoding="utf-8")
    assert "no campaign yet" in _run(empty)

    world = tmp_path / "w2" / "world-state"
    (world / "campaigns" / "probe").mkdir(parents=True)
    (world / "active-campaign.txt").write_text("probe", encoding="utf-8")
    assert "no character yet" in _run(world)
