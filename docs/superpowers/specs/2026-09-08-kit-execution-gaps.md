# Kit Execution Gaps & Build Bugs — Spec

**Date:** 2026-09-08
**Found by:** building the-slow-heart end to end via `/new-game`.

Three defects, all reproduced against real campaign data. Two are gaps that make
declared kit features non-functional; one is a crash that blocks play on Windows.

> **Retracted during investigation:** an earlier draft listed
> `gm-npc.sh set-inner --mood` as a silent no-op. It is not. The call site passes
> `current_mood=args.mood` correctly (`npc_manager.py:1136`) and a clean test
> confirms the field persists. The original observation read the key `mood` rather
> than `current_mood`, and the first re-test ran against an NPC that had never been
> created (`create` takes three positional args; `add` is not a subcommand).

## Gap 1 — Declared signature systems cannot be executed

Scene context prints, verbatim:

> `--- YOUR WORLD'S SIGNATURE SYSTEMS (executable — ROLL these, do not just narrate them) ---`
> `Resolve with lib/game_core primitives (named_track / price_roll / reaction_roll / guarded_payoff).`

There is no command that does this. `lib/game_core.py` has no `main()` and no
argparse — its `__main__` block (line 528) is the self-check assertion suite. No
wrapper in `tools/` invokes `price_roll`, `reaction_roll` or `guarded_payoff`; the
only references anywhere are `book_bible.py` (writing declarations),
`world_kit.py` (reading them) and `session_manager.py` (rendering them).

So the GM is instructed every beat to roll systems that can only be rolled by
hand-writing Python. In the-slow-heart, **Diablerie is a `price_roll`** — the
campaign's central irreversible act has no way to be resolved.

## Gap 2 — resource-axis progression has no tool path

`WorldKit.advance_progression()` (`world_kit.py:200`) and `level()` (`:203`)
exist and are correct. Nothing calls them.

`PlayerManager.award_xp()` (`player_manager.py:238`) is hardcoded to the
XP-threshold path: it reads `_xp_view`, compares against `_xp_thresholds`, and walks
`level`. A campaign declaring `{"model": "resource-axis", "resource": "years"}` has
no way to add to that resource, and therefore no way to change tier.

the-slow-heart advanced on waking years when this gap was found; it has since
moved to a `milestone` progression, so that campaign no longer illustrates the
gap. The gap itself is still real — the DCC fixture (`tests/fixtures/world-state`)
declares a genuine resource-axis kit (`resource: "viewers"`), and as shipped it
had no way to advance at all.

## Bug 3 — Tool layer dies on non-ASCII output under Windows

`bash tools/gm-session.sh context` aborted with `UnicodeEncodeError: 'charmap'
codec can't encode characters in position 9509-9512` before printing a line,
because Windows consoles default to cp1252 and campaign content contains em-dashes,
curly quotes and non-ASCII names.

This blocks play entirely on Windows. A fix is already applied in the working tree
(`export PYTHONIOENCODING=utf-8` in `tools/common.sh`) but is untested and
uncommitted.

## Robustness 4 — `play_pack.room` silently poisons the journal when it holds prose

Not strictly an engine bug: the play pack spec documents
`"room": "<one street / room / deck>"`, a short name. When a long descriptive
string is supplied instead, `apply_stage` uses it verbatim as both a **location key**
(`play_pack.py:272`) and every present NPC's **location tag** (`:289`).

`entity_manager.npcs_present` matches location by case-insensitive **exact
equality**, deliberately ("substring matching is search, not presence"). So the
staged NPCs are present only at a location whose name is a paragraph, and vanish
from NPC VOICES the moment the player moves anywhere a human would type.

Observed in this build: five location keys of 33–178 characters, and three NPCs
tagged with a 178-character paragraph. Repaired by hand.

The failure is silent, and the corrupted data is tedious to unpick after the fact.
A length guard with a derived short name is cheap insurance.

## Requirements

1. A tool-layer command that executes any declared signature system through its
   `game_core` primitive, using the config stored in `ruleset.json`.
2. A tool-layer command that advances a resource-axis progression resource and
   reports tier changes, routed through `WorldKit`.
3. The tool layer must not die on non-ASCII output on any platform.
4. `apply_stage` must derive a short, matchable location name when `room` is prose.

## Non-goals

- **Auto-sourcing `named_track` current values.** Storage for world-level tracks is
  the separate world-tracks plan. Until it lands, the roll command takes `--current`
  explicitly. Character-bound tracks (the `blood` vital) already persist.
- **Reworking `award_xp`.** The xp-levels path works; this adds a sibling verb rather
  than unifying them.
