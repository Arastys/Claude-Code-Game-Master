# Untouched-Surface Audit — Findings and Classification

**Date:** 2026-09-10
**Found by:** three parallel read-only audits of the 123 code files no recent work had touched, after a session's bug-finding rate raised the question of whether the work was causing the damage.

## It was not causing the damage

Measured rather than assumed. A worktree at `dea9931`, the commit the session started from:

| | `dea9931` | `29a1752` |
|---|---|---|
| passing | 564 | 854 |
| failing | 50 | 31 |
| test files | 77 | 91 |

**New persistent failures introduced: zero.** Every one of today's 31 failures was already failing at the starting commit, and 19 pre-existing ones were fixed along the way. Every defect below reproduces on the untouched original.

The reason the count kept climbing is coverage, not breakage. Each area where defects were found had **no tests at all** at session start: statusline 0, the `--json` contract 0, kit-driven rendering 0. `tools/gm-statusline.sh` ran after every assistant message for the repo's entire life without one test written against it.

## The systemic finding

**This repo's documentation describes a more capable and more coherent system than exists.** Not in one place — as a pattern:

- `CLAUDE.md`: "All tools take `--json` for structured returns." False for most verbs of most tools.
- `docs/conventions/tool-wrapper-contract.md`: named four enforcement test files, none of which was ever written (corrected 2026-09-10).
- `.claude/commands/enhance.md`: instructs `gm-enhance.sh search`, a verb that does not exist.
- `.claude/commands/world-check.md`: a readiness checklist that contradicts `CLAUDE.md`'s anti-gazetteer mandate, so a correct one-stage build is reported broken.
- `lib/schemas.py`: rejects the output of `lib/location_manager.py`, the only thing that writes locations.
- Three files hold three different, disagreeing vocabularies for one NPC `attitude` field.

That class of defect misleads an **agent** rather than crashing a program, which is why it accumulated invisibly. It is the reason for a second plan alongside the correctness one: a repo that misdescribes itself makes every future task more expensive.

## Verified findings — reproduced directly

These were each run and their output recorded.

### V1 (Critical) — `lib/dice.py:45-47,101` prints a modifier it does not apply

`simple_pattern.match()` is not `fullmatch()`, so it accepts a prefix and discards the tail; `format_roll_result` echoes the **original** notation. The output claims arithmetic the total does not contain.

```
"1d20 + 5"  →  🎲 1d20 + 5: [20] = 20        the +5 silently dropped
"1d6+2d8"   →  🎲 1d6+2d8: [2] +2 = 4        parsed as 1d6+2; the d8 vanished
```

`CLAUDE.md` instructs `uv run python lib/dice.py "1d20+<total>"` and states "the dice are why the world feels real". A space anywhere in the notation makes the roll wrong while looking right. Same hole in `advantage_pattern` and `disadvantage_pattern`.

Separately: invoked directly as `CLAUDE.md` describes, without `tools/common.sh` exporting `PYTHONIOENCODING=utf-8`, the 🎲 in the output raises `UnicodeEncodeError` on a cp1252 console and no roll is printed at all.

### V2 (Critical) — `lib/consequence_manager.py:251-267,283` rollback destroys state and reports success

`tick()` writes `data['_snapshot']` and calls `save_json` **only** inside `if expired or fired:`. A tick that fires nothing therefore leaves the previous beat's snapshot in place, and a later `rollback_last()` restores it — discarding everything added since.

```
tick 1 fires          → snapshot written (state: 1 consequence)
add two more          → 3 active
tick 2 fires nothing  → snapshot NOT refreshed, nothing saved
rollback              → [SUCCESS] Rolled back the last reactive beat
active after          → 1   ['The bell tolls']      ← two consequences destroyed
```

Reachable through `bash tools/gm-consequence.sh rollback`.

### V3 (Critical) — `lib/npc_manager.py:20-34` persists a 5e sheet into a kit that declares none

`PARTY_MEMBER_DEFAULTS` has no `is_dnd5e` gate. On a `custom` kit declaring `vitals: ["hp","blood"]` and no `ac`/`race`/`class`:

```
$ gm-npc.sh promote "Grimjaw"
character_sheet: {race:"Unknown", class:"Commoner", ac:10,
                  attack_bonus:2, damage:"1d6", xp:0, ...}
```

This is the eleventh instance of the invented-5e-field family, ten of which were fixed in earlier plans. It reaches further than the others: `gm-player.sh become` copies that sheet into `character.json`, so the **Death Protocol hand-off** produces a "Level 1 Unknown Commoner, AC 10" PC in a world with none of those concepts.

### V4 (Important) — `lib/validators.py:36` locks the runtime out of names it allowed in

`validate_name`'s `^[a-zA-Z0-9\s\-']+$` rejects any non-ASCII letter and any period. `NPCManager.create_batch` — the import path — does **not** call it, so extraction creates such NPCs freely; every runtime verb calls it first and refuses.

```
Eurgain, Cadwal, Nant Ddu, Y Bleiddiaid    → accepted
Bran ap Llŷr, Père Anselme, St. Cuthbert   → REJECTED
```

The live campaign's current names all pass, but it is a Welsh Bronze Age setting where `Llŷr` and `Ffraid` are ordinary. `location_manager.py` uses the same validator for place names.

### V5 (Critical) — `tools/gm-session.sh:190` crashes and exits 0

The `move` branch forwards its leftover arguments — including a trailing `--json` — to `gm-enhance.sh scene "$@"`, whose manager has no flag-stripping. The crash is swallowed: the result is captured into `CONTEXT=$(...)` and only tested with `[ -n "$CONTEXT" ]`.

```
$ gm-session.sh move "Nant Ddu" --json
entity_enhancer.py: error: unrecognized arguments: --json
$ echo $?
0
```

Gated on `[ -d "$CAMPAIGN_DIR/vectors" ]`, which the live campaign satisfies.

### V6 (Critical) — `tools/gm-search.sh:80-85` discards the query

The argument loop has no case for `--json`, so it falls to the catch-all and is assigned **as the query** when the query slot is still empty.

```
$ gm-search.sh --json "dragon"
{"ok": false, "error": "no query provided", "code": null}
```

The same catch-all silently drops a second bare positional, which is how `gm-search.sh --rag-only "<query>" 50` runs at the default of 4 results. That form appears 13 times across `.claude/commands/import.md` and the four `extractor-*` agents.

### V7 (Important) — envelope purity is broken in several untouched wrappers

`gm-session.sh` prints a banner before the envelope on `start`, `end`, `status`, `move`, `save`, `restore`, `list-saves` and `history`; `gm-npc.sh status` appends a RAG report **after** it; `gm-consequence.sh` drops the flag on 5 of 7 verbs; `gm-condition.sh` on all 3; `gm-overview.sh` never recognises it.

```
$ gm-session.sh status --json
Campaign Status
===============
{"ok": true, ...}      ← json.loads fails
```

### V8 (Medium) — `.claude/commands/enhance.md:39` instructs a verb that does not exist

`gm-enhance.sh search` → `Unknown command: search`, exit 1. The tool's own usage text names the correct command (`gm-search.sh --rag-only`).

## Relayed findings — reported by an audit, not independently reproduced

Recorded with that status explicitly, because the difference matters.

- **`lib/schemas.py`** rejects the engine's own output: `LocationManager.add` always persists `description: ''`, which `validate_location` requires, so every engine-created location is invalid (20/20 in the fixture). Its `VALID_ITEM_TYPES` is a closed 61-entry 5e whitelist. It rejects a scalar `hp` — the exact case `_read_vital` exists to support — and requires `level` even on a resource-axis kit whose level is derived.
- **Three disagreeing attitude vocabularies** across `validators.py`, `schemas.py` and `extraction_schemas.py`: `curious`/`fearful`/`respectful` valid in one and invalid in another; `ally`/`enemy` the reverse.
- **`lib/npc_manager.py:388-411`** reads through `entity_aliases` but writes by exact match, so `gm-npc.sh mood "Donut"` (key `"Princess Donut"`) exits 1 with **no output at all**.
- **`lib/npc_manager.py:975-982`** — `stale`, `checked` and `unify-tags` are implemented but absent from `tools/gm-npc.sh`, so the whole canon-drift feature and the `tag_unify` migration are unreachable through the mandated door. `stale`'s own output tells the GM to run a verb the wrapper lacks.
- **`lib/threat_clocks.py:185,194`** — `advance` on a misspelled clock name returns `null` at exit 0; `choose --json` leaks `[SUCCESS] Added consequence …` ahead of its envelope.
- **`lib/rag/quote_extractor.py:154`** — `read_text()` with no encoding on a file `save_json` writes as UTF-8 with `ensure_ascii=False`. A curly quote in NPC context kills Pass 2 of import, and the caller reports success.
- **`lib/rag/vector_store.py:37`** — the constructor `mkdir`s `vectors/` on a *read*, so a bookless campaign permanently claims a vector store and every `[ -d vectors ]` gate afterwards answers yes.
- **`lib/combat_manager.py:43,115`** — defaults and renders `ac: 10` unconditionally, directly under a docstring saying "no 5e assumptions".
- **`.claude/commands/world-check.md:258-296`** — a readiness checklist requiring 3+ locations, 4+ NPCs and 2+ consequences, which reports a correct `/new-game` one-stage build as broken and pushes a model toward the gazetteer `CLAUDE.md` forbids.
- **`.claude/agents/gear-master.md` and `loot-dropper.md`** carry no kit gating at all, unlike their `monster-manual`/`rules-master` siblings; `loot-dropper` self-describes as "D&D 5e" with hardcoded rarity tiers and gold pieces.
- **Dead modules:** `lib/world.py` (no importer; its documented `World("conan")` usage calls `set_active`, rewriting the global active-campaign pointer from what reads as a scoped constructor), `lib/logging_config.py` (no importer), and seven 5e-vocabulary functions in `lib/validators.py` with no callers.
- **Five wrappers are never driven as a subprocess by any test** — `gm-combat.sh`, `gm-lore.sh`, `gm-migrate-campaigns.sh`, `gm-playpack.sh`, `gm-system.sh`. That is the only test shape that catches the exit-0 class.
- **`tools/gm-migrate-campaigns.sh`** never sources `common.sh` and hardcodes `$PROJECT_ROOT/world-state`, so it cannot be redirected — untestable by construction, on a script that copies campaign data.

## Classification, and what follows

Two plans argue from this spec, split on a single question: **does it corrupt state or produce wrong numbers during play, or does it mislead whoever reads it?**

**`2026-09-10-play-correctness.md`** takes V1, V2, V3 and V4 — the four that damage a campaign or lie about a die roll. Small, independent, each with a reproduction that becomes a regression test.

**`2026-09-10-repo-tells-the-truth.md`** takes the systemic finding: the false claims, the contradictory vocabularies, the validator that rejects its own engine's output, the dead modules, and the untested wrappers. None of it crashes anything. All of it makes the next task more expensive than it should be.

## Non-goals for both plans

- **Implementing `--json` everywhere.** ~20 tools × many verbs. Correcting the claim and publishing an accurate per-tool table is cheaper, more honest, and does not risk the bare-string-capture breakage that a blanket rollout already caused once.
- **Rewriting `lib/schemas.py` as a kit-aware validator.** The fix here is to stop it rejecting valid engine output; a genuinely kit-driven validator is its own design problem.
- **The 31 environmental test failures.** 26 need Windows Developer Mode for `os.symlink`; 5 are path-shape assertions. Neither is code.
- **OKF stamps.** `okf.mjs` is not installed and `/plugin` is unavailable over Remote Control, so docs ship unstamped and index entries are hand-added.
