# World Tracks & Factions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two pieces of persisted world state the engine lacks — bidirectional world-level meters, and faction/territory/affiliation records — both surfaced in scene context.

**Architecture:** Two new managers following the existing `EntityManager` pattern (`lib/<x>_manager.py` → `tools/gm-<x>.sh` → per-campaign JSON), modelled closely on `lib/threat_clocks.py`. `WorldTrackManager` delegates all arithmetic to `game_core.named_track` so a stored track behaves identically to the kit primitive a ruleset declares. `FactionManager` stores plain records whose `standing` field is directly consumable as `game_core.reaction_roll`'s `track_value`. Both render into `get_full_context` next to THREAT CLOCKS.

**Tech Stack:** Python 3.11+, pytest (in the `dev` extra), bash wrappers, per-campaign JSON via `lib/json_ops.py`.

**Spec:** `docs/superpowers/specs/2026-09-08-world-tracks-and-factions.md`
**Campaign context:** `docs/superpowers/specs/2026-09-08-the-slow-heart-design.md`

## Global Constraints

- Python is invoked as `uv run python` — never bare `python` or `python3`.
- Tests run with `uv run --extra dev pytest` — pytest is in the `dev` extra, and plain `uv run pytest` fails with `Failed to spawn: pytest`.
- Managers subclass `EntityManager` (`lib/entity_manager.py`) and persist through `self.json_ops.load_json(filename)` / `self.json_ops.save_json(filename, data)`.
- CLIs use `cli_output.wants_json()`, `strip_json_flag()`, `emit()`. Nothing may print to stdout on a `--json` path except the JSON envelope.
- Bash wrappers are thin: `source "$(dirname "$0")/common.sh"`, then `require_active_campaign`, then delegate `"$@"` to the module. Always invoked as `bash tools/gm-*.sh`.
- Tests import from the package path (`from lib.world_tracks import WorldTrackManager`) and take the `dcc_world` fixture, which is a writable copy of `tests/fixtures/world-state` returned as a **string path** passed to the manager constructor.
- Standing is clamped to `[-5, +5]`. Track values are clamped to `[0, max]` by `named_track`.
- Name matching for members and territory is case-insensitive on read, and preserves stored casing.

---

## File Structure

**Created:**
- `lib/world_tracks.py` — `WorldTrackManager`: persisted world-level meters over `game_core.named_track`. Owns `world-tracks.json`.
- `tools/gm-track.sh` — thin wrapper.
- `tests/test_world_tracks.py` — track arithmetic, threshold firing, CLI stdout hygiene.
- `lib/faction_manager.py` — `FactionManager`: standing, members, territory, relations. Owns `factions.json`.
- `tools/gm-faction.sh` — thin wrapper.
- `tests/test_faction_manager.py` — standing clamping, membership, territory, contested ground.
- `tests/test_world_state_context.py` — both sections render into `get_full_context`.

**Modified:**
- `lib/session_manager.py:847-856` — add WORLD TRACKS and FACTIONS sections after the THREAT CLOCKS block.
- `docs/modules/living-world.md` — document both subsystems.
- `docs/schema-reference.md` — document `world-tracks.json` and `factions.json`.

---

### Task 1: WorldTrackManager core

**Files:**
- Create: `lib/world_tracks.py`
- Test: `tests/test_world_tracks.py`

**Interfaces:**
- Consumes: `EntityManager` (`lib/entity_manager.py`), `game_core.named_track` (`lib/game_core.py:365`).
- Produces:
  - `WorldTrackManager(world_state_dir: str = None)` with attribute `tracks_file = "world-tracks.json"`
  - `add_track(name: str, max_value: int, thresholds: list = None, note: str = None, current: int = 0) -> dict`
  - `adjust(name: str, delta: int) -> dict | None` returning `{"name", "before", "after", "max", "crossed", "at_max"}`
  - `set_value(name: str, value: int) -> dict | None` (same return shape)
  - `remove_track(name: str) -> bool`
  - `get_tracks() -> dict`
  - `render(tracks: dict) -> str` (staticmethod)

- [ ] **Step 1: Write the failing test**

Create `tests/test_world_tracks.py`:

```python
"""Tests for world tracks.

A threat clock only fills. A world track moves both ways and reports the
thresholds it crosses in either direction, because the world forgetting
something is as much a beat as the world learning it.
"""

from lib.world_tracks import WorldTrackManager

THRESHOLDS = [
    {"at": 3, "consequence": "A rumour with the right shape is circulating."},
    {"at": 5, "consequence": "The valley knows how to finish one of the Old Dead."},
]


def test_add_track_stores_shape_and_starts_empty(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS, note="What the world remembers.")
    stored = m.get_tracks()["Y Cof"]
    assert stored["current"] == 0
    assert stored["max"] == 6
    assert stored["thresholds"] == THRESHOLDS
    assert stored["note"] == "What the world remembers."


def test_adjust_clamps_to_zero_and_max(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6)
    assert m.adjust("Y Cof", 99)["after"] == 6
    assert m.adjust("Y Cof", -99)["after"] == 0


def test_adjust_reports_thresholds_crossed_climbing(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    result = m.adjust("Y Cof", 5)
    assert [t["at"] for t in result["crossed"]] == [3, 5]
    assert result["before"] == 0
    assert result["after"] == 5


def test_adjust_reports_thresholds_crossed_falling(dcc_world):
    """The forgetting direction is a beat too — this is why it is not a clock."""
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS, current=6)
    result = m.adjust("Y Cof", -4)
    assert [t["at"] for t in result["crossed"]] == [3, 5]
    assert result["after"] == 2


def test_adjust_persists_between_managers(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6)
    m.adjust("Y Cof", 4)
    assert WorldTrackManager(dcc_world).get_tracks()["Y Cof"]["current"] == 4


def test_set_value_reports_crossings(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    result = m.set_value("Y Cof", 4)
    assert result["after"] == 4
    assert [t["at"] for t in result["crossed"]] == [3]


def test_adjust_unknown_track_returns_none(dcc_world):
    assert WorldTrackManager(dcc_world).adjust("Nothing", 1) is None


def test_remove_track(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6)
    assert m.remove_track("Y Cof") is True
    assert m.remove_track("Y Cof") is False
    assert "Y Cof" not in m.get_tracks()


def test_render_shows_a_bar_and_value(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, current=2)
    out = WorldTrackManager.render(m.get_tracks())
    assert "Y Cof" in out
    assert "2/6" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_world_tracks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.world_tracks'`

- [ ] **Step 3: Write the implementation**

Create `lib/world_tracks.py`:

```python
#!/usr/bin/env python3
"""
World tracks — persisted, world-level named meters.

A threat clock only fills (`ThreatClockManager.advance` clamps the top and not the
bottom, deliberately). A world track moves BOTH ways and reports every threshold it
crosses in either direction, because the world forgetting something over generations
is as much a beat as the world learning it.

Values live in world-tracks.json. All arithmetic delegates to game_core.named_track,
so a stored track behaves exactly like the kit primitive a ruleset declares — the
declaration in ruleset.json `systems` says what a track means, this says where its
value lives.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from entity_manager import EntityManager
from game_core import named_track


class WorldTrackManager(EntityManager):
    """Named world-level meters with bidirectional threshold reporting."""

    def __init__(self, world_state_dir: str = None):
        super().__init__(world_state_dir)
        self._wsd = world_state_dir
        self.tracks_file = "world-tracks.json"

    def _load(self) -> Dict[str, Any]:
        return self.json_ops.load_json(self.tracks_file) or {}

    def add_track(self, name: str, max_value: int, thresholds: List[Dict] = None,
                  note: str = None, current: int = 0) -> Dict[str, Any]:
        data = self._load()
        entry = {
            "current": max(0, min(int(max_value), int(current))),
            "max": int(max_value),
            "thresholds": list(thresholds or []),
        }
        if note:
            entry["note"] = note
        data[name] = entry
        self.json_ops.save_json(self.tracks_file, data)
        return entry

    def adjust(self, name: str, delta: int) -> Optional[Dict[str, Any]]:
        """Apply delta, clamped to [0, max]. Returns the named_track result + name."""
        data = self._load()
        track = data.get(name)
        if track is None:
            return None
        result = named_track(
            int(track.get("current", 0)),
            int(delta),
            {"max": int(track.get("max", 0)),
             "thresholds": track.get("thresholds") or []},
        )
        track["current"] = result["after"]
        self.json_ops.save_json(self.tracks_file, data)
        return {"name": name, **result}

    def set_value(self, name: str, value: int) -> Optional[Dict[str, Any]]:
        """Set an absolute value, still reporting the thresholds it passes through."""
        track = self._load().get(name)
        if track is None:
            return None
        return self.adjust(name, int(value) - int(track.get("current", 0)))

    def remove_track(self, name: str) -> bool:
        data = self._load()
        if name in data:
            del data[name]
            self.json_ops.save_json(self.tracks_file, data)
            return True
        return False

    def get_tracks(self) -> Dict[str, Any]:
        return self._load()

    @staticmethod
    def render(tracks: Dict[str, Any]) -> str:
        """Filled/empty bars for the GM-visible context."""
        lines = []
        for name, t in tracks.items():
            cur, mx = int(t.get("current", 0)), int(t.get("max", 1))
            bar = "●" * cur + "○" * max(0, mx - cur)
            note = f" — {t['note']}" if t.get("note") else ""
            lines.append(f"{name}: [{bar}] {cur}/{mx}{note}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_world_tracks.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit**

```bash
git add lib/world_tracks.py tests/test_world_tracks.py
git commit -m "$(cat <<'EOF'
world-tracks: persisted world-level meters over game_core.named_track

A threat clock only fills. Y Cof and meters like it must fall as well as rise,
and report the thresholds crossed in either direction.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 2: Fire threshold consequences on upward crossings

**Files:**
- Modify: `lib/world_tracks.py` (add `_fire_crossings`, call it from `adjust`)
- Test: `tests/test_world_tracks.py` (append)

**Interfaces:**
- Consumes: `WorldTrackManager.adjust` from Task 1; `ConsequenceManager.add_consequence(text: str, trigger: str) -> str` (`lib/consequence_manager.py`).
- Produces: `adjust()` and `set_value()` return dicts gain a `"fired"` key — a `list[str]` of consequence ids, empty when nothing fired.

Climbing is the dangerous direction, so only upward crossings fire. Firing on the way down would be incoherent — the world forgetting something is not an event that arrives. This mirrors `ThreatClockManager._fire_if_filled` (`lib/threat_clocks.py:43`), including its stdout redirection.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_world_tracks.py`:

```python
from lib.consequence_manager import ConsequenceManager

RUMOUR = "A rumour with the right shape is circulating."


def _active(world):
    data = ConsequenceManager(world).json_ops.load_json("consequences.json") or {}
    return [c.get("consequence", "") for c in data.get("active", [])]


def _fired(world, needle=RUMOUR):
    return [c for c in _active(world) if needle in c]


def test_climbing_past_a_threshold_fires_its_consequence(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    result = m.adjust("Y Cof", 3)
    fired = _fired(dcc_world)
    assert len(fired) == 1
    assert "[Track — Y Cof]" in fired[0]
    assert len(result["fired"]) == 1


def test_falling_past_a_threshold_fires_nothing(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS, current=6)
    result = m.adjust("Y Cof", -4)
    assert _fired(dcc_world) == []
    assert result["fired"] == []


def test_climbing_two_thresholds_at_once_fires_both(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    result = m.adjust("Y Cof", 5)
    assert len(result["fired"]) == 2


def test_threshold_without_a_consequence_fires_nothing(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Quiet", 3, thresholds=[{"at": 1}])
    before = len(_active(dcc_world))
    result = m.adjust("Quiet", 1)
    assert result["fired"] == []
    assert len(_active(dcc_world)) == before


def test_firing_keeps_stdout_parseable(dcc_world, capsys):
    """adjust() is behind a --json CLI path; a fire must not leak onto stdout."""
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    capsys.readouterr()
    m.adjust("Y Cof", 3)
    out = capsys.readouterr()
    assert out.out.strip() == "", f"fire leaked onto stdout: {out.out!r}"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_world_tracks.py -v -k "fire or firing or threshold_without"`
Expected: FAIL — `KeyError: 'fired'`

- [ ] **Step 3: Write the implementation**

In `lib/world_tracks.py`, add the method to `WorldTrackManager`:

```python
    def _fire_crossings(self, name: str, result: Dict[str, Any]) -> List[str]:
        """Write consequences for thresholds crossed while CLIMBING.

        Climbing is the dangerous direction — the world learning something is an
        event that arrives, while the world forgetting is a slow condition. Firing
        both ways would put an incoherent beat in front of the GM every time a
        track decayed. Mirrors ThreatClockManager._fire_if_filled, including the
        stdout redirect: add_consequence announces itself, and this runs inside
        adjust(), whose --json output must stay parseable.
        """
        if result["after"] <= result["before"]:
            return []
        import contextlib
        from consequence_manager import ConsequenceManager

        fired = []
        with contextlib.redirect_stdout(sys.stderr):
            cm = ConsequenceManager(self._wsd)
            for threshold in result.get("crossed") or []:
                text = threshold.get("consequence")
                if not text:
                    continue
                fired.append(cm.add_consequence(
                    f"[Track — {name}] {text}",
                    trigger=f"the {name} track reached {threshold.get('at')}"))
        return fired
```

Then change the tail of `adjust()` from:

```python
        track["current"] = result["after"]
        self.json_ops.save_json(self.tracks_file, data)
        return {"name": name, **result}
```

to:

```python
        track["current"] = result["after"]
        self.json_ops.save_json(self.tracks_file, data)
        return {"name": name, **result, "fired": self._fire_crossings(name, result)}
```

- [ ] **Step 4: Run the full track suite to verify it passes**

Run: `uv run --extra dev pytest tests/test_world_tracks.py -v`
Expected: PASS — 14 passed

- [ ] **Step 5: Commit**

```bash
git add lib/world_tracks.py tests/test_world_tracks.py
git commit -m "$(cat <<'EOF'
world-tracks: fire threshold consequences on upward crossings

Climbing is the direction that arrives as a beat; decay is a condition.
Mirrors the clock fire path, stdout redirect included.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 3: World tracks CLI and wrapper

**Files:**
- Modify: `lib/world_tracks.py` (append `main()`)
- Create: `tools/gm-track.sh`
- Test: `tests/test_world_tracks.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 1–2; `cli_output.wants_json/strip_json_flag/emit`.
- Produces: `bash tools/gm-track.sh add|adjust|set|remove|list [--json]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_tracks.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(world, *args):
    env = dict(os.environ, GM_WORLD_STATE_BASE=str(world))
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "lib" / "world_tracks.py"), *args],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))


def test_cli_list_emits_a_json_envelope(dcc_world):
    WorldTrackManager(dcc_world).add_track("Y Cof", 6, thresholds=THRESHOLDS)
    proc = _run_cli(dcc_world, "list", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["data"]["Y Cof"]["max"] == 6


def test_cli_adjust_json_stays_parseable_when_a_threshold_fires(dcc_world):
    WorldTrackManager(dcc_world).add_track("Y Cof", 6, thresholds=THRESHOLDS)
    proc = _run_cli(dcc_world, "adjust", "Y Cof", "--delta", "3", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["data"]["after"] == 3
    assert len(payload["data"]["fired"]) == 1
```

Note: `dcc_world` copies the fixture to `<tmp>/world-state`, and `GM_WORLD_STATE_BASE`
points the manager's default base at it, so the CLI (which constructs the manager with
no argument) resolves to the same tree.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_world_tracks.py -v -k cli`
Expected: FAIL — non-zero return code, argparse reports no such action

- [ ] **Step 3: Write the implementation**

Append to `lib/world_tracks.py`:

```python
def main():
    import argparse
    import json
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    parser = argparse.ArgumentParser(description="World tracks")
    sub = parser.add_subparsers(dest="action")

    p = sub.add_parser("add"); p.add_argument("name"); p.add_argument("max", type=int)
    p.add_argument("--current", type=int, default=0)
    p.add_argument("--note")
    p.add_argument("--thresholds-json",
                   help='[{"at": 3, "consequence": "..."}, ...]')

    p = sub.add_parser("adjust"); p.add_argument("name")
    p.add_argument("--delta", type=int, required=True)

    p = sub.add_parser("set"); p.add_argument("name")
    p.add_argument("--value", type=int, required=True)

    p = sub.add_parser("remove"); p.add_argument("name")
    sub.add_parser("list")

    json_mode = wants_json()
    args = parser.parse_args(strip_json_flag(sys.argv[1:]))
    if not args.action:
        parser.print_help(); sys.exit(1)

    m = WorldTrackManager()
    if args.action == "add":
        thresholds = json.loads(args.thresholds_json) if args.thresholds_json else None
        out = m.add_track(args.name, args.max, thresholds=thresholds,
                          note=args.note, current=args.current)
    elif args.action == "adjust":
        out = m.adjust(args.name, args.delta)
    elif args.action == "set":
        out = m.set_value(args.name, args.value)
    elif args.action == "remove":
        out = {"removed": m.remove_track(args.name)}
    else:
        out = m.get_tracks()

    if out is None:
        sys.exit(emit_error(f"no such track: {args.name}", json_mode))

    if json_mode:
        emit(out, json_mode=True)
    else:
        print(json.dumps(out, indent=2))
        if args.action == "list":
            print(WorldTrackManager.render(out))


if __name__ == "__main__":
    main()
```

Create `tools/gm-track.sh`:

```bash
#!/bin/bash
# gm-track.sh - World tracks (thin wrapper for world_tracks.py)
#
#   gm-track.sh list                                  Show all world tracks
#   gm-track.sh add "Y Cof" 6 [--current N] [--note "..."]
#              [--thresholds-json '[{"at":3,"consequence":"..."}]']
#                                                     New world-level meter
#   gm-track.sh adjust "Y Cof" --delta 2              Move it (clamped to [0,max])
#   gm-track.sh set "Y Cof" --value 4                 Set it absolutely
#   gm-track.sh remove "Y Cof"                        Remove a track
#
# Thresholds crossed while CLIMBING fire into the consequence engine.
# Crossings in BOTH directions are reported. All commands accept --json.

source "$(dirname "$0")/common.sh"

require_active_campaign

$PYTHON_CMD "$LIB_DIR/world_tracks.py" "$@"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_world_tracks.py -v`
Expected: PASS — 16 passed

Then confirm the wrapper is reachable:

Run: `bash tools/gm-track.sh 2>&1 | head -5`
Expected: argparse usage text, or the no-active-campaign guard message

- [ ] **Step 5: Commit**

```bash
git add lib/world_tracks.py tools/gm-track.sh tests/test_world_tracks.py
git commit -m "$(cat <<'EOF'
world-tracks: CLI + gm-track.sh wrapper

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 4: FactionManager core — standing and membership

**Files:**
- Create: `lib/faction_manager.py`
- Test: `tests/test_faction_manager.py`

**Interfaces:**
- Consumes: `EntityManager`.
- Produces:
  - `FactionManager(world_state_dir: str = None)` with `factions_file = "factions.json"`
  - `add_faction(name: str, standing: int = 0, note: str = None) -> dict`
  - `set_standing(name: str, value: int) -> dict | None`
  - `adjust_standing(name: str, delta: int) -> dict | None`
  - `add_member(name: str, npc: str) -> dict | None`
  - `remove_member(name: str, npc: str) -> dict | None`
  - `remove_faction(name: str) -> bool`
  - `get_factions() -> dict`
  - Module constants `STANDING_MIN = -5`, `STANDING_MAX = 5`

- [ ] **Step 1: Write the failing test**

Create `tests/test_faction_manager.py`:

```python
"""Tests for faction state.

The bible's `factions` graph is a static, confirm-locked reference. This is the
live half: standing the PC has earned, who belongs to what, and who holds which
ground.
"""

from lib.faction_manager import FactionManager, STANDING_MAX, STANDING_MIN

TITHE = "The Valley Tithe"
WOLVES = "Plant y Lleuad"


def test_add_faction_defaults_to_neutral_standing(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE, note="The families bound to the offering.")
    stored = m.get_factions()[TITHE]
    assert stored["standing"] == 0
    assert stored["members"] == []
    assert stored["territory"] == []
    assert stored["relations"] == {}
    assert stored["note"] == "The families bound to the offering."


def test_standing_clamps_to_the_reaction_roll_range(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    assert m.set_standing(TITHE, 99)["standing"] == STANDING_MAX
    assert m.set_standing(TITHE, -99)["standing"] == STANDING_MIN


def test_adjust_standing_accumulates_and_clamps(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE, standing=3)
    assert m.adjust_standing(TITHE, 1)["standing"] == 4
    assert m.adjust_standing(TITHE, 10)["standing"] == STANDING_MAX
    assert m.adjust_standing(TITHE, -20)["standing"] == STANDING_MIN


def test_membership_is_added_once_and_removed_case_insensitively(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.add_member(TITHE, "Nest")
    m.add_member(TITHE, "nest")
    assert m.get_factions()[TITHE]["members"] == ["Nest"]

    m.remove_member(TITHE, "NEST")
    assert m.get_factions()[TITHE]["members"] == []


def test_membership_persists_between_managers(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.add_member(TITHE, "Aeron")
    assert FactionManager(dcc_world).get_factions()[TITHE]["members"] == ["Aeron"]


def test_operations_on_an_unknown_faction_return_none(dcc_world):
    m = FactionManager(dcc_world)
    assert m.set_standing(WOLVES, 1) is None
    assert m.adjust_standing(WOLVES, 1) is None
    assert m.add_member(WOLVES, "Nest") is None


def test_remove_faction(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    assert m.remove_faction(TITHE) is True
    assert m.remove_faction(TITHE) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_faction_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.faction_manager'`

- [ ] **Step 3: Write the implementation**

Create `lib/faction_manager.py`:

```python
#!/usr/bin/env python3
"""
Factions — the live half of the world's politics.

world-bible.json carries a `factions` graph, but the bible is a confirm-locked
reference document with no write path: it says who exists, not who currently holds
what. This owns the mutable half — standing the PC has earned, who belongs to which
faction, which ground each one claims, and how they regard each other.

`standing` is clamped to [-5, +5] so it drops straight into
game_core.reaction_roll as its `track_value`.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from entity_manager import EntityManager

STANDING_MIN = -5
STANDING_MAX = 5


def _clamp_standing(value: Any) -> int:
    return max(STANDING_MIN, min(STANDING_MAX, int(value)))


def _has_ci(items: List[Any], value: str) -> bool:
    """Case-insensitive membership, matching entity_manager.npcs_present."""
    needle = (value or "").strip().lower()
    return any(str(i).strip().lower() == needle for i in (items or []))


def _without_ci(items: List[Any], value: str) -> List[Any]:
    needle = (value or "").strip().lower()
    return [i for i in (items or []) if str(i).strip().lower() != needle]


class FactionManager(EntityManager):
    """Standing, membership, territory and relations for the world's factions."""

    def __init__(self, world_state_dir: str = None):
        super().__init__(world_state_dir)
        self._wsd = world_state_dir
        self.factions_file = "factions.json"

    def _load(self) -> Dict[str, Any]:
        return self.json_ops.load_json(self.factions_file) or {}

    def _save(self, data: Dict[str, Any]) -> None:
        self.json_ops.save_json(self.factions_file, data)

    def add_faction(self, name: str, standing: int = 0,
                    note: str = None) -> Dict[str, Any]:
        data = self._load()
        entry = {
            "standing": _clamp_standing(standing),
            "members": [],
            "territory": [],
            "relations": {},
        }
        if note:
            entry["note"] = note
        data[name] = entry
        self._save(data)
        return entry

    def set_standing(self, name: str, value: int) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        faction["standing"] = _clamp_standing(value)
        self._save(data)
        return faction

    def adjust_standing(self, name: str, delta: int) -> Optional[Dict[str, Any]]:
        faction = self._load().get(name)
        if faction is None:
            return None
        return self.set_standing(name, int(faction.get("standing", 0)) + int(delta))

    def add_member(self, name: str, npc: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        members = faction.setdefault("members", [])
        if not _has_ci(members, npc):
            members.append(npc)
            self._save(data)
        return faction

    def remove_member(self, name: str, npc: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        faction["members"] = _without_ci(faction.get("members"), npc)
        self._save(data)
        return faction

    def remove_faction(self, name: str) -> bool:
        data = self._load()
        if name in data:
            del data[name]
            self._save(data)
            return True
        return False

    def get_factions(self) -> Dict[str, Any]:
        return self._load()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_faction_manager.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add lib/faction_manager.py tests/test_faction_manager.py
git commit -m "$(cat <<'EOF'
factions: standing + membership, the live half of the bible's static graph

standing is clamped to [-5,+5] so it feeds game_core.reaction_roll directly.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 5: Territory — claims, holders, and contested ground

**Files:**
- Modify: `lib/faction_manager.py`
- Test: `tests/test_faction_manager.py` (append)

**Interfaces:**
- Consumes: `FactionManager` and the `_has_ci` / `_without_ci` helpers from Task 4.
- Produces:
  - `claim(name: str, location: str) -> dict | None`
  - `release(name: str, location: str) -> dict | None`
  - `holders_of(location: str) -> list[str]`
  - `contested() -> dict[str, list[str]]` — location (stored casing) → faction names, only where more than one claims it

`holders_of` and `contested` are what make territory more than a list: who holds this
place, and where two factions both think they do.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_faction_manager.py`:

```python
CWM = "Cwm Bedd"


def test_claim_is_idempotent_and_case_insensitive(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.claim(TITHE, CWM)
    m.claim(TITHE, "cwm bedd")
    assert m.get_factions()[TITHE]["territory"] == [CWM]


def test_release_removes_a_claim(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.claim(TITHE, CWM)
    m.release(TITHE, "CWM BEDD")
    assert m.get_factions()[TITHE]["territory"] == []


def test_holders_of_finds_every_claimant(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.add_faction(WOLVES)
    m.claim(TITHE, CWM)
    m.claim(WOLVES, "cwm bedd")
    assert sorted(m.holders_of(CWM)) == sorted([TITHE, WOLVES])


def test_holders_of_unclaimed_ground_is_empty(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    assert m.holders_of("Preseli") == []
    assert m.holders_of("") == []


def test_contested_lists_only_ground_two_factions_claim(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.add_faction(WOLVES)
    m.claim(TITHE, CWM)
    m.claim(TITHE, "Preseli")
    m.claim(WOLVES, "cwm bedd")

    contested = m.contested()
    assert list(contested.keys()) == [CWM]
    assert sorted(contested[CWM]) == sorted([TITHE, WOLVES])


def test_claim_on_an_unknown_faction_returns_none(dcc_world):
    assert FactionManager(dcc_world).claim("Nobody", CWM) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_faction_manager.py -v -k "claim or holders or contested or release"`
Expected: FAIL — `AttributeError: 'FactionManager' object has no attribute 'claim'`

- [ ] **Step 3: Write the implementation**

Add to `FactionManager` in `lib/faction_manager.py`:

```python
    def claim(self, name: str, location: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        territory = faction.setdefault("territory", [])
        if not _has_ci(territory, location):
            territory.append(location)
            self._save(data)
        return faction

    def release(self, name: str, location: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        faction["territory"] = _without_ci(faction.get("territory"), location)
        self._save(data)
        return faction

    def holders_of(self, location: str) -> List[str]:
        """Every faction claiming this place. More than one means contested."""
        if not (location or "").strip():
            return []
        return [name for name, f in self._load().items()
                if _has_ci(f.get("territory"), location)]

    def contested(self) -> Dict[str, List[str]]:
        """Ground more than one faction claims: location (as stored) -> claimants."""
        claimants: Dict[str, List[str]] = {}
        display: Dict[str, str] = {}
        for name, faction in self._load().items():
            for place in faction.get("territory") or []:
                key = str(place).strip().lower()
                if not key:
                    continue
                display.setdefault(key, str(place))
                claimants.setdefault(key, []).append(name)
        return {display[k]: v for k, v in claimants.items() if len(v) > 1}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_faction_manager.py -v`
Expected: PASS — 13 passed

- [ ] **Step 5: Commit**

```bash
git add lib/faction_manager.py tests/test_faction_manager.py
git commit -m "$(cat <<'EOF'
factions: territory claims, holders_of, and contested ground

Two claimants on one place is the politics; a list of places is not.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 6: Relations, render, CLI and wrapper

**Files:**
- Modify: `lib/faction_manager.py`
- Create: `tools/gm-faction.sh`
- Test: `tests/test_faction_manager.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 4–5.
- Produces:
  - `set_relation(name: str, other: str, stance: str) -> dict | None`
  - `render(factions: dict) -> str` (staticmethod)
  - `bash tools/gm-faction.sh add|standing|member|unmember|claim|release|relation|holders|contested|remove|list [--json]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_faction_manager.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(world, *args):
    env = dict(os.environ, GM_WORLD_STATE_BASE=str(world))
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "lib" / "faction_manager.py"), *args],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))


def test_set_relation_records_a_stance(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.set_relation(TITHE, WOLVES, "hostile")
    assert m.get_factions()[TITHE]["relations"][WOLVES] == "hostile"


def test_render_shows_standing_and_territory(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE, standing=2)
    m.claim(TITHE, CWM)
    m.add_member(TITHE, "Nest")
    out = FactionManager.render(m.get_factions())
    assert TITHE in out
    assert "+2" in out
    assert CWM in out
    assert "Nest" in out


def test_cli_list_emits_a_json_envelope(dcc_world):
    FactionManager(dcc_world).add_faction(TITHE, standing=1)
    proc = _run_cli(dcc_world, "list", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["data"][TITHE]["standing"] == 1


def test_cli_contested_reports_shared_ground(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE); m.add_faction(WOLVES)
    m.claim(TITHE, CWM); m.claim(WOLVES, CWM)
    proc = _run_cli(dcc_world, "contested", "--json")
    assert proc.returncode == 0, proc.stderr
    assert sorted(json.loads(proc.stdout)["data"][CWM]) == sorted([TITHE, WOLVES])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_faction_manager.py -v -k "relation or render or cli"`
Expected: FAIL — `AttributeError: 'FactionManager' object has no attribute 'set_relation'`

- [ ] **Step 3: Write the implementation**

Add to `FactionManager`:

```python
    def set_relation(self, name: str, other: str,
                     stance: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        faction = data.get(name)
        if faction is None:
            return None
        faction.setdefault("relations", {})[other] = stance
        self._save(data)
        return faction

    @staticmethod
    def render(factions: Dict[str, Any]) -> str:
        """One line per faction for the GM-visible context."""
        lines = []
        for name, f in factions.items():
            parts = [f"standing {int(f.get('standing', 0)):+d}"]
            if f.get("territory"):
                parts.append("holds: " + ", ".join(f["territory"]))
            if f.get("members"):
                parts.append("members: " + ", ".join(f["members"]))
            for other, stance in (f.get("relations") or {}).items():
                parts.append(f"vs {other}: {stance}")
            lines.append(f"{name}: " + " | ".join(parts))
        return "\n".join(lines)
```

Append `main()` to `lib/faction_manager.py`:

```python
def main():
    import argparse
    import json
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    parser = argparse.ArgumentParser(description="Factions")
    sub = parser.add_subparsers(dest="action")

    p = sub.add_parser("add"); p.add_argument("name")
    p.add_argument("--standing", type=int, default=0); p.add_argument("--note")
    p = sub.add_parser("standing"); p.add_argument("name")
    p.add_argument("--set", dest="set_value", type=int)
    p.add_argument("--delta", type=int)
    p = sub.add_parser("member"); p.add_argument("name"); p.add_argument("npc")
    p = sub.add_parser("unmember"); p.add_argument("name"); p.add_argument("npc")
    p = sub.add_parser("claim"); p.add_argument("name"); p.add_argument("location")
    p = sub.add_parser("release"); p.add_argument("name"); p.add_argument("location")
    p = sub.add_parser("relation"); p.add_argument("name")
    p.add_argument("other"); p.add_argument("stance")
    p = sub.add_parser("holders"); p.add_argument("location")
    sub.add_parser("contested")
    p = sub.add_parser("remove"); p.add_argument("name")
    sub.add_parser("list")

    json_mode = wants_json()
    args = parser.parse_args(strip_json_flag(sys.argv[1:]))
    if not args.action:
        parser.print_help(); sys.exit(1)

    m = FactionManager()
    if args.action == "add":
        out = m.add_faction(args.name, standing=args.standing, note=args.note)
    elif args.action == "standing":
        if args.set_value is None and args.delta is None:
            sys.exit(emit_error("pass --set or --delta", json_mode))
        out = (m.set_standing(args.name, args.set_value) if args.set_value is not None
               else m.adjust_standing(args.name, args.delta))
    elif args.action == "member":
        out = m.add_member(args.name, args.npc)
    elif args.action == "unmember":
        out = m.remove_member(args.name, args.npc)
    elif args.action == "claim":
        out = m.claim(args.name, args.location)
    elif args.action == "release":
        out = m.release(args.name, args.location)
    elif args.action == "relation":
        out = m.set_relation(args.name, args.other, args.stance)
    elif args.action == "holders":
        out = m.holders_of(args.location)
    elif args.action == "contested":
        out = m.contested()
    elif args.action == "remove":
        out = {"removed": m.remove_faction(args.name)}
    else:
        out = m.get_factions()

    if out is None:
        sys.exit(emit_error(f"no such faction: {args.name}", json_mode))

    if json_mode:
        emit(out, json_mode=True)
    else:
        print(json.dumps(out, indent=2))
        if args.action == "list":
            print(FactionManager.render(out))


if __name__ == "__main__":
    main()
```

Create `tools/gm-faction.sh`:

```bash
#!/bin/bash
# gm-faction.sh - Faction state (thin wrapper for faction_manager.py)
#
#   gm-faction.sh list                                Show all factions
#   gm-faction.sh add "Name" [--standing N] [--note "..."]
#   gm-faction.sh standing "Name" --set 2             Set standing (clamped -5..+5)
#   gm-faction.sh standing "Name" --delta -1          Adjust standing
#   gm-faction.sh member "Name" "NPC"                 Add a member
#   gm-faction.sh unmember "Name" "NPC"               Remove a member
#   gm-faction.sh claim "Name" "Location"             Claim territory
#   gm-faction.sh release "Name" "Location"           Drop a claim
#   gm-faction.sh relation "Name" "Other" hostile     How they regard another faction
#   gm-faction.sh holders "Location"                  Who claims this place
#   gm-faction.sh contested                           Ground claimed by more than one
#   gm-faction.sh remove "Name"                       Remove a faction
#
# `standing` is clamped to [-5,+5] and feeds game_core.reaction_roll directly.
# All commands accept --json.

source "$(dirname "$0")/common.sh"

require_active_campaign

$PYTHON_CMD "$LIB_DIR/faction_manager.py" "$@"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_faction_manager.py -v`
Expected: PASS — 17 passed

- [ ] **Step 5: Commit**

```bash
git add lib/faction_manager.py tools/gm-faction.sh tests/test_faction_manager.py
git commit -m "$(cat <<'EOF'
factions: relations, render, CLI + gm-faction.sh wrapper

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

### Task 7: Scene context wiring and docs

**Files:**
- Modify: `lib/session_manager.py:847-856` (insert after the THREAT CLOCKS block)
- Create: `tests/test_world_state_context.py`
- Modify: `docs/modules/living-world.md`, `docs/schema-reference.md`

**Interfaces:**
- Consumes: `WorldTrackManager.render` (Task 1), `FactionManager.render` and `contested` (Tasks 5–6).
- Produces: `get_full_context()` output gains `--- WORLD TRACKS ---` and `--- FACTIONS ---` sections, each rendered only when non-empty.

`session_manager` reads sibling JSON directly via `self.json_ops.load_json` for
clocks rather than constructing a manager; follow that pattern for the data load, and
use the managers only for their static `render` helpers.

- [ ] **Step 1: Write the failing test**

Create `tests/test_world_state_context.py`:

```python
"""World tracks and factions must reach the GM through scene context.

State the GM never sees is state that does not exist at the table.
"""

from lib.faction_manager import FactionManager
from lib.session_manager import SessionManager
from lib.world_tracks import WorldTrackManager


def test_world_tracks_render_into_context(dcc_world):
    WorldTrackManager(dcc_world).add_track(
        "Y Cof", 6, current=2, note="What the world remembers.")
    context = SessionManager(dcc_world).get_full_context()
    assert "--- WORLD TRACKS ---" in context
    assert "Y Cof" in context
    assert "2/6" in context


def test_factions_render_into_context(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction("The Valley Tithe", standing=2)
    m.claim("The Valley Tithe", "Cwm Bedd")
    context = SessionManager(dcc_world).get_full_context()
    assert "--- FACTIONS ---" in context
    assert "The Valley Tithe" in context
    assert "Cwm Bedd" in context


def test_contested_ground_is_flagged(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction("The Valley Tithe")
    m.add_faction("Plant y Lleuad")
    m.claim("The Valley Tithe", "Cwm Bedd")
    m.claim("Plant y Lleuad", "Cwm Bedd")
    context = SessionManager(dcc_world).get_full_context()
    assert "CONTESTED" in context
    assert "Cwm Bedd" in context


def test_sections_are_absent_when_nothing_is_declared(dcc_world):
    context = SessionManager(dcc_world).get_full_context()
    assert "--- WORLD TRACKS ---" not in context
    assert "--- FACTIONS ---" not in context
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_world_state_context.py -v`
Expected: FAIL — `AssertionError: assert '--- WORLD TRACKS ---' in ...`

- [ ] **Step 3: Write the implementation**

In `lib/session_manager.py`, immediately after the THREAT CLOCKS block that ends at
line 856 (`lines.append(f"{clock_name}: [{bar}] {cur}/{mx}{flag}")`), insert:

```python
        # --- World Tracks (bidirectional world-level meters; only when declared) ---
        tracks = self.json_ops.load_json("world-tracks.json") or {}
        if tracks:
            from world_tracks import WorldTrackManager
            lines.append("")
            lines.append("--- WORLD TRACKS ---")
            lines.append(WorldTrackManager.render(tracks))

        # --- Factions (standing, territory, relations; only when declared) ---
        factions = self.json_ops.load_json("factions.json") or {}
        if factions:
            from faction_manager import FactionManager
            lines.append("")
            lines.append("--- FACTIONS ---")
            lines.append(FactionManager.render(factions))
            for place, claimants in FactionManager(self._wsd).contested().items():
                lines.append(f"⚔ CONTESTED: {place} — {', '.join(claimants)}")
```

`self._wsd` already exists — `SessionManager.__init__` sets it at
`lib/session_manager.py:80`, commented as "passed through to sibling managers". Use it
as-is; do not add a second world-state attribute.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_world_state_context.py -v`
Expected: PASS — 4 passed

Then confirm nothing else regressed:

Run: `uv run --extra dev pytest`
Expected: PASS — the full suite, with no new failures against the pre-change baseline

- [ ] **Step 5: Update the docs**

In `docs/modules/living-world.md`, add a section after the threat-clocks material:

```markdown
## World tracks

`world-tracks.json`, via `lib/world_tracks.py` / `bash tools/gm-track.sh`.

A threat clock only fills — `advance()` clamps the top and not the bottom, on
purpose. A world track moves both ways and reports every threshold it crosses in
either direction, because the world *forgetting* something over generations is as
much a beat as the world learning it. All arithmetic delegates to
`game_core.named_track`, so a stored track behaves exactly like the kit primitive a
ruleset declares.

Thresholds fire into the consequence engine on **upward** crossings only. Climbing
is the direction that arrives as an event; decay is a slow condition, and firing on
the way down would put an incoherent beat in front of the GM.

## Factions

`factions.json`, via `lib/faction_manager.py` / `bash tools/gm-faction.sh`.

`world-bible.json` carries a `factions` graph, but the bible is a confirm-locked
reference with no write path: it says who exists, not who currently holds what. This
owns the mutable half — `standing` (clamped `[-5, +5]`, consumable directly as
`game_core.reaction_roll`'s `track_value`), `members`, `territory`, and `relations`.

`holders_of(location)` and `contested()` are what make territory more than a list:
ground claimed by two factions is flagged in scene context.
```

In `docs/schema-reference.md`, add both file shapes:

```markdown
### `world-tracks.json`

```json
{
  "Y Cof": {
    "current": 2,
    "max": 6,
    "thresholds": [{"at": 3, "consequence": "A rumour is circulating."}],
    "note": "What the world remembers about killing the Old Dead."
  }
}
```

### `factions.json`

```json
{
  "The Valley Tithe": {
    "standing": 1,
    "members": ["Nest"],
    "territory": ["Cwm Bedd"],
    "relations": {"Plant y Lleuad": "hostile"},
    "note": "The families bound to the offering."
  }
}
```
```

- [ ] **Step 6: Commit**

```bash
git add lib/session_manager.py tests/test_world_state_context.py docs/modules/living-world.md docs/schema-reference.md
git commit -m "$(cat <<'EOF'
world-state-context: surface world tracks + factions in scene context

State the GM never sees is state that does not exist at the table. Contested
ground is flagged explicitly.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01LjoPBmbPg1Hk3iGVJN9u9o
EOF
)"
```

---

## Notes for the executor

- **Baseline the suite first.** Run `uv run --extra dev pytest` before Task 1 and keep
  the result. `docs/log.md` records a pre-existing failure in the suite, so "no *new*
  failures" is the bar, not "everything green".
- **`session_manager.py` line numbers will drift** as earlier tasks land. Anchor on the
  THREAT CLOCKS block, not on line 847.
- **OKF tooling is not installed on this machine** (`~/.claude/skills/okf/scripts/okf.mjs`
  is missing), so the `okf status` step from CLAUDE.md cannot run. The claiming docs
  were identified by hand: `docs/modules/living-world.md`, `docs/schema-reference.md`,
  and `docs/flows/play-turn.md` all mention threat clocks and are the natural homes for
  this material. Task 7 covers the first two; check `play-turn.md` and update it if it
  enumerates context sections.
- **Campaign creation is not blocked by this plan.** See the build-order table in
  `docs/superpowers/specs/2026-09-08-the-slow-heart-design.md` — every creation step
  writes a declaration, and these managers add live state on top of declarations.
