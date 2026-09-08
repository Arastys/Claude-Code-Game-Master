"""Character creation must not stamp D&D-shaped fields onto a non-5e sheet.

gold on a Bronze Age sheet is a lie (coinage postdates the setting by ~1400
years), and a 5e xp object on a milestone kit contradicts _xp_view's own
documented invariant that such a sheet "must not grow a phantom xp object".
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAVE = REPO_ROOT / "features" / "character-creation" / "save_character.py"

DND_RULESET = {"name": "D&D", "kit": "dnd5e",
               "stat_schema": {"attributes": ["str"], "vitals": ["hp"]},
               "progression": {"model": "xp-levels"}}
CUSTOM_RULESET = {"name": "The Slow Heart", "kit": "custom",
                  "stat_schema": {"attributes": ["strength"], "vitals": ["hp", "blood"]},
                  "progression": {"model": "milestone"}}

CUSTOM_PC = {"name": "Rhiannon", "level": 0, "stats": {"strength": 4},
             "hp": {"current": 30, "max": 30}}


def _campaign(world_dir):
    base = Path(world_dir)
    active = (base / "active-campaign.txt").read_text(encoding="utf-8").strip()
    return base / "campaigns" / active


def _run_save(world_dir, ruleset, character):
    cdir = _campaign(world_dir)
    (cdir / "ruleset.json").write_text(json.dumps(ruleset), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SAVE), json.dumps(character)],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "GM_WORLD_STATE_BASE": str(world_dir)},
        cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads((cdir / "character.json").read_text(encoding="utf-8"))


def test_custom_kit_sheet_has_no_invented_gold(dcc_world):
    assert "gold" not in _run_save(dcc_world, CUSTOM_RULESET, CUSTOM_PC)


def test_custom_kit_sheet_has_no_invented_xp(dcc_world):
    assert "xp" not in _run_save(dcc_world, CUSTOM_RULESET, CUSTOM_PC)


def test_custom_kit_sheet_has_no_invented_5e_prose_fields(dcc_world):
    sheet = _run_save(dcc_world, CUSTOM_RULESET, CUSTOM_PC)
    for field in ("background", "alignment", "bonds", "flaws", "ideals", "traits"):
        assert field not in sheet, f"{field} was invented on a non-5e sheet"


def test_custom_kit_keeps_fields_the_author_supplied(dcc_world):
    authored = dict(CUSTOM_PC, gold=12, background="last of her mother's line")
    sheet = _run_save(dcc_world, CUSTOM_RULESET, authored)
    assert sheet["gold"] == 12
    assert sheet["background"] == "last of her mother's line"


def test_custom_kit_keeps_falsy_author_supplied_fields(dcc_world):
    """The defect class here is membership-vs-truthiness: a "simplification" to
    character_data.get(field) (falling back to the default on ANY falsy value,
    not just a missing key) would pass the truthy-only test above while silently
    reintroducing the bug for an explicitly-authored gold=0 or background=""."""
    authored = dict(CUSTOM_PC, gold=0, background="")
    sheet = _run_save(dcc_world, CUSTOM_RULESET, authored)
    assert sheet["gold"] == 0
    assert sheet["background"] == ""


def test_dnd5e_sheet_is_unchanged(dcc_world):
    pc = {"name": "Thorin", "race": "Dwarf", "class": "Fighter", "level": 1,
          "stats": {"str": 15, "dex": 10, "con": 14, "int": 10, "wis": 10, "cha": 10}}
    sheet = _run_save(dcc_world, DND_RULESET, pc)
    assert sheet["gold"] == 0
    assert sheet["xp"] == {"current": 0, "next_level": 300}
    assert sheet["background"] == ""
