# World Tracks & Factions — Spec

**Date:** 2026-09-08
**Campaign context:** `2026-09-08-the-slow-heart-design.md`

## Problem

Two gaps in the engine, both found while designing a campaign about political
succession across four thousand years.

### 1. World-level meters have nowhere to live

`ruleset.json` `systems` entries are **declarations only**. Scene context renders a
`named_track`'s *shape* (`session_manager.py:1088`) but never a current value, because
`game_core.named_track` is a pure function — the caller supplies `current`.

The blood pool works only because it lives in the character's persisted `vitals`. A
meter that belongs to the *world* rather than a character has no home.

A threat clock is the only persisted numeric world-level meter, and it cannot serve:
`ThreatClockManager.advance()` computes `min(max, current + ticks)` with **no lower
clamp** (`threat_clocks.py:76`), so a clock cannot count down without going negative.
Clocks only fill, by design.

The campaign needs **Y Cof** — how much the living world remembers about killing
immortals — which must rise when the PC is witnessed and *fall* across generations as
the people who knew die. Both directions are meaningful beats.

### 2. There is no faction, territory or affiliation state

- `factions` exists only as a **static bible field**, validated as a graph
  (`world_bible.py:63`). The bible has no write CLI and `draft-bible` refuses a
  confirmed bible, so it is a reference document, not live state.
- **Zero** occurrences of territory, claim, allegiance, affiliation or ownership
  across `lib/` and `tools/`.

The individual layer of espionage is well served — `gm-npc.sh set-inner` gives each
NPC a goal, mood and **secret**, and `gm-npc.sh update` records per-NPC memory of the
player, surfaced in scene context whenever they are present. What is missing is the
macro layer: who belongs to what, who holds which ground, and how factions regard each
other and the PC.

Retrofitting this after fifty sessions means backfilling every NPC and location by
hand, and this campaign is explicitly about a political order forming, being
challenged, and being replaced.

## Requirements

### World tracks

- Persist named world-level meters with `current`, `max`, and thresholds.
- Arithmetic delegates to `game_core.named_track` so behaviour matches the kit
  primitive exactly: clamped to `[0, max]`, crossings reported in **both** directions.
- Threshold consequences fire into the consequence engine on **upward** crossings
  only — climbing is the dangerous direction, and firing on the way down would be
  incoherent. Mirrors `ThreatClockManager._fire_if_filled`.
- Firing must not leak onto stdout, so `--json` output stays parseable.
- Render in scene context alongside threat clocks.

### Factions

- Persist factions with `standing` (clamped `[-5, +5]`, usable directly as
  `game_core.reaction_roll`'s `track_value`), `members` (NPC names), `territory`
  (location names), `relations` (faction → stance), and an optional `note`.
- Territory must answer two questions that make it more than a list:
  **who holds this place**, and **which places are contested** (claimed by more than
  one faction).
- Membership and territory lookups are case-insensitive on read, preserving the
  stored casing — matching `entity_manager.npcs_present`.
- Render in scene context.

## Non-goals

- **Per-NPC belief state** ("NPC X believes something false"). The existing per-NPC
  memory field covers this as unstructured text; a structured version is a separate
  piece of work and is not needed to start play.
- **Auto-seeding `factions.json` from the bible graph.** A one-time manual seed at
  campaign creation is sufficient and avoids coupling live state to a confirm-locked
  document.
- **Faction standing thresholds.** `reaction_roll`'s tiers already do that job.

## Constraints

- Managers subclass `EntityManager`, persist via `self.json_ops`, and expose a CLI via
  `cli_output.wants_json` / `strip_json_flag` / `emit`.
- Bash wrappers are thin: source `common.sh`, `require_active_campaign`, delegate `"$@"`.
- Python is always invoked as `uv run python`.
- Tests run with `uv run --extra dev pytest` (pytest lives in the `dev` extra).
