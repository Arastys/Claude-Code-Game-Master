---
type: Gotcha
title: This pytest prints no tally line, and a piped run will let a red commit through
description: The suite here aborts on a collection error, reports no "X passed" summary, and silently commits on failure if you chain it behind a pipe — three traps that have each produced a false green.
sources:
  - { resource: /tests/conftest.py }
  - { resource: /tests/test_reset_archive.py }
---

# Running the suite here has three traps

Each one has produced a wrong answer in this repo — a report claiming numbers nobody
counted, a run that aborted before it started, and a commit made on a failing test.

## The command

```bash
uv run python -m pytest -q --continue-on-collection-errors
```

**Baseline as of 2026-09-10: 854 passing, 31 failing.** The 31 are environmental, not
broken code: 27 need Windows Developer Mode for `os.symlink`, and 4 are
path-separator assertions. Compare the failing *set*, not just the count.

## Trap 1 — the run aborts without `--continue-on-collection-errors`

`tests/test_reset_archive.py` calls `os.geteuid`, which does not exist on Windows.
Without the flag, pytest stops with `Interrupted: 1 error during collection` and runs
**nothing** — which reads as "no failures" if you only skim the tail.

## Trap 2 — there is no final tally line

This pytest prints no `X passed, Y failed` summary. Do not infer one. Count:

```bash
uv run python -m pytest -q --continue-on-collection-errors > out.txt 2>&1
grep -c '^FAILED ' out.txt
```

For the passing count, count progress markers before the summary section:

```bash
awk '/short test summary info/{exit} {print}' out.txt | tr -cd '.F' | wc -c
```

Two separate agents have reported tallies they did not count — one said
"101 failed / 636 passed" when the truth was 31/706. Numbers nobody counted are
worse than no numbers, because they look like evidence.

## Trap 3 — a piped test run will not gate your commit

```bash
pytest … | tail -3 && git commit -m "..."     # commits even when tests fail
```

A pipeline's exit status is the **last** command's. `tail` always succeeds, so the
`&&` never guards anything. This is not hypothetical: it put a knowingly-broken test
into `e5eaf99` on this repo. Run the tests, read the result, then commit as a
separate step.

## Comparing failing sets

A count can stay at 31 while the *membership* changes — one fixed, one broken. The
check that actually means something:

```bash
grep '^FAILED ' out.txt | sed 's/ - .*//' | sort > after.set
diff before.set after.set    # empty = you changed nothing you did not mean to
```

## A related trap in test helpers

`tests/test_statusline.py::_run` had to be given `encoding="utf-8"` explicitly.
`subprocess` with `text=True` decodes using the Windows locale encoding, so any
non-ASCII output — the HUD's bar glyphs, an em dash, a box-drawing character —
returns as mojibake and no assertion on it can pass. Eleven tests in that file only
ever checked ASCII, which is why it went unnoticed until the twelfth did not.

## Related

* [`docs/conventions/tool-wrapper-contract.md`](../conventions/tool-wrapper-contract.md) — where the `--json` envelope is enforced.
