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


VIGOR_ONLY = {
    "name": "vigor-only",
    "stat_schema": {"attributes": ["might"], "vitals": ["vigor"]},
    "progression": {"model": "milestone"},
}


def test_the_hud_invents_no_hp_track_for_a_kit_that_declares_none(tmp_path):
    """FIX 1: a kit whose declared vitals omit hp entirely (vitals: ["vigor"])
    must render no HP segment at all — the old code fell into HP_MAX=0 and
    rendered an empty red bar labelled Critical, permanently, on a world with
    no hit points."""
    out = _run(_world(tmp_path, "probe", VIGOR_ONLY,
                      {"name": "Ashen", "level": 1, "vigor": 4}))
    assert "HP" not in out
    assert "Critical" not in out


def test_the_hud_scalar_hp_at_full_health_is_not_critical(tmp_path):
    """FIX 1: a plain-number hp track has no max to compute a proportion from.
    The old code defaulted PCT to 0 in that case, so a character at full health
    on a scalar-hp kit rendered a bold red bar labelled Critical, permanently."""
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Nomad", "level": 1, "hp": 6}))
    assert "6" in out
    assert "Critical" not in out


def test_the_hud_survives_a_legacy_plain_int_xp(tmp_path):
    """FIX 2: `$ch.xp.current` on a plain-int xp is a jq type error (exit 5, no
    stdout), which left every field of the read empty — the whole HUD blanked
    to `⚔   Lv` after every assistant message on a normal, documented sheet
    shape (see player_manager.py's _xp_view)."""
    out = _run(_world(tmp_path, "realms", DND5E,
                      {"name": "Bram", "level": 3,
                       "hp": {"current": 20, "max": 24}, "xp": 900}))
    assert "Bram" in out


def test_the_hud_keeps_the_characters_location_when_the_overview_has_none(tmp_path):
    """FIX 3: the overview jq read still used the transport this branch
    documented as broken (IFS=$'\\t' with unstripped CRLF). With a date/time but
    no player_position.current_location, OLOC picked up a stray CR, which read
    as non-empty and clobbered the character's own location with garbage."""
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Rhiannon", "level": 0,
                       "hp": {"current": 30, "max": 30},
                       "current_location": "Cwm Bychan"},
                      overview={"current_date": "Day 3", "time_of_day": "Dusk"}))
    lines = out.splitlines()
    line1 = next(l for l in lines if "Rhiannon" in l)
    assert "Cwm Bychan" in line1
    assert not line1.rstrip().endswith("·")


RACE_TRAIT_KIT = {
    "name": "race-trait",
    "stat_schema": {"attributes": ["might"], "vitals": ["hp"], "traits": ["race"]},
    "progression": {"model": "milestone"},
}


def test_the_hud_does_not_double_print_a_trait_that_collides_with_identity(tmp_path):
    """FIX 4: `race` is already folded into the identity segment (Lv1 Cimmerian);
    a kit declaring it again as a trait must not print the value twice."""
    out = _run(_world(tmp_path, "probe", RACE_TRAIT_KIT,
                      {"name": "Conan", "level": 1, "race": "Cimmerian",
                       "hp": {"current": 5, "max": 5}}))
    assert out.count("Cimmerian") == 1


def test_the_hud_still_reports_no_campaign_and_no_character(tmp_path):
    empty = tmp_path / "world-state"
    (empty / "campaigns").mkdir(parents=True)
    (empty / "active-campaign.txt").write_text("", encoding="utf-8")
    assert "no campaign yet" in _run(empty)

    world = tmp_path / "w2" / "world-state"
    (world / "campaigns" / "probe").mkdir(parents=True)
    (world / "active-campaign.txt").write_text("probe", encoding="utf-8")
    assert "no character yet" in _run(world)


def test_a_scalar_hp_track_draws_no_bar(tmp_path):
    """An empty ten-cell bar beside a healthy character reads as an empty tank.

    Drawing a bar asserts a proportion, and a plain-number track has no maximum
    to draw one against — the same class of assertion that made a full-health
    character render as Critical before the bar/state split was fixed.
    """
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Nomad", "level": 1, "hp": 6}))
    assert "HP 6" in out
    assert "░" not in out
    assert "█" not in out


def test_a_dict_hp_track_still_draws_its_bar(tmp_path):
    out = _run(_world(tmp_path, "probe", CUSTOM,
                      {"name": "Bram", "level": 1, "hp": {"current": 10, "max": 30}}))
    assert "10/30" in out
    assert "█" in out and "░" in out
