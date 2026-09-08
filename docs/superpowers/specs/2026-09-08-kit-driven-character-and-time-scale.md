# Kit-Driven Character Render & Time Scale — Spec

**Date:** 2026-09-08
**Found by:** asking what The Slow Heart would need that does not exist yet.

## The governing principle

This repo's whole direction is that **the engine holds no game's concepts**. A World Kit
declares what its world runs on; the engine renders and resolves without understanding
any of it. `ruleset.json` already carries `stat_schema.attributes`, `stat_schema.vitals`,
`progression.model` and `resolution.model`, and `WorldKit` is the single reader.

The defects below are all the same failure: a place where the engine hardcoded one
game's vocabulary instead of asking the kit.

**The acceptance criterion for every change here: it must be expressible by a kit that
has never heard of vampires, and equally by one that has never heard of D&D.** A fix
that special-cases `blood` or `generation` would repeat the exact mistake at one remove
and is not a fix.

## Defect 1 — the CHARACTER block is a hardcoded 5e line

`lib/session_manager.py:907` builds the character line the GM reads **every turn** as a
fixed f-string:

```python
f"{name} - Level {level} {race} {cls} | HP: {hp_cur}/{hp_max} | AC: {ac} | XP: {xp_val} | Gold: {gold}"
```

Every field but name, level and HP is a 5e assumption. For a `custom` kit it renders:

```
Rhiannon - Level 0 Brythonic ? | HP: 30/30 | AC: ? | XP: 0 | Gold: 0
```

- `class` → `?` — the concept does not exist in that world
- `AC` → `?` — legitimate for a d20-vs-DC world to have, but only if the kit declares it
- `XP: 0` — a `milestone` kit does not track XP
- `Gold: 0` — printed from a `.get()` default even after creation was fixed to omit the
  key entirely, so removing it from the sheet changed nothing the GM sees
- **Every kit vital beyond `hp` is invisible** — including `blood`, the meter that gates
  every action in that campaign

The engine **already solved this elsewhere**. `WorldKit.vitals()` returns what the world
declares; `PlayerManager._kit_vitals()` walks it; `PlayerManager._vitals_summary()`
renders `| Vigor: 3/5 | Corruption: 2`; and `test_kit_vitals.py::test_vitals_appear_in_show_output`
guards it. `gm-player.sh show` has been kit-driven for some time. The context brief kept
a divergent hardcoded copy.

`PlayerManager._read_vital` is a `@staticmethod` (`player_manager.py:535`) and handles
both stored shapes — `{current, max}` and a plain number — so the fix reuses it rather
than duplicating the awkward part.

## Defect 2 — fixed traits have no declared home

A world's non-rolled, non-resource facts have nowhere to live. `stat_schema` has
`attributes` (rolled) and `vitals` (resources). Generation is neither: it is a fixed
property that gates ceilings, and it is the single number The Slow Heart's metaphysics
runs on. The same is true of that world's gift tier, and would be true of a lineage, a
clearance level, a caste, or a corporate rank in some other kit.

Today such a value can be written to the sheet but is invisible to the GM, and nothing
declares that the world has it.

Adding `generation` to `lib/` would hardcode one campaign into the engine exactly as
`class` hardcodes 5e. **The engine must never know what a trait means** — only that the
kit declared one and that the sheet may carry a value for it.

## Defect 3 — elapsed time caps at weeks

`lib/time_manager.py:20-21` recognises only `N day(s)` and `N week(s)`. Everything else
falls through to 1 tick, so `"10 years"`, `"a century"` and `"40 years of practice"` all
advance threat clocks exactly as far as waiting a moment.

**Large tick counts are not the problem.** `ThreatClockManager.tick_time_clocks`
(`threat_clocks.py:92-103`) clamps with `min(mx, cur + ticks)`, skips already-full
clocks, and fires each consequence once on the fill transition — so a huge skip cannot
overflow or double-fire. If forty years pass, every pending pressure resolving is the
truthful outcome, not a bug. The gap is only that the durations cannot be expressed.

## Requirements

1. The CHARACTER block renders what the active kit declares: name, level and HP always;
   every declared vital; every declared trait; and 5e sheet fields **only when present on
   the sheet**. No `?` placeholders, no invented zeros.
2. `stat_schema` gains an optional `traits` list. The engine renders declared traits
   without interpreting them. A kit declaring none is unaffected.
3. `ticks_from_duration` understands months and years alongside days and weeks.

## Non-goals

- **Per-NPC belief state ("who knows what").** A real subsystem, deferred to its own plan.
- **Machine-readable NPC generation.** Follows from requirement 2's pattern but touches
  `npc_manager`; separate work.
- **Any engine knowledge of a specific trait's meaning.** `generation` must remain a
  string in one campaign's `ruleset.json`.
- **Changing threat-clock tick semantics.** Clamping and once-per-fill firing are correct.

## Acceptance

Every requirement is tested against **at least three kits** — `dnd5e`, the
resource-axis DCC fixture, and a `custom` kit declaring extra vitals and traits — using
the existing `_make_world(tmp_path, slug, ruleset)` builder in `tests/test_kit_vitals.py`.
A change that only works for one of them has not met the bar.

## Deferred follow-ups (found during this plan, ruled out of its scope)

The CHARACTER brief was one of several surfaces rendering the same character.
Fixing it exposed the siblings. Each is real, none belongs to this spec — Defect 1
is scoped to the CHARACTER block, and widening it mid-branch is how a clean change
becomes an incident. Verified in the source at the lines named, 2026-09-08.

1. **`tools/gm-statusline.sh`** — the always-on HUD, still the same hardcoded
   template (`.race // "?"`, `.ac // "?"`, `.gold // 0`). It is the surface the
   player looks at most, and it is the last one still inventing placeholders.
2. **`lib/session_manager.py:975-979`** — the party-member block, four invented
   defaults (`hp` `{current:10,max:10}`, `ac` 10, `race` "Unknown", `class`
   "Commoner") and the same `.get('hp', {})` crash on a scalar-hp sheet.
3. **`lib/player_manager.py:712`** — `revive_character` reads
   `char.get('hp', {}).get('max', 0)` and then `char['hp']['current'] = ...`.
   Both raise on a kit that models hp as a bare number. Same class as the
   `show_player` crash this plan fixed; the finding named only the two show
   functions, so this one was missed at the time.
4. **`lib/identity_onboarding.py:69`** — `from_canon` writes
   `"ac": sheet.get("ac", 10)` unconditionally, so lifting a canon NPC to PC
   invents an armour class on any kit. Same family as the `gold`/`xp`/`ac`
   defaults fixed in `save_character.py`; a different write path entirely.

Items 3 and 4 are one-line fixes with a test each. Items 1 and 2 are the same
kit-driven render treatment this plan gave the CHARACTER block, applied twice more.
