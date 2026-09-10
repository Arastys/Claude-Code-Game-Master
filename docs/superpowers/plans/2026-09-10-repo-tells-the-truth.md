# The Repo Tells The Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repo describe itself accurately, and make the untestable testable — so the next task is not spent discovering that the map is wrong.

**Architecture:** Five tasks, ordered cheapest-and-safest first. Delete what is dead; give shared vocabularies one home; stop the validator rejecting its own engine's output; close the exit-0 blind spot with a subprocess test per untested wrapper; then correct every false instruction and publish an accurate capability table. No new subsystems.

**Tech Stack:** Python 3 (stdlib), bash, pytest, Markdown. Run everything with `uv run python`, never bare `python`.

**Spec:** `docs/superpowers/specs/2026-09-10-untouched-surface-audit.md` — the systemic finding and the relayed findings.

## Standing authorisation for this plan

The user has explicitly authorised this plan to **override the project's own restrictions and conventions on file edits and style where doing so removes confusion**. That licence is used deliberately in Tasks 1, 3 and 5: deleting modules, changing a shared validator's contract, and rewriting sections of `CLAUDE.md` and the `.claude/` instruction files — all of which a narrower reading would have left alone.

**One project rule is deliberately NOT overridden: never hand-type an OKF stamp.** `okf.mjs` is not installed and `/plugin` is unavailable over Remote Control, so every doc this plan touches ships unstamped and index entries are hand-added. A stamp asserts that someone read the cited code; fabricating one manufactures false provenance, which is the exact class of defect this plan exists to remove. Unstamped and honest beats stamped and lying. Record the drift; do not paper it.

## Global Constraints

- **A claim in a doc is a claim about code.** Before writing that a tool does something, run it. Before deleting a module as dead, prove nothing imports it. Every finding this plan acts on has a reproduction in the spec; every change should leave one behind.
- **The engine holds no game's concepts.** A World Kit declares each world's vitals, traits and progression; `lib/world_kit.py` is the single reader. The one legitimate exception is a genuinely `dnd5e` kit, gated the way `features/character-creation/save_character.py:157-166` gates `DND_SHEET_DEFAULTS`.
- **Human-visible output must not change** unless a task says so. This is a live tool layer.
- **Tests never touch the live campaign.** Always `GM_WORLD_STATE_BASE` against a fixture under `tmp_path`. `world-state/campaigns/the-slow-heart/` is real user data; probing it with speculative commands caused a corruption incident on this repo.
- **All file writes use `encoding="utf-8"`** — Windows here, where `open()` defaults to cp1252.
- **Never run a filesystem-wide search** (`find /`, `find ~`). Two agents on this repo left one running for hours, one burning 2h21m of CPU. Use `grep`, `rg`, or a targeted path.
- **Run the suite as** `uv run python -m pytest -q --continue-on-collection-errors`. Baseline **854 passing / 31 failing** (26 need Windows Developer Mode for `os.symlink`; 5 are path-shape assertions); the failing set must be byte-identical afterwards. This pytest prints **no tally line** — count `^FAILED ` lines. Never gate a commit behind a piped test run. See `docs/gotchas/running-the-suite.md`.

---

## File Structure

| File | Change |
|---|---|
| `lib/world.py`, `lib/logging_config.py` | Delete — no importer, and `world.py`'s documented usage silently rewrites the global campaign pointer. |
| `lib/validators.py` | Delete seven 5e-vocabulary validators and their `main()` CLI wiring; import the shared attitude vocabulary. |
| `lib/vocabularies.py` (create) | One home for the vocabularies three files currently disagree about. |
| `lib/schemas.py` | Import the shared vocabulary; stop rejecting valid engine output. |
| `lib/extraction_schemas.py` | Import the shared vocabulary; drop the legacy `location_tags` instruction. |
| `tools/gm-migrate-campaigns.sh` | Honour `GM_WORLD_STATE_BASE` so it can be tested at all. |
| `tools/gm-search.sh` | Refuse a stray positional instead of silently discarding it. |
| `tests/test_wrapper_smoke.py` (create) | A subprocess test for each of the five wrappers that have none. |
| `tests/test_shared_vocabularies.py` (create) | The three files agree, and cannot silently diverge again. |
| `CLAUDE.md` | Correct the `--json` claim and the specialist-agents line. |
| `docs/conventions/tool-json-support.md` (create) | The accurate per-tool capability table. |
| `.claude/commands/*.md`, `.claude/agents/*.md` | Correct every instruction that names a verb, flag, file or agent that does not exist. |

---

### Task 1: Delete what is dead

**Files:**
- Delete: `lib/world.py`, `lib/logging_config.py`
- Modify: `lib/validators.py` — remove seven 5e-vocabulary validators **and their CLI wiring**
- Modify: `docs/conventions/tool-wrapper-contract.md` — one stale sentence naming `validate_dice`
- Test: `tests/test_no_dead_modules.py` (create)

**Interfaces:** none produced.

`lib/world.py` is the dangerous one. It has no importer, no wrapper and no test, but it reads like the natural API — and its own documented usage, `World("conan")`, calls `set_active`, **rewriting the global `active-campaign.txt`** from what looks like a scoped read-only constructor. An agent that finds it and follows its docstring switches the user's campaign as a side effect of constructing an object.

- [ ] **Step 1: Prove they are dead**

Run and paste the output into your report:

```bash
grep -rn "import world\b\|from world import\|world\.World\|World(" --include=*.py lib/ tools/ features/ tests/ | grep -v "world_kit\|world_bible\|world_tick\|world_tracks\|book_bible"
grep -rn "logging_config" --include=*.py --include=*.sh --include=*.md . | grep -v docs/superpowers
grep -rn "validate_damage_type\|validate_skill\|validate_alignment\|validate_condition\|validate_ability\|validate_dice\|validate_time_of_day" --include=*.py --include=*.sh lib/ tools/ features/ tests/
```

**If any of the first two returns a live caller, stop and report it** rather than deleting.

I ran all three myself when writing this plan. Results, so you know what to expect and can tell a surprise from a confirmation:

- `lib/world.py` — three hits, **all inside its own docstrings** (lines 33, 36, 236). Genuinely no importer.
- `lib/logging_config.py` — one hit, in `.venv/` (an unrelated `opentelemetry` function). Genuinely unreferenced in the repo.
- The seven validators — **seven hits, and they are real**: a dispatch map in `validators.py`'s own `main()`. See Step 3; this is why the deletion is three parts, not one.

- [ ] **Step 2: Write the test that keeps them dead**

Create `tests/test_no_dead_modules.py`:

```python
"""Two modules and seven functions were deleted as unreachable.

lib/world.py was the reason this is a test rather than just a deletion: it had no
importer, but it read like the natural API, and its documented usage — World("conan")
— called set_active, rewriting the global active-campaign pointer as a side effect
of constructing what looks like a scoped reader. Anything that reintroduces that
shape should have to argue for it.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_the_deleted_modules_stay_deleted():
    assert not (REPO_ROOT / "lib" / "world.py").exists()
    assert not (REPO_ROOT / "lib" / "logging_config.py").exists()


def test_no_module_grew_a_campaign_switching_constructor():
    """The specific hazard: a constructor that rewrites active-campaign.txt."""
    import re
    for path in (REPO_ROOT / "lib").glob("*.py"):
        src = path.read_text(encoding="utf-8")
        init = re.search(r"def __init__\(self[^)]*\):(.*?)(?=\n    def |\Z)", src, re.S)
        if init and "set_active" in init.group(1):
            raise AssertionError(f"{path.name}'s __init__ calls set_active")
```

- [ ] **Step 3: Delete**

```bash
git rm lib/world.py lib/logging_config.py
```

Then remove `validate_damage_type`, `validate_skill`, `validate_alignment`, `validate_condition`, `validate_ability`, `validate_dice` and `validate_time_of_day` from `lib/validators.py`.

**They are not as callerless as the spec says, and deleting the functions alone breaks the file.** All seven are wired into `validators.py`'s own `main()` — an `argparse` `choices=[...]` list and a `validators_map` dispatch dict at roughly lines 275-300. Removing a function without its two entries leaves a `choices` value that maps to nothing. Delete all three parts of each: the method, its `choices` entry, and its `validators_map` entry. I verified there is **no consumer of that CLI** anywhere — no doc, skill, wrapper or test drives `python lib/validators.py <type> <value>` — so the CLI surface can shrink safely.

**One doc goes stale and must be updated in the same commit.** `docs/conventions/tool-wrapper-contract.md:101` describes `lib/validators.py` as holding "the shared input guards (names, attitudes, dice notation)". `validate_dice` is one of the seven. Correct that sentence.

Add a short note at the top of the class recording that seven 5e-vocabulary validators and their CLI wiring were removed as unreachable, so nobody re-adds them believing they were an oversight.

**Two more functions are also callerless, and are deliberately left alone:** `validate_quest_priority` and `validate_plot_status` both have zero library callers (verified). They are engine concepts rather than 5e vocabulary, so the governing-rule argument that justifies deleting the seven does not apply to them, and removing them would be tidying rather than removing confusion. Leave them; note them in your report. (`validate_plot_type`, by contrast, has 11 live callers.)

Do **not** touch `validate_name` or `validate_attitude` in this task — Task 2 changes the latter, and `validate_name` belongs to the play-correctness plan.

- [ ] **Step 4: Run the suite, then commit**

```bash
git add -A lib/validators.py tests/test_no_dead_modules.py
git commit -m "lib: delete two dead modules and seven callerless 5e validators"
```

---

### Task 2: One home for the vocabularies three files disagree about

**Files:**
- Create: `lib/vocabularies.py`
- Modify: `lib/validators.py`, `lib/schemas.py`, `lib/extraction_schemas.py`
- Test: `tests/test_shared_vocabularies.py` (create)

**Interfaces:**
- Produces: `lib/vocabularies.py` exporting `ATTITUDES: tuple[str, ...]`.

One field, `attitude`, has three definitions that disagree in both directions: `curious`, `fearful` and `respectful` are valid in `validators.py` and invalid in `schemas.py`; `ally` and `enemy` are the reverse; `extraction_schemas.py` holds a third, five-value list. So an NPC the extractor creates can fail the validator, and an attitude the input guard accepts can fail the world check.

- [ ] **Step 1: Read all three and write down the union**

```bash
grep -n "valid_attitudes\|VALID_ATTITUDES\|attitude" lib/validators.py lib/schemas.py lib/extraction_schemas.py
```

Paste all three lists into your report before changing anything. The canonical set is **the union**, not any one file's list — every value in any of the three is one some part of the system already produces or accepts, so narrowing would break a live path.

- [ ] **Step 2: Write the failing test**

Create `tests/test_shared_vocabularies.py`:

```python
"""One field, one vocabulary.

`attitude` had three disagreeing definitions: curious/fearful/respectful valid in
validators.py and invalid in schemas.py, ally/enemy the reverse, and a third
five-value list in extraction_schemas.py. So an NPC the extractor created could
fail the validator, and an attitude the input guard accepted could fail
/world-check.
"""

from lib.vocabularies import ATTITUDES


def test_every_consumer_uses_the_shared_vocabulary():
    """Not "the lists happen to match" — they must be the same object, so they
    cannot silently diverge again."""
    from lib import validators, schemas, extraction_schemas
    assert set(schemas.VALID_ATTITUDES) == set(ATTITUDES)
    for value in ATTITUDES:
        ok, _ = validators.Validators.validate_attitude(value)
        assert ok, f"validators rejects the shared value {value!r}"
        ok2, _ = schemas.validate_npc({"description": "x", "attitude": value})
        assert ok2 or "attitude" not in str(ok2), f"schemas rejects {value!r}"


def test_the_previously_disagreeing_values_are_all_accepted():
    for value in ("curious", "fearful", "respectful", "ally", "enemy",
                  "friendly", "neutral", "hostile"):
        assert value in ATTITUDES, f"{value} was valid somewhere and is now lost"
```

Adapt the `validate_npc` call to that function's real signature — read it first.

- [ ] **Step 3: Create the shared home**

Create `lib/vocabularies.py`:

```python
#!/usr/bin/env python3
"""Vocabularies shared by more than one consumer.

`attitude` previously had three definitions — an input guard in validators.py, a
world-state validator in schemas.py, and an extraction contract in
extraction_schemas.py — which disagreed in both directions. An NPC the extractor
created could fail the validator; an attitude the guard accepted could fail
/world-check. The set below is the union of all three, because every value in any
of them is one some part of the system already produces.

A vocabulary that more than one module needs lives here, imported, never copied.
"""

# The union of the three former lists. Narrowing this breaks a live path.
ATTITUDES = (
    'friendly', 'neutral', 'hostile', 'suspicious', 'helpful', 'indifferent',
    'fearful', 'respectful', 'dismissive', 'curious', 'ally', 'enemy',
)
```

Include the actual union you recorded in Step 1 — the tuple above is this plan's best reading of the three lists and **must be reconciled against what you actually found.** If a value exists that this tuple omits, add it and say so.

- [ ] **Step 4: Point all three at it**

In each of `lib/validators.py`, `lib/schemas.py` and `lib/extraction_schemas.py`, replace the local list with an import from `lib.vocabularies`. Keep each file's own error message and validation shape — only the vocabulary moves.

`extraction_schemas.py` describes a contract for extraction agents in prose as well as code; update the prose to match, and note in your report whether the schema is embedded in an agent-facing string that also needs editing.

- [ ] **Step 5: Run the suite, then commit**

```bash
git add lib/vocabularies.py lib/validators.py lib/schemas.py lib/extraction_schemas.py tests/test_shared_vocabularies.py
git commit -m "vocabularies: one attitude list, imported by all three consumers"
```

---

### Task 3: The validator must not reject its own engine's output

**Files:**
- Modify: `lib/schemas.py`
- Test: `tests/test_schemas_accepts_engine_output.py` (create)

**Interfaces:** none produced.

`/world-check` runs `uv run python lib/schemas.py`. Against the shipped DCC fixture it reports 20 invalid locations out of 20 and 58 invalid items, because:

- `validate_location` requires `description`, and `LocationManager.add` — the only writer — always persists `description: ''`.
- `VALID_ITEM_TYPES` is a closed 61-entry 5e weapon/armour whitelist, so `crysknife`, `currency` and `explosive` are all "invalid".
- `validate_character` rejects a scalar `hp`, the exact case `PlayerManager._read_vital` exists to support.
- `validate_character` requires `level` even on a resource-axis kit whose level is derived.

A validator that reports a healthy world as broken trains its reader to ignore it, which is worse than having none.

- [ ] **Step 1: Reproduce the four**

Run against the shipped fixture and paste the output:

```bash
uv run python lib/schemas.py tests/fixtures/world-state/campaigns/dungeon-crawler-carl 2>&1 | head -30
uv run python -c "
import sys; sys.path.insert(0,'lib')
import schemas
print(schemas.validate_character({'name':'Kal','level':1,'hp':12}))
print(schemas.validate_character({'name':'Kal','viewers':4200000}))
print(schemas.validate_item('Crysknife', {'type':'crysknife'}))
"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_schemas_accepts_engine_output.py`, asserting that:

- a location as `LocationManager.add` actually writes it (with `description: ''`) validates;
- a character with a scalar `hp` validates;
- a character on a resource-axis kit with no `level` validates;
- an item with a type outside the 5e whitelist validates;
- **and the guards that should still fail, still fail** — a location with no name at all, a character with no name, an item that is not a dict.

Write it with the real function signatures; read them first. Include one test that runs `lib/schemas.py` against the shipped DCC fixture and asserts **zero** location errors, since that is the user-visible symptom.

- [ ] **Step 3: Loosen the four checks, and only those**

Use the standing authorisation here: this changes a shared validator's contract.

- **Location `description`**: accept an empty string. A location legitimately has no description until `describe` is called, and requiring one makes every engine-created location invalid. Require a `name` or key instead.
- **`VALID_ITEM_TYPES`**: stop treating it as a closed set. Keep it as a *known-types* list for informational use if anything reads it, and make `validate_item` accept any non-empty string type. A kit declares its own world's objects; a closed 5e list is precisely the hardcoding the engine's governing rule forbids.
- **Scalar `hp`**: accept both an `int` and a `{current, max}` dict, matching `_read_vital`'s documented contract.
- **Required `level`**: make it required only when the kit's progression model actually has levels. If `validate_character` has no kit in scope, make `level` optional rather than required — a false failure is worse than a missed one here.

Add a comment at each of the four sites naming what it used to reject and why that was wrong.

**Do not attempt a kit-aware rewrite of this validator.** The spec lists that as a non-goal: it is a design problem, not a loosening. Scope this to "stop rejecting valid engine output".

- [ ] **Step 4: Confirm `/world-check` now passes a healthy world**

Run `lib/schemas.py` against the DCC fixture again and paste the before/after counts.

- [ ] **Step 5: Run the suite, then commit**

```bash
git add lib/schemas.py tests/test_schemas_accepts_engine_output.py
git commit -m "schemas: accept what the engine actually writes"
```

---

### Task 4: Close the exit-0 blind spot

**Files:**
- Modify: `tools/gm-migrate-campaigns.sh`, `tools/gm-search.sh`
- Test: `tests/test_wrapper_smoke.py` (create)

**Interfaces:** none produced.

Five wrappers are **never driven as a subprocess by any test**: `gm-combat.sh`, `gm-lore.sh`, `gm-migrate-campaigns.sh`, `gm-playpack.sh`, `gm-system.sh`. A subprocess test is the only shape that catches the exit-0 class — a wrapper can fail, print a usage banner, exit 0, and every Python-level test stays green. That is exactly how `gm-player.sh advance` shipped through three review gates on this repo.

`gm-migrate-campaigns.sh` cannot be tested at all: it never sources `common.sh` and hardcodes `$PROJECT_ROOT/world-state`, so any test exercising it would read and write the developer's live campaign. Making it redirectable is a precondition, not scope creep — the same argument that applied to `gm-statusline.sh`.

- [ ] **Step 1: Make `gm-migrate-campaigns.sh` redirectable**

Give it the same one-line resolution every other tool uses (`tools/common.sh:48`): `WORLD_STATE_BASE="${GM_WORLD_STATE_BASE:-$PROJECT_ROOT/world-state}"`, and replace every hardcoded `$PROJECT_ROOT/world-state` with it. Read the whole script first — it prompts before a destructive copy, and that prompt must still fire.

**Do not execute this script**, even against a fixture, until Step 3's test does so deliberately with a non-interactive input. Report what you find by reading.

- [ ] **Step 2: Make `gm-search.sh` refuse a stray positional**

Its catch-all arm silently discards any second bare positional, which is why `gm-search.sh --rag-only "<query>" 50` runs at the default of 4. Change the catch-all so that a second positional is an **error**, naming both the value and the `-n` flag:

```bash
        *)
            if [ -z "$QUERY" ]; then
                QUERY="$1"
            else
                # Silently discarding this is how 13 documented call sites ran at
                # the default result count for however long they have existed.
                echo "[ERROR] Unexpected argument: $1" >&2
                echo "        Result count is set with -n <count>, not a trailing number." >&2
                exit 1
            fi
            shift
            ;;
```

Task 5 corrects the 13 call sites. Doing the tool first means those sites fail loudly in the interim rather than silently, which is the safer order.

- [ ] **Step 3: Write a smoke test for each of the five**

Create `tests/test_wrapper_smoke.py`. For each of `gm-combat.sh`, `gm-lore.sh`, `gm-playpack.sh`, `gm-system.sh` and `gm-migrate-campaigns.sh`, assert as a subprocess through `bash`:

- invoked with **no arguments**, it either does something valid or exits **non-zero** — never prints a usage banner and exits 0;
- invoked with a **nonsense verb**, it exits non-zero;
- at least one legitimate invocation succeeds against a `GM_WORLD_STATE_BASE` fixture.

Do **not** exercise `gm-migrate-campaigns.sh`'s destructive copy. Drive only its refusal paths, and feed it `</dev/null` so an interactive prompt cannot hang the suite.

If any wrapper turns out to print usage and exit 0, **that is a finding, not a test to bend around.** Report it; the fix belongs in this task.

- [ ] **Step 4: Run the suite, then commit**

```bash
git add tools/gm-migrate-campaigns.sh tools/gm-search.sh tests/test_wrapper_smoke.py
git commit -m "tools: every wrapper has a subprocess smoke test, and search refuses a stray count"
```

---

### Task 5: Correct every instruction that is false

**Files:**
- Modify: `CLAUDE.md`
- Create: `docs/conventions/tool-json-support.md`
- Modify: `.claude/commands/enhance.md`, `world-check.md`, `gm.md`, `import.md`; `.claude/agents/monster-manual.md`, `rules-master.md`, `npc-builder.md`, `world-builder.md`, `create-character.md`, `gear-master.md`, `loot-dropper.md`, and the four `extractor-*.md`
- Test: `tests/test_instructions_are_true.py` (create)

**Interfaces:** none produced.

These files are **loaded and followed by a model during play**, so a wrong command in one is not a typo — it is a bug that executes. This is where the standing authorisation matters most: several of these need rewriting, not annotating.

- [ ] **Step 1: Write the test that keeps them honest**

Create `tests/test_instructions_are_true.py`. It should mechanically check, across `.claude/**/*.md` and `CLAUDE.md`:

- every `tools/gm-*.sh` referenced exists;
- every `lib/*.py` and `features/**/*.py` path referenced exists;
- every `bash tools/gm-X.sh <verb>` names a verb that appears in that wrapper's `case` (or its usage block);
- every `.claude/agents/<name>` referenced as a spawnable agent has a definition file;
- no runnable command in a fenced block or table cell lacks the `bash tools/` prefix.

A regex sweep will produce false positives on prose. Make the test **precise about what counts as a runnable command** (a fenced block, or a table cell beginning with `bash `), and where it cannot be sure, prefer a narrower rule over a noisy one. Report the false-positive rate you tuned it to.

- [ ] **Step 2: Correct the outright-wrong references**

Each of these is verified in the spec. Fix the reference; do not invent a replacement without checking what the tool actually accepts:

- `.claude/commands/enhance.md` — `gm-enhance.sh search` does not exist. The tool's own usage names the right command: `gm-search.sh --rag-only`.
- `.claude/agents/monster-manual.md` — references `dnd_encounter.py`; the file is `dnd_encounter_v2.py`, used correctly eight other times in the same file. Also documents `--limit` default 10; the real default is 50.
- `.claude/agents/rules-master.md` — `list_rules.py --category combat`; there is no `--category` flag (only `--search`, `--limit`, `--sections`).
- `.claude/commands/import.md` — spawns `extractor-monsters`, which has no definition.
- `.claude/agents/world-builder.md` — twelve `./tools/gm-*.sh` in copy-pasteable places, and one consequence example missing its `add` verb (`gm-consequence.sh "[event]" "[timing]"` → `Unknown action`, the verbless-write class this repo has a gotcha about).
- `.claude/agents/create-character.md` — two `./tools/gm-player.sh save-json`.
- `.claude/commands/gm.md` — `gm-location.sh add "The Rusty Tankard" "A cozy tavern…"` passes a description into the `position` slot, so the tavern is created with no description. Use `add` then `describe`.
- The four `extractor-*.md` and `import.md` — thirteen `gm-search.sh --rag-only "<q>" N` calls whose trailing count is discarded. Change each to `-n N`. Task 4 made this fail loudly, so leaving one uncorrected now breaks the pipeline visibly rather than silently.

- [ ] **Step 3: Fix the two instructions that contradict the design**

Use the authorisation here — both need rewriting, not a caveat.

**`.claude/commands/world-check.md`** — its readiness checklist requires 3+ locations, 4+ NPCs, a three-tier plot structure and 2+ consequences before a world is "ready". `CLAUDE.md` mandates the opposite: "Do not scrape a gazetteer 'so it's ready'", and "`/new-game` and `/import` both stop at one stage on purpose." A model running `/world-check` after a correct lean build is told the world is broken and pushed toward exactly the bulk generation the design forbids. **Rewrite the checklist to check what the lean design actually requires** — a kit, a confirmed bible, one staged room with people in it, a voice, one clock — and to report abundance as neutral information rather than a failure.

**`.claude/commands/gm.md`** — the CHARACTER DISPLAY section unconditionally instructs presenting race, class, background, alignment, ability scores, HP/AC/speed, saves, proficient skills, features, gold and inventory. On a custom kit `gm-player.sh show` correctly returns `"Kael - Level 1 (HP: 18/18)"`, so eight of eleven fields do not exist. **Rewrite it to present what the kit declares** — the same rule the tool already follows.

- [ ] **Step 4: Give the ungated specialist agents a kit gate**

`.claude/agents/gear-master.md` and `loot-dropper.md` have no kit check anywhere; `loot-dropper` self-describes as "D&D 5e" with hardcoded rarity tiers and gold pieces. Their siblings `monster-manual.md` and `rules-master.md` both open with an explicit "check the active World Kit first" section — **copy that pattern into both**, and add the `(book-first, kit-aware)` qualifier to their entry in `CLAUDE.md`'s specialist-agents line, which currently marks only `monster-manual` and `rules-master`.

`.claude/agents/npc-builder.md` presents `gm-npc.sh promote` then `set … ac 12 / class "Fighter"` as the universal way to stat a follower. The underlying defect is fixed by the play-correctness plan's Task 4; **this file still needs its instruction corrected** to set kit-declared fields rather than 5e ones. If that plan has not landed yet, say so in your report and correct the instruction anyway.

- [ ] **Step 5: Replace the false `--json` claim with an accurate table**

`CLAUDE.md` says "All tools take `--json` for structured returns." That is false for most verbs of most tools, and the spec's non-goals rule out implementing it everywhere — ~20 tools × many verbs, and a blanket rollout already caused a bare-string-capture breakage once.

Create `docs/conventions/tool-json-support.md`: a table of every `tools/gm-*.sh`, each verb's status (**envelope** / **plain text** / **refused** / **n/a**), built by *running* each one against a fixture, not by reading. Include the `DM_JSON=1` caveat and the bare-string-capture rule that `gm-campaign.sh path`/`active` exist to demonstrate.

Then change `CLAUDE.md`'s sentence to point at it — something true and short, e.g. that many tools take `--json` and the table says which. Add the new doc to `docs/conventions/index.md` by hand.

- [ ] **Step 6: Run the suite, then commit**

Two commits, so the mechanical corrections and the design rewrites stay separable:

```bash
git add tests/test_instructions_are_true.py .claude/ && git commit -m "instructions: every referenced verb, flag, file and agent now exists"
git add CLAUDE.md docs/conventions/ && git commit -m "docs: an accurate --json table, and a readiness check that matches the lean design"
```

---

## Plan Self-Review

**Spec coverage.** Dead modules and callerless validators → Task 1. Three attitude vocabularies → Task 2. `schemas.py` rejecting engine output → Task 3. Five untested wrappers, `gm-migrate-campaigns.sh`'s anchoring, `gm-search.sh`'s swallowed positional → Task 4. Every `.claude/` instruction finding, the false `--json` claim, the world-check contradiction, the ungated agents → Task 5.

**Deliberately not covered, and why.** The remaining relayed findings are real and left for their own work: `npc_manager`'s alias-aware reads with exact-match writes (a silent exit-1 that defeats persist-before-narrate, and a genuine design question about whether writes should resolve aliases); the three verbs missing from `tools/gm-npc.sh` that make canon-drift and `tag_unify` unreachable; `threat_clocks`' `advance` on a misspelled name returning `null` at exit 0; `quote_extractor`'s unencoded read; `vector_store` creating `vectors/` on a read; `combat_manager`'s invented AC; and the envelope-purity gaps in `gm-session.sh` and `gm-npc.sh`. Each is a defect; none blocks working forwards, and a plan that tried to hold all of them would land none of them.

**Placeholders.** Task 2's `ATTITUDES` tuple and Task 3's four loosenings are stated as intent with the instruction to reconcile against what the implementer actually reads, because pasting a value I have not verified against three files is how earlier plans in this repo shipped defects. Task 5's test is specified by behaviour rather than code for the same reason — a naive regex over prose produces noise, and the tuning is a judgement the implementer must make and report.

**Type consistency.** `ATTITUDES` is a `tuple[str, ...]` imported by three modules, never copied. `validate_*` functions keep `(bool, Optional[str])`. `WORLD_STATE_BASE` is a bash string resolved identically to `common.sh:48`.

**Known risks.**
- Task 3 loosens a validator, so it will stop reporting things it used to. That is the point, but a genuine schema violation could now pass. Every loosening keeps a paired "still fails" test for exactly that reason.
- Task 4 changes `gm-search.sh` to refuse an argument it used to ignore, which will break any caller relying on the old silence — that is why Step 2 precedes Task 5's corrections, so the interim failure is loud.
- Task 5 rewrites two `.claude/` files' design intent. That is the authorisation being used, and it is the change most worth a careful review: `world-check.md` and `gm.md` are read by a model that will act on them, and a rewrite that is merely *different* rather than *truer* makes things worse.
