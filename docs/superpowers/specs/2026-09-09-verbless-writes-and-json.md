# Verbless Writes and the `--json` Contract — Spec

**Date:** 2026-09-09
**Found by:** probing the live campaign's tools to answer "is it playable", and
corrupting the campaign by doing so.

## What actually happened

Three commands were run against the live campaign to check whether `--json` was
supported:

```
bash tools/gm-note.sh list --json
bash tools/gm-time.sh list --json
```

The first recorded a permanent world fact whose text was `--json`, filed under a
category named `list`. The second set the campaign's date to `--json` and its time
of day to `list`, then advanced every `advance_on: time` threat clock — moving a
narrative countdown two segments closer to firing. Neither printed an error.
Neither exited non-zero. Both reported `[SUCCESS]`.

The damage was repaired from an autosave, byte-exact. The defect is not repaired.

## The root cause is not missing `--json`

That was the symptom. The cause is that **`gm-note.sh` and `gm-time.sh` take no
verb.** Every other tool in the layer dispatches on a subcommand — `gm-clock.sh
add`, `gm-faction.sh standing`, `gm-know.sh stance`. These two do not:

```
gm-note.sh <category> <fact>
gm-time.sh <time_of_day> <date> [--ticks N] [--duration "<text>"]
```

The first positional *is data*. So there is no malformed invocation — every string
is a valid category, and every string is a valid time of day. `--json` was not
rejected because there was nothing to reject it against. A typo, a shell glob that
expanded unexpectedly, a flag intended for a different tool, a variable that came
back empty: each is silently accepted and written to permanent state.

Both tools mutate on every invocation. There is no read-only path through either.
That combination — no verb, always writes — is the whole defect.

## The `--json` contract is documented and false

This is not merely a CLAUDE.md sentence. `docs/conventions/tool-wrapper-contract.md`
makes it a documented convention with a fixed wiring pattern — `wants_json()` to
detect, `strip_json_flag()` before argparse, `emit()` / `emit_error()` to output —
and `CLAUDE.md` states it as fact in the State Persistence section: **"All tools
take `--json` for structured returns."**

Five managers with a CLI do not, and they fail in three different ways:

| Tool | `--json` behaviour |
|---|---|
| `gm-plot.sh` | argparse rejects it: `unrecognized arguments: --json`, exit 2 — loud and safe |
| `gm-location.sh` | ignored; prints human text and exits 0 |
| `gm-campaign.sh` | ignored; prints human text and exits 0 |
| `gm-note.sh` | **consumed as the fact's text and written to `facts.json`** |
| `gm-time.sh` | **consumed as the date, written to the overview, and ticks every time-clock** |

`lib/entity_manager.py` also lacks `cli_output`, but it is a base class with no
`main()` and no wrapper — it is not part of this and needs no change.

The rows differ in severity but share one cause: a documented interface that five
tools do not implement, and that two of them silently reinterpret as data.

**The convention doc also overstates its own enforcement.** It says
`tests/test_json_wrappers_*.py` covers "player, npc, session, consequence". Only
`tests/test_json_wrappers_onboard.py` exists — none of the four named files does.
Envelope assertions do live in ten other test files (`test_faction_manager.py`,
`test_knowledge_manager.py`, `test_world_tracks.py` and others), so the contract is
better tested than the doc's own sentence suggests, just not where it claims. The
doc's "Enforcement point" section needs correcting alongside this work; a
convention that misstates where it is enforced invites exactly the gap this spec
exists to close.

## A second defect in the same file

`tools/gm-time.sh` ends:

```bash
bash "$TOOLS_DIR/gm-consequence.sh" tick
exit 0
```

The `exit 0` is unconditional, so a failed consequence tick is reported as
success. Every earlier step in that script checks `$?` and propagates; the last one
discards it. This is the same shape as the wrapper defect an earlier plan shipped —
a failure that exits 0 and therefore never surfaces.

## Requirements

1. **A data position never accepts a value beginning with `-`.** In `gm-note.sh`
   and `gm-time.sh`, an argument in a positional data slot that starts with a
   hyphen is refused with a message naming the argument, and a non-zero exit. A
   category, a fact, a time of day and a date never legitimately begin with a
   hyphen; a value that does is a mistake every time. This is the requirement that
   would have prevented the corruption.
2. **`--json` is honoured or refused, never absorbed.** Each of the five tools
   either returns the `cli_output` envelope under `--json`, or refuses the flag
   with a non-zero exit. No tool may treat it as data.
3. **`gm-plot.sh`, `gm-location.sh` and `gm-campaign.sh` gain real `--json`
   support** through the existing `lib/cli_output.py` helpers — `wants_json()`,
   `strip_json_flag()`, `emit()`, `emit_error()` — matching how
   `faction_manager.py` and `knowledge_manager.py` already do it. Note the trap the
   convention doc names: a manager whose logic `print()`s human text must suppress
   that in JSON mode or the envelope arrives preceded by garbage.
   `note_manager` and `time_manager` both print `[SUCCESS]` lines from inside their
   logic, so they need the `contextlib.redirect_stdout` treatment
   `lib/consequence_manager.py:362-367` already uses.
4. **`gm-note.sh` and `gm-time.sh` gain `--json` too**, subject to requirement 1:
   the flag is stripped before the positional slots are read, so it can never
   occupy one.
5. **`tools/gm-time.sh` propagates the consequence tick's exit status** instead of
   `exit 0`.
6. **`CLAUDE.md`'s claim becomes true**, and
   `docs/conventions/tool-wrapper-contract.md`'s "Enforcement point" section is
   corrected to name the test files that actually exist. Requirements 3 and 4 make
   the CLAUDE.md sentence true, so it stands and the tools change; the convention
   doc's claim is false today and must be fixed by editing the doc.
7. **Every verb of every changed tool gets a wrapper-level subprocess test**
   driving the `.sh` through `bash`, not only the Python entry point. A previous
   plan shipped a verb that printed usage and exited 0 through three review gates
   because only the Python side was tested.

## Explicitly required tests

The corruption must be reproduced as a red test before it is fixed:

- `gm-note.sh list --json` writes nothing to `facts.json` and exits non-zero.
- `gm-time.sh list --json` leaves `current_date`, `time_of_day` and every threat
  clock unchanged, and exits non-zero.
- A category or time-of-day beginning with `-` is refused even without `--json`.
- A legitimate two-argument call to each still works unchanged.
- `gm-time.sh` returns non-zero when the consequence tick fails.

## Non-goals

- **Giving `gm-note.sh` and `gm-time.sh` real subcommands.** It would be the
  cleaner design, and it is a breaking change to all nine call sites: `CLAUDE.md`,
  four `.claude/commands/*.md` (`gm`, `help`, `import`, `world-check`),
  `.claude/agents/world-builder.md`, `.claude/skills/gm-craft/SKILL.md`, and two
  files under `docs/conventions/` (`persist-before-narrate.md`,
  `tool-wrapper-contract.md`). The guard in requirement 1 closes
  the hole without a migration. Recorded here so the trade-off is visible rather
  than forgotten.
- **`lib/entity_manager.py`.** No CLI, no wrapper, nothing to fix.
- **Auditing every other tool's flag handling.** This spec covers the five that
  fail the documented contract. A broader audit is its own work.
- **Making the tools read-only in any mode.** `gm-note.sh` and `gm-time.sh` are
  write tools; the fix is refusing malformed input, not adding a dry run.

## Acceptance

Every requirement is exercised through the bash wrapper as a subprocess, against a
`GM_WORLD_STATE_BASE` fixture world — never the live campaign. The suite baseline
is 819 passing / 31 failing, run as
`uv run python -m pytest -q --continue-on-collection-errors`; the failing set must
be byte-identical afterwards.

A final check that is not a unit test: after the change, running each of the five
tools with `--json` against a throwaway campaign must leave that campaign's state
files byte-identical unless the command was a legitimate write.
