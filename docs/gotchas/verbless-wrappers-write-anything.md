---
type: Gotcha
title: A wrapper with no verb writes whatever it is handed
description: gm-note.sh and gm-time.sh read their first positional as data, so no invocation can be malformed — a typo, a stray flag or an unset variable went to permanent state printing [SUCCESS] and exiting 0.
sources:
  - { resource: /tools/gm-note.sh }
  - { resource: /tools/gm-time.sh }
  - { resource: /tools/common.sh }
---

# A wrapper with no verb writes whatever it is handed

Almost every tool in this layer dispatches on a subcommand — `gm-clock.sh add`,
`gm-faction.sh standing`, `gm-know.sh stance`. Two do not:

```
gm-note.sh <category> <fact>
gm-time.sh <time_of_day> <date>
```

Their first positional **is data**. So there is no such thing as a malformed
invocation: every string is a valid category, and every string is a valid time of
day. Both tools also write on every call — there is no read-only path through
either.

## What that cost

Probing a live campaign to check whether `--json` was supported:

```
$ gm-note.sh list --json
[SUCCESS] Recorded fact in list: --json          ← a permanent world fact named "--json"

$ gm-time.sh list --json
[SUCCESS] Time updated to: list, --json          ← campaign date set to "--json",
                                                   and every advance_on:time clock ticked
```

Both exited 0. The likelier version in practice is quieter still:

```
$ gm-note.sh "$CATEGORY" "$FACT"        # both variables unset
[SUCCESS] Recorded fact in :
$ cat facts.json
{"": [{"fact": "", "timestamp": "..."}]}
```

## The guard

`tools/common.sh` provides `reject_bad_data_slot <slot-name> <value>`, called on
every positional data slot in both wrappers. It refuses any value that begins with
`-`, and any value that is empty or whitespace-only. A category, a fact, a time of
day and a date never legitimately start with a hyphen or consist of nothing.

`split_json_flag` in the same file pulls `--json` out of the arguments before the
positional slots are read, so the flag can never occupy one. Note that the two
mechanisms cover different cases: `--json` is caught by the resulting **arity**
error, while the guard catches `--type`, `-x`, `-`, `--`, and the empty string.

## Why it was not simply given verbs

That would be the cleaner design, and it is a breaking change to all nine call
sites — `CLAUDE.md`, four `.claude/commands/*.md`, `.claude/agents/world-builder.md`,
`.claude/skills/gm-craft/SKILL.md`, and two files under `docs/conventions/`. The
guard closes the hole without a migration. If someone ever does add verbs, the
guard becomes redundant rather than wrong.

## The general shape, worth recognising elsewhere

**A tool that cannot distinguish a mistake from an instruction will act on both.**
The same family has appeared three times in this repo:

* a wrapper that turned out to be a `case` dispatcher rather than a `"$@"`
  pass-through, so a new verb printed usage and **exited 0** through three review
  gates — which is why every wrapper verb now needs a test that drives the `.sh`
  through `bash`, not just the Python entry point;
* `gm-campaign.sh` with no arguments, which still prints usage and exits 0;
* `gm-time.sh`, which reported success after a failed consequence tick because its
  last line was an unconditional `exit 0`.

When a tool's failure mode is "exit 0 and look fine", no test that checks only the
exit status can see it.

## Related

* [`docs/conventions/tool-wrapper-contract.md`](../conventions/tool-wrapper-contract.md) — the `--json` envelope and where it is enforced.
* [Running the suite](running-the-suite.md) — including why a piped test run does not gate a commit.
