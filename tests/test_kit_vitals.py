"""Tests for character-save-kit-vitals: saving a PC and tracking vitals honors the
active World Kit instead of hardcoding D&D 5e.

Both fixture worlds are built in tmp_path, so nothing here reads or writes the
repo's world-state (the live active-campaign.txt is never touched).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib.player_manager import PlayerManager

ROOT = Path(__file__).resolve().parent.parent
SAVE_CHARACTER = ROOT / "features" / "character-creation" / "save_character.py"

HYBORIAN_RULESET = {
    "name": "The Hyborian Age",
    "kit": "hyborian",
    "stat_schema": {
        "attributes": ["might", "guile", "grit"],
        "vitals": ["hp", "vigor", "corruption"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
    "active_agents": [],
}

UNDERSCORE_RULESET = {
    "name": "The Underscore World",
    "kit": "custom",
    "stat_schema": {
        "attributes": [],
        "vitals": ["hp", "mana_pool"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
    "active_agents": [],
}

DND5E_RULESET = {
    "name": "Forgotten Realms",
    "kit": "dnd5e",
    "stat_schema": {
        "attributes": ["str", "dex", "con", "int", "wis", "cha"],
        "vitals": ["hp"],
    },
    "progression": {"model": "xp-levels"},
    "resolution": {"model": "d20-vs-dc"},
    "active_agents": [],
}

TRAIT_RULESET = {
    "name": "The Slow Heart",
    "kit": "custom",
    "stat_schema": {
        "attributes": ["strength", "dexterity", "stamina"],
        "vitals": ["hp", "blood"],
        "traits": ["generation", "gift_tier"],
    },
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
    "active_agents": [],
}

CONAN = {
    "name": "Conan",
    "race": "Cimmerian",
    "class": "Reaver",
    "level": 6,
    "attributes": {"might": 18, "guile": 13, "grit": 17},
    "hp": {"current": 58, "max": 58},
    "vigor": {"current": 5, "max": 5},
    "corruption": 0,
}


def _make_world(tmp_path, slug, ruleset):
    world = tmp_path / "world-state"
    campaign = world / "campaigns" / slug
    campaign.mkdir(parents=True)
    (world / "active-campaign.txt").write_text(slug, encoding="utf-8")
    (campaign / "ruleset.json").write_text(json.dumps(ruleset), encoding="utf-8")
    return world


@pytest.fixture
def hyborian_world(tmp_path):
    return _make_world(tmp_path, "hyborian", HYBORIAN_RULESET)


@pytest.fixture
def underscore_world(tmp_path):
    return _make_world(tmp_path, "underscore", UNDERSCORE_RULESET)


@pytest.fixture
def dnd_world(tmp_path):
    return _make_world(tmp_path, "forgotten-realms", DND5E_RULESET)


@pytest.fixture
def slow_heart_world(tmp_path):
    return _make_world(tmp_path, "slow-heart", TRAIT_RULESET)


def _save(world, payload):
    """Run save_character.py against `world` (it resolves world-state from cwd)."""
    return subprocess.run(
        [sys.executable, str(SAVE_CHARACTER), json.dumps(payload)],
        capture_output=True, text=True, cwd=str(world.parent), env={**os.environ},
    )


def _sheet(world):
    slug = (world / "active-campaign.txt").read_text(encoding="utf-8").strip()
    return json.loads((world / "campaigns" / slug / "character.json").read_text(encoding="utf-8"))


def test_attributes_is_the_stat_key(hyborian_world):
    r = _save(hyborian_world, CONAN)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _sheet(hyborian_world)["stats"] == CONAN["attributes"]


def test_stats_is_still_accepted_as_a_legacy_alias(hyborian_world):
    legacy = {k: v for k, v in CONAN.items() if k != "attributes"}
    legacy["stats"] = CONAN["attributes"]
    r = _save(hyborian_world, legacy)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _sheet(hyborian_world)["stats"] == CONAN["attributes"]


def test_authored_max_hp_is_preserved(hyborian_world):
    _save(hyborian_world, CONAN)
    hp = _sheet(hyborian_world)["hp"]
    assert hp["max"] == 58 and hp["current"] == 58


def test_no_5e_save_block_on_a_non_dnd5e_sheet(hyborian_world):
    _save(hyborian_world, CONAN)
    assert "saves" not in _sheet(hyborian_world)


def test_kit_vitals_persist(hyborian_world):
    _save(hyborian_world, CONAN)
    sheet = _sheet(hyborian_world)
    assert sheet["vigor"] == {"current": 5, "max": 5}
    assert sheet["corruption"] == 0


def test_kit_vitals_are_readable_and_modifiable(hyborian_world):
    _save(hyborian_world, CONAN)
    mgr = PlayerManager(str(hyborian_world))

    assert mgr.modify_vital(None, "vigor")["current"] == 5

    spent = mgr.modify_vital(None, "vigor", -2)
    assert spent["success"] and spent["current"] == 3 and spent["max"] == 5

    tainted = mgr.modify_vital(None, "corruption", +1)
    assert tainted["success"] and tainted["current"] == 1

    # Shape is preserved: the dict track stays a dict, the plain track stays plain.
    sheet = _sheet(hyborian_world)
    assert sheet["vigor"] == {"current": 3, "max": 5}
    assert sheet["corruption"] == 1

    assert mgr.modify_vital(None, "vigor", set_value=5)["current"] == 5


def test_vitals_appear_in_show_output(hyborian_world):
    _save(hyborian_world, CONAN)
    mgr = PlayerManager(str(hyborian_world))
    mgr.modify_vital(None, "vigor", -2)
    mgr.modify_vital(None, "corruption", +1)

    summary = mgr.show_player("Conan")
    assert "Vigor: 3/5" in summary and "Corruption: 1" in summary
    assert "Vigor: 3/5" in mgr.show_all_players()[0]


def test_show_output_and_character_brief_agree_on_an_underscore_named_vital(underscore_world):
    """Extra fix A: gm-player.sh show used vital.capitalize() ('Mana_pool'), the
    CHARACTER brief used vital.replace('_', ' ').title() ('Mana Pool') — two
    conventions for the same label. Both now go through the shared
    character_schema.stat_label helper and must agree."""
    r = _save(underscore_world, {
        "name": "Vex", "level": 1, "attributes": {},
        "hp": {"current": 10, "max": 10},
        "mana_pool": {"current": 4, "max": 6},
    })
    assert r.returncode == 0, r.stdout + r.stderr

    summary = PlayerManager(str(underscore_world)).show_player("Vex")
    assert "Mana Pool: 4/6" in summary
    assert "Mana_pool" not in summary

    from lib.session_manager import SessionManager
    ctx = SessionManager(str(underscore_world)).get_full_context()
    assert "Mana Pool: 4/6" in ctx


def test_undeclared_vital_is_refused(hyborian_world):
    _save(hyborian_world, CONAN)
    result = PlayerManager(str(hyborian_world)).modify_vital(None, "sanity", -1)
    assert result["success"] is False


def test_hp_keeps_its_dedicated_path(hyborian_world):
    """hp is a declared vital, but routes through modify_hp (dying gate + clamp)."""
    _save(hyborian_world, CONAN)
    mgr = PlayerManager(str(hyborian_world))
    result = mgr.modify_vital(None, "hp", -58)
    assert result["success"] and result["current_hp"] == 0
    assert _sheet(hyborian_world)["status"] == "dying"


def test_every_vital_response_has_the_same_shape(hyborian_world):
    """hp delegates to modify_hp but still answers with vital/current/max."""
    _save(hyborian_world, CONAN)
    mgr = PlayerManager(str(hyborian_world))

    hp = mgr.modify_vital(None, "hp", -8)
    vigor = mgr.modify_vital(None, "vigor", -2)
    read = mgr.modify_vital(None, "corruption")

    keys = {"success", "name", "vital", "current", "max"}
    assert keys <= hp.keys() and keys <= vigor.keys() and keys <= read.keys()
    assert hp["vital"] == "hp" and hp["current"] == 50 and hp["max"] == 58
    assert hp["previous"] == 58
    assert hp["current_hp"] == 50 and hp["max_hp"] == 58   # modify_hp's own keys kept


def test_dnd5e_still_derives_hp_and_saves(dnd_world):
    r = _save(dnd_world, {
        "name": "Thorin", "race": "Dwarf", "class": "Fighter", "level": 1,
        "stats": {"str": 16, "dex": 12, "con": 15, "int": 10, "wis": 13, "cha": 8},
    })
    assert r.returncode == 0, r.stdout + r.stderr
    sheet = _sheet(dnd_world)
    assert sheet["hp"] == {"current": 12, "max": 12}   # d10 hit die + CON +2
    assert sheet["saves"]["str"] == 5                  # +3 mod + proficiency
    assert sheet["saves"]["dex"] == 1


def test_dnd5e_authored_hp_is_preserved_verbatim(dnd_world):
    """Authoring beats deriving in every kit — a rolled sheet is not recomputed."""
    r = _save(dnd_world, {
        "name": "Thorin", "race": "Dwarf", "class": "Fighter", "level": 1,
        "stats": {"str": 16, "dex": 12, "con": 15, "int": 10, "wis": 13, "cha": 8},
        "hp": {"current": 7, "max": 14},
    })
    assert r.returncode == 0, r.stdout + r.stderr
    sheet = _sheet(dnd_world)
    assert sheet["hp"] == {"current": 7, "max": 14}     # not the formula's 12/12
    assert sheet["saves"]["str"] == 5                   # 5e derivation still runs


def test_non_dnd5e_missing_hp_warns_and_defaults_to_10(hyborian_world):
    """Unauthored HP on a non-dnd5e kit persists 10/10 and names the fallback."""
    payload = {k: v for k, v in CONAN.items() if k != "hp"}
    r = _save(hyborian_world, payload)
    assert r.returncode == 0, r.stdout + r.stderr
    result = json.loads(r.stdout)
    assert _sheet(hyborian_world)["hp"] == {"current": 10, "max": 10}
    warnings = result["warnings"]
    assert isinstance(warnings, list) and warnings
    assert any("10/10" in w for w in warnings)
    assert any("author" in w.lower() for w in warnings)


def test_declared_traits_persist_through_the_real_write_path(slow_heart_world):
    """FIX 1: a declared trait (generation, gift_tier) had no supported write
    path — save_character.py carried vitals but had no `kit.traits()` sibling,
    so an authored trait was silently dropped. This goes through the real
    save_character.py subprocess (not a hand-written character.json) to prove
    the write path itself, not just a hand-authored fixture."""
    r = _save(slow_heart_world, {
        "name": "Rhiannon", "level": 0,
        "attributes": {"strength": 2, "dexterity": 3, "stamina": 2},
        "hp": {"current": 30, "max": 30}, "blood": 7,
        "generation": 5, "gift_tier": 1,
    })
    assert r.returncode == 0, r.stdout + r.stderr
    sheet = _sheet(slow_heart_world)
    assert sheet["generation"] == 5
    assert sheet["gift_tier"] == 1
    assert sheet["blood"] == 7   # the sibling vitals loop still works alongside it


SCALAR_HP_RULESET = {
    "name": "The Flat Track",
    "kit": "custom",
    "stat_schema": {"attributes": [], "vitals": ["hp"]},
    "progression": {"model": "milestone"},
    "resolution": {"model": "d20-vs-dc"},
    "active_agents": [],
}


@pytest.fixture
def flat_track_world(tmp_path):
    return _make_world(tmp_path, "flat-track", SCALAR_HP_RULESET)


def test_show_player_survives_a_scalar_hp_sheet(flat_track_world):
    """FIX 5: show_player/show_all_players did `char.get('hp', {}).get('current')`,
    which raises AttributeError on a scalar hp track like {"name": "Nomad",
    "hp": 30} — exactly the shape the CHARACTER brief already handles via
    PlayerManager._read_vital.

    Written directly to character.json rather than through save_character.py:
    resolve_hp there always normalizes an authored scalar into a {current, max}
    dict, so it can never itself produce the bare shape this bug is about.
    """
    char_path = flat_track_world / "campaigns" / "flat-track" / "character.json"
    char_path.write_text(json.dumps({"name": "Nomad", "level": 2, "hp": 30}),
                          encoding="utf-8")

    mgr = PlayerManager(str(flat_track_world))
    summary = mgr.show_player("Nomad")
    assert summary is not None
    assert "HP: 30" in summary
    assert "HP: 30/None" not in summary and "HP: 30/0" not in summary

    all_summary = mgr.show_all_players()[0]
    assert "HP: 30" in all_summary


def test_undeclared_field_is_not_carried_as_a_trait(slow_heart_world):
    """Only traits the kit actually declares are carried — an arbitrary extra
    field on the payload is not a catch-all passthrough."""
    r = _save(slow_heart_world, {
        "name": "Rhiannon", "level": 0,
        "attributes": {"strength": 2, "dexterity": 3, "stamina": 2},
        "hp": {"current": 30, "max": 30},
        "favorite_color": "black",
    })
    assert r.returncode == 0, r.stdout + r.stderr
    assert "favorite_color" not in _sheet(slow_heart_world)
