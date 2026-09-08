# Kit Execution Gaps & Build Bugs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the kit's declared mechanics actually runnable from the tool layer, and stop the tool layer crashing on non-ASCII output.

**Architecture:** Two new tool-layer entry points over machinery that already exists and is already correct — `lib/kit_systems.py` dispatches a declared `ruleset.json` system to its `game_core` primitive, and a new `PlayerManager.advance_resource` routes through the untouched `WorldKit.advance_progression`. Plus two defensive fixes: forcing UTF-8 on Python stdio, and deriving a short location key when `play_pack.room` holds prose.

**Tech Stack:** Python 3.11+, pytest (in the `dev` extra), bash wrappers.

**Spec:** `docs/superpowers/specs/2026-09-08-kit-execution-gaps.md`
**Campaign context:** `docs/superpowers/specs/2026-09-08-the-slow-heart-design.md`

## Global Constraints

- Python is invoked as `uv run python` — never bare `python` or `python3`.
- Tests run with `uv run --extra dev pytest` — plain `uv run pytest` fails with `Failed to spawn: pytest`.
- Managers subclass `EntityManager` and persist through `self.json_ops`.
- CLIs use `cli_output.wants_json()` / `strip_json_flag()` / `emit()` / `emit_error()`. Nothing prints to stdout on a `--json` path except the JSON envelope.
- Bash wrappers source `common.sh`, call `require_active_campaign`, and delegate `"$@"`.
- Tests import from the package path and take the `dcc_world` fixture (a **string path** to a writable fixture copy).
- `game_core` primitives are pure functions and stay that way — no I/O, no persistence.

---

## File Structure

**Created:**
- `lib/kit_systems.py` — resolve a declared system by name and dispatch it to its `game_core` primitive.
- `tools/gm-system.sh` — thin wrapper.
- `tests/test_kit_systems.py` — dispatch, arg validation, CLI envelope.
- `tests/test_resource_axis_progression.py` — resource advancement and tier changes.
- `tests/test_stage_location_name.py` — short-name derivation.

**Modified:**
- `tools/common.sh` — export `PYTHONIOENCODING=utf-8` (**already applied, uncommitted**).
- `lib/player_manager.py` — add `advance_resource` + an `advance` subcommand.
- `lib/play_pack.py` — add `_short_name`, use it in `apply_stage`.
- `docs/modules/game-core-and-world-kit.md` — document both new commands.

---

### Task 1: Lock in the UTF-8 fix

**Files:**
- Modify: `tools/common.sh` (change already present in the working tree — verify, do not re-apply)
- Test: `tests/test_hooks.py` is unrelated; create `tests/test_tool_layer_encoding.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a guarantee that wrapper subprocesses run with UTF-8 stdio.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tool_layer_encoding.py`:

```python
"""The tool layer must survive non-ASCII output on any platform.

Windows consoles default to cp1252. Campaign content is full of em-dashes and
non-ASCII names, and `gm-session.sh context` died with a UnicodeEncodeError
before printing a single line.
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMON_SH = REPO_ROOT / "tools" / "common.sh"


def test_common_sh_forces_utf8_stdio():
    assert "PYTHONIOENCODING=utf-8" in COMMON_SH.read_text(encoding="utf-8")


def test_a_wrapper_can_print_non_ascii_under_a_legacy_codepage(isolated_world_state):
    """Simulate the cp1252 console that broke this."""
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    script = (
        'source "$(dirname "$0")/common.sh"\n'
        '$PYTHON_CMD -c "print(\'Käthe — Y Bedd\')"\n'
    )
    runner = REPO_ROOT / "tools" / "_zz_encoding_probe.sh"
    runner.write_text(script, encoding="utf-8")
    try:
        proc = subprocess.run(["bash", str(runner)], capture_output=True,
                              text=True, encoding="utf-8", env=env,
                              cwd=str(REPO_ROOT))
    finally:
        runner.unlink()
    assert proc.returncode == 0, proc.stderr
    assert "Käthe" in proc.stdout
```

The probe sets `PYTHONIOENCODING=cp1252` in the parent environment; `common.sh` must
override it. If the export is missing or placed after `PYTHON_CMD` is used, this fails.

- [ ] **Step 2: Run the tests**

Run: `uv run --extra dev pytest tests/test_tool_layer_encoding.py -v`
Expected: PASS — the `common.sh` change is already in the working tree. If it fails,
the export is missing or ordered wrong; add it immediately after `PYTHON_CMD=$(find_python)`.

- [ ] **Step 3: Commit**

```bash
git add tools/common.sh tests/test_tool_layer_encoding.py
git commit -m "$(cat <<'EOF'
tool-layer: force UTF-8 stdio so wrappers survive a cp1252 console

gm-session.sh context died with UnicodeEncodeError before printing a line on
Windows, which blocked play entirely.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 2: Execute declared signature systems

**Files:**
- Create: `lib/kit_systems.py`, `tools/gm-system.sh`
- Test: `tests/test_kit_systems.py`

**Interfaces:**
- Consumes: `WorldKit.systems()` (`world_kit.py:173`); `game_core.named_track` / `price_roll` / `reaction_roll` / `guarded_payoff`.
- Produces:
  - `KitSystems(world_state_dir: str = None)`
  - `list_systems() -> list[dict]`
  - `find(name: str) -> dict | None` (case-insensitive, exact match on `name`)
  - `roll(name: str, *, current=None, delta=None, severity=None, track_value=None, modifier=None, rng=None) -> dict` returning `{"system", "primitive", **primitive_result}`
  - Raises `KeyError` for an unknown system, `ValueError` for a missing required argument.

- [ ] **Step 1: Write the failing test**

Create `tests/test_kit_systems.py`:

```python
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
    assert out["cost"] in {"clean", "haunted", "overwritten"}
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
    assert out["reaction"] in {"warm", "cold"}


def test_guarded_payoff_needs_no_arguments(kit_world):
    out = KitSystems(kit_world).roll("Opening a barrow", rng=random.Random(5))
    assert out["outcome"] in {"clean", "guardian_wakes", "curse_attaches"}


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_kit_systems.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.kit_systems'`

- [ ] **Step 3: Write the implementation**

Create `lib/kit_systems.py`:

```python
#!/usr/bin/env python3
"""
Roll the kit's declared signature systems.

ruleset.json `systems` entries are instantiations of a game_core primitive, and
scene context tells the GM every beat to ROLL them rather than narrate them. There
was no way to do that: game_core is a pure library with no CLI, and no wrapper
invoked it. This resolves a system by name and dispatches it to its primitive with
the stored config.

The primitives stay pure — this module supplies the per-attempt arguments the
config cannot know (a track's current value, an attempt's severity, a reputation
score) and returns the primitive's own result untouched.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from world_kit import WorldKit
from game_core import named_track, price_roll, reaction_roll, guarded_payoff


class KitSystems:
    """Resolve and execute the active kit's declared signature systems."""

    def __init__(self, world_state_dir: str = None):
        self.kit = WorldKit(world_state_dir)

    def list_systems(self) -> List[Dict[str, Any]]:
        return self.kit.systems()

    def find(self, name: str) -> Optional[Dict[str, Any]]:
        needle = (name or "").strip().lower()
        for system in self.list_systems():
            if str(system.get("name", "")).strip().lower() == needle:
                return system
        return None

    def roll(self, name: str, *, current: int = None, delta: int = None,
             severity: int = None, track_value: int = None,
             modifier: int = None, rng: Any = None) -> Dict[str, Any]:
        system = self.find(name)
        if system is None:
            raise KeyError(f"no declared system named {name!r}")
        primitive = system.get("primitive")
        config = dict(system.get("config") or {})
        if modifier is not None:
            config["modifier"] = int(modifier)

        if primitive == "named_track":
            if current is None or delta is None:
                raise ValueError("named_track needs --current and --delta")
            result = named_track(int(current), int(delta), config)
        elif primitive == "price_roll":
            if severity is None:
                raise ValueError("price_roll needs --severity")
            result = price_roll(int(severity), config, rng=rng)
        elif primitive == "reaction_roll":
            if track_value is None:
                raise ValueError("reaction_roll needs --track-value")
            result = reaction_roll(int(track_value), config, rng=rng)
        elif primitive == "guarded_payoff":
            result = guarded_payoff(config, rng=rng)
        else:
            raise ValueError(f"unknown primitive {primitive!r} on system {name!r}")

        return {"system": system.get("name"), "primitive": primitive, **result}


def main():
    import argparse
    import json
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    parser = argparse.ArgumentParser(description="Roll the kit's signature systems")
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("list")
    p = sub.add_parser("roll")
    p.add_argument("name")
    p.add_argument("--current", type=int)
    p.add_argument("--delta", type=int)
    p.add_argument("--severity", type=int)
    p.add_argument("--track-value", dest="track_value", type=int)
    p.add_argument("--modifier", type=int, help="per-attempt bonus; overrides config")

    json_mode = wants_json()
    args = parser.parse_args(strip_json_flag(sys.argv[1:]))
    if not args.action:
        parser.print_help(); sys.exit(1)

    ks = KitSystems()
    if args.action == "list":
        out = ks.list_systems()
    else:
        try:
            out = ks.roll(args.name, current=args.current, delta=args.delta,
                          severity=args.severity, track_value=args.track_value,
                          modifier=args.modifier)
        except (KeyError, ValueError) as exc:
            sys.exit(emit_error(str(exc).strip("'"), json_mode))

    if json_mode:
        emit(out, json_mode=True)
    else:
        print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

Create `tools/gm-system.sh`:

```bash
#!/bin/bash
# gm-system.sh - Roll the kit's declared signature systems (wrapper for kit_systems.py)
#
#   gm-system.sh list                                  Show declared systems
#   gm-system.sh roll "<name>" [args]                  Execute one
#
#     named_track     --current N --delta N
#     price_roll      --severity N [--modifier N]
#     reaction_roll   --track-value N [--modifier N]
#     guarded_payoff  (no arguments)
#
# --modifier is a PER-ATTEMPT bonus and overrides the stored config value.
# All commands accept --json.

source "$(dirname "$0")/common.sh"

require_active_campaign

$PYTHON_CMD "$LIB_DIR/kit_systems.py" "$@"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_kit_systems.py -v`
Expected: PASS — 12 passed

- [ ] **Step 5: Commit**

```bash
git add lib/kit_systems.py tools/gm-system.sh tests/test_kit_systems.py
git commit -m "$(cat <<'EOF'
kit-systems: make declared signature systems rollable from the tool layer

Scene context has been telling the GM to ROLL these every beat with no command
that could. --modifier carries the per-attempt bonus (practice, gear, standing).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 3: Advance a resource-axis progression

**Files:**
- Modify: `lib/player_manager.py` (add `advance_resource`, add the `advance` subcommand and its dispatch branch)
- Test: `tests/test_resource_axis_progression.py`

**Interfaces:**
- Consumes: `WorldKit.advance_progression(state, **kw)` (`world_kit.py:200`), `WorldKit.level_for(state)` (`:203`), `PlayerManager._load_character` / `_save_character`.
- Produces: `PlayerManager.advance_resource(name: str | None, amount: int) -> dict` returning `{"success", "resource", "before", "after", "level_before", "level_after", "tier", "tier_changed"}`.

`tier` is the name from `ruleset.json` `progression.tier_names[level]` when declared,
otherwise `None`. Level is the count of tiers reached, so it indexes `tier_names`
directly.

- [ ] **Step 1: Write the failing test**

Create `tests/test_resource_axis_progression.py`:

```python
"""resource-axis campaigns must be able to advance.

WorldKit.advance_progression and level_for were correct and unreachable — award_xp
is hardcoded to the xp-levels threshold path, so a kit declaring
{"model": "resource-axis", "resource": "years"} could not gain a single year.
"""

import json
from pathlib import Path

import pytest

from lib.player_manager import PlayerManager

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_resource_axis_progression.py -v`
Expected: FAIL — `AttributeError: 'PlayerManager' object has no attribute 'advance_resource'`

- [ ] **Step 3: Write the implementation**

Add to `PlayerManager` in `lib/player_manager.py`, next to `award_xp`:

```python
    def advance_resource(self, name: str, amount: int) -> Dict[str, Any]:
        """Advance a resource-axis progression (years, viewers, spice...).

        award_xp walks the xp-levels threshold table and cannot serve a kit whose
        progression is an accumulating world resource. WorldKit already computes
        both halves — this persists them. Level is the count of tiers reached, so
        it indexes progression.tier_names directly.
        """
        char = self._load_character(name)
        if not char:
            print(f"[ERROR] Character '{name}' not found")
            return {'success': False}

        kit = self.world_kit()
        resource = getattr(kit.progression, 'resource', None)
        if not resource:
            return {'success': False,
                    'error': f"kit progression '{kit.progression.name}' has no resource axis"}

        before = int(char.get(resource, 0))
        level_before = kit.level_for(char)
        char[resource] = int(kit.advance_progression(char, amount=int(amount))[resource])
        level_after = kit.level_for(char)
        char['level'] = level_after
        self._save_character(char.get('name', name), char)

        tier_names = ((kit.ruleset.get('progression') or {}).get('tier_names')) or []
        tier = tier_names[level_after] if level_after < len(tier_names) else None
        return {'success': True, 'resource': resource,
                'before': before, 'after': int(char[resource]),
                'level_before': level_before, 'level_after': level_after,
                'tier': tier, 'tier_changed': level_after != level_before}
```

Add the subparser next to the `xp` parser in `main()`:

```python
    # Advance a resource-axis progression (years, viewers, spice, ...)
    advance_parser = subparsers.add_parser(
        'advance', help="Advance the kit's progression resource (resource-axis kits)")
    advance_parser.add_argument('name', nargs='?', help='Character name (defaults to active PC)')
    advance_parser.add_argument('--amount', type=int, required=True,
                                help='How much of the resource to add (e.g. 10 years)')
```

And the dispatch branch alongside the other actions:

```python
    elif args.action == 'advance':
        result = manager.advance_resource(args.name, args.amount)
        if not result.get('success'):
            sys.exit(1)
        if json_mode:
            emit(result, json_mode=True)
        else:
            print(f"{result['resource']}: {result['before']} -> {result['after']}")
            if result['tier_changed']:
                print(f"TIER CHANGE -> {result['tier'] or result['level_after']}")
```

Pass `args.name` straight through, exactly as the `award` branch does
(`player_manager.py:1242`). `_load_character` **ignores the name and always loads the
active PC from `character.json`** (`:68`), so `nargs='?'` needs no resolution logic
here — a `None` name is normal, not an error.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_resource_axis_progression.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add lib/player_manager.py tests/test_resource_axis_progression.py
git commit -m "$(cat <<'EOF'
progression: give resource-axis kits a tool path to advance

WorldKit.advance_progression/level_for were correct and unreachable; award_xp is
hardcoded to xp-levels. A years-based kit could not gain a single year.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 4: Derive a short location name when `room` is prose

**Files:**
- Modify: `lib/play_pack.py` (add `_short_name`; use it at the two sites in `apply_stage`)
- Test: `tests/test_stage_location_name.py`
- Modify: `docs/modules/game-core-and-world-kit.md`

**Interfaces:**
- Consumes: `apply_stage` (`play_pack.py:261`).
- Produces: `_short_name(room: str, limit: int = 48) -> str` — module-private.

`apply_stage` currently uses `pack["room"]` verbatim as a location key
(`:272`) and as every present NPC's location tag (`:289`). `npcs_present` matches by
exact equality, so a prose room makes staged NPCs unreachable. Keep the full prose as
the location **description**; use the short name as the **key** and the tag.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stage_location_name.py`:

```python
"""A prose `room` must not poison the journal.

apply_stage used play_pack.room verbatim as a location key and as every present
NPC's location tag. npcs_present matches location by exact equality, so staged
NPCs became unreachable from any name a person would type.
"""

import json
from pathlib import Path

import pytest

from lib.play_pack import apply_stage, _short_name

PROSE = ("Y Bedd — the offering stone on the shoulder above Cwm Bedd, at dusk. "
         "Turned earth where you came up.")


@pytest.mark.parametrize("room,expected", [
    (PROSE, "Y Bedd"),
    ("The Rusty Anchor", "The Rusty Anchor"),
    ("Barovia, the village", "Barovia"),
    ("Deck 12.", "Deck 12"),
    ("   ", "the stage"),
])
def test_short_name_derivation(room, expected):
    assert _short_name(room) == expected


def test_stage_keys_the_location_by_the_short_name(dcc_world):
    cdir = Path(dcc_world) / "campaigns" / "dungeon-crawler-carl"
    overview = json.loads((cdir / "campaign-overview.json").read_text(encoding="utf-8"))
    overview["play_pack"] = {
        "whose_story": "Eurgain", "room": PROSE, "present": ["Nest"],
        "exits": [], "hook": "the cup", "offstage": [], "primer": "start here",
    }
    (cdir / "campaign-overview.json").write_text(json.dumps(overview, indent=2),
                                                 encoding="utf-8")
    apply_stage(cdir)

    locations = json.loads((cdir / "locations.json").read_text(encoding="utf-8"))
    assert "Y Bedd" in locations
    assert PROSE not in locations
    assert PROSE in locations["Y Bedd"]["description"]

    npcs = json.loads((cdir / "npcs.json").read_text(encoding="utf-8"))
    assert npcs["Nest"]["tags"]["locations"] == ["Y Bedd"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_stage_location_name.py -v`
Expected: FAIL — `ImportError: cannot import name '_short_name'`

- [ ] **Step 3: Write the implementation**

`lib/play_pack.py` does **not** import `re` — add `import re` to its import block
(after `import json` at line 10), then add near the top of the module:

```python
def _short_name(room: str, limit: int = 48) -> str:
    """A matchable location key from a `room` that may have been written as prose.

    play_pack.room is specified as "one street / room / deck", but it invites
    description, and apply_stage used it verbatim as a location key AND as every
    present NPC's location tag. npcs_present matches by exact equality, so a
    paragraph made the whole staged cast unreachable. Splitting on the first
    dash/comma/sentence break recovers the name a person would actually type,
    and a short well-formed room passes through untouched.
    """
    head = re.split(r"\s+[—–-]\s+|[.,:;]", (room or "").strip(), maxsplit=1)[0].strip()
    if not head:
        head = (room or "").strip()[:limit].rstrip()
    return head[:limit].rstrip() or "the stage"
```

In `apply_stage`, immediately after the empty-room guard, add:

```python
    room_key = _short_name(pack["room"])
```

Then replace `pack["room"]` with `room_key` at these sites, keeping the full prose as
the description:

- `created = {"location": room_key, ...}`
- the `_ensure_location(...)` call: pass `room_key` as the name, and make the
  description `pack["primer"] or pack["hook"]` prefixed with the full `pack["room"]`
  text so nothing is lost — `f'{pack["room"]}\n\n{pack["primer"] or pack["hook"]}'`
- `_ensure_location(locations, exit_name, f"exit from {room_key}")`
- `_connect(locations, room_key, exit_name, "visible from here")`
- the NPC tag: `"tags": {"locations": [room_key], "quests": []}`
- `_merge_npc(..., add_location=room_key)`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_stage_location_name.py -v`
Expected: PASS — 7 passed

Then confirm nothing regressed:

Run: `uv run --extra dev pytest`
Expected: no new failures against the pre-change baseline

- [ ] **Step 5: Update the docs and commit**

In `docs/modules/game-core-and-world-kit.md`, add:

```markdown
## Rolling the declared systems

`bash tools/gm-system.sh list` shows the kit's declared signature systems;
`bash tools/gm-system.sh roll "<name>" [args]` executes one through its `game_core`
primitive using the config stored in `ruleset.json`.

| Primitive | Arguments |
|---|---|
| `named_track` | `--current N --delta N` |
| `price_roll` | `--severity N [--modifier N]` |
| `reaction_roll` | `--track-value N [--modifier N]` |
| `guarded_payoff` | none |

`--modifier` is a **per-attempt** bonus (practice, gear, standing) and overrides the
stored config value. The primitives stay pure; this supplies only the arguments a
static config cannot know.

## Advancing a resource-axis kit

`bash tools/gm-player.sh advance --amount N` adds to the kit's declared progression
resource and reports any tier change, naming it from `progression.tier_names` when
declared. `gm-player.sh xp` remains the xp-levels path.
```

```bash
git add lib/play_pack.py tests/test_stage_location_name.py docs/modules/game-core-and-world-kit.md
git commit -m "$(cat <<'EOF'
play-pack: derive a matchable location key when room is written as prose

A paragraph in play_pack.room became a location key and every staged NPC's
location tag, and npcs_present matches by exact equality — so the whole opening
cast dropped out of scene context on the first move.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

## Notes for the executor

- **Baseline the suite first.** Run `uv run --extra dev pytest` before Task 1 and keep
  the result — `docs/log.md` records a pre-existing failure, so the bar is "no *new*
  failures".
- **Line numbers drift** as tasks land. Anchor on function names, not line numbers.
- **`the-slow-heart` already has hand-repaired data** — its `locations.json` was
  rebuilt with short keys and its NPCs retagged to `"Y Bedd"`. Task 4 fixes the cause;
  it does not need to migrate that campaign.
- **Task 2 unlocks the-slow-heart's central mechanic.** Diablerie is a `price_roll`
  with `severity` = generation gap doubled and `modifier` = the diablerist's practice.
  Until `gm-system.sh` exists it cannot be resolved.
- **`gm-npc.sh set-inner --mood` is NOT broken** — an earlier note claimed otherwise.
  It passes `current_mood=args.mood` correctly and a clean test confirms it persists.
  No task needed.
