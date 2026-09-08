"""Declared signature systems must be rollable from the tool layer.

Scene context tells the GM to ROLL these every beat. Before this module the only
way to do that was to hand-write Python.
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from lib.kit_systems import KitSystems

REPO_ROOT = Path(__file__).resolve().parent.parent

SYSTEMS = [
    {"primitive": "named_track", "name": "Y Syched",
     "config": {"max": 10, "thresholds": [{"at": 3, "consequence": "the Thirst rises"}]}},
    {"primitive": "price_roll", "name": "Diablerie",
     "config": {"dice": "1d20", "modifier": 0,
                "ladder": [{"min_roll": 16, "cost": "clean"},
                           {"min_roll": 10, "cost": "haunted"},
                           {"min_roll": -99, "cost": "overwritten"}]}},
    {"primitive": "reaction_roll", "name": "The Aberth",
     "config": {"dice": "2d6", "tiers": [{"min": 10, "reaction": "warm"},
                                         {"min": 2, "reaction": "cold"}]}},
    {"primitive": "guarded_payoff", "name": "Opening a barrow",
     "config": {"dice": "1d20", "clean_at": 15, "guardian_at": 6}},
]


@pytest.fixture
def kit_world(dcc_world):
    path = Path(dcc_world) / "campaigns" / "dungeon-crawler-carl" / "ruleset.json"
    ruleset = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    ruleset["systems"] = SYSTEMS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ruleset, indent=2), encoding="utf-8")
    return dcc_world


def test_list_returns_declared_systems(kit_world):
    names = [s["name"] for s in KitSystems(kit_world).list_systems()]
    assert names == ["Y Syched", "Diablerie", "The Aberth", "Opening a barrow"]


def test_find_is_case_insensitive(kit_world):
    assert KitSystems(kit_world).find("y syched")["primitive"] == "named_track"


def test_unknown_system_raises(kit_world):
    with pytest.raises(KeyError):
        KitSystems(kit_world).roll("Nothing At All", current=0, delta=1)


def test_named_track_applies_delta_and_reports_crossings(kit_world):
    out = KitSystems(kit_world).roll("Y Syched", current=1, delta=3)
    assert out["primitive"] == "named_track"
    assert out["after"] == 4
    assert [t["at"] for t in out["crossed"]] == [3]


def test_named_track_requires_current_and_delta(kit_world):
    with pytest.raises(ValueError):
        KitSystems(kit_world).roll("Y Syched", delta=1)


def test_price_roll_uses_severity_and_reads_the_ladder(kit_world):
    out = KitSystems(kit_world).roll("Diablerie", severity=0, rng=random.Random(1))
    assert out["primitive"] == "price_roll"
    assert out["cost"] == "overwritten"  # Random(1) rolls 5 on 1d20; total 5 < 10
    assert out["severity"] == 0


def test_price_roll_modifier_overrides_config(kit_world):
    """Practice is a per-attempt bonus, not a property of the system."""
    plain = KitSystems(kit_world).roll("Diablerie", severity=10, rng=random.Random(7))
    skilled = KitSystems(kit_world).roll("Diablerie", severity=10, modifier=8,
                                         rng=random.Random(7))
    assert skilled["total"] == plain["total"] + 8


def test_price_roll_requires_severity(kit_world):
    with pytest.raises(ValueError):
        KitSystems(kit_world).roll("Diablerie")


def test_reaction_roll_uses_track_value(kit_world):
    out = KitSystems(kit_world).roll("The Aberth", track_value=5, rng=random.Random(3))
    assert out["primitive"] == "reaction_roll"
    assert out["track_value"] == 5
    assert out["reaction"] == "warm"  # Random(3) rolls 7 on 2d6; total 7+5=12 >= 10


def test_guarded_payoff_needs_no_arguments(kit_world):
    out = KitSystems(kit_world).roll("Opening a barrow", rng=random.Random(5))
    assert out["outcome"] == "clean"  # Random(5) rolls 20 on 1d20; 20 >= clean_at 15


def test_cli_roll_emits_a_json_envelope(kit_world):
    env = dict(os.environ, GM_WORLD_STATE_BASE=str(kit_world))
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "lib" / "kit_systems.py"),
         "roll", "Y Syched", "--current", "0", "--delta", "3", "--json"],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["data"]["after"] == 3


def test_cli_unknown_system_exits_nonzero(kit_world):
    env = dict(os.environ, GM_WORLD_STATE_BASE=str(kit_world))
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "lib" / "kit_systems.py"),
         "roll", "Nope", "--json"],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(REPO_ROOT))
    assert proc.returncode != 0
