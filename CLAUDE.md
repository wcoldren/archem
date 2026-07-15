# Claude instructions for the archem Emerald fork

This is `wcoldren/archem`, a personal experimental fork of the Pokémon Emerald
Archipelago world. It is developed as part of Bill's `~/repos/AP` workspace (this
repo is vendored there under `vendor/archem`); the workspace `CLAUDE.md` and the
per-game docs under `games/emerald/` hold the broader context.

## Merge and milestone review gate

- Before any merge into `trunk` (archem) or `local-test`, and before each M1/M2
  milestone commit on AP `main`, run `/code-review` in a **fresh-context session**
  on the diff. Findings must be addressed or explicitly waived in the commit
  message (say which finding and why).
- Engine struct-layout changes — `ArchipelagoOptions` and anything `rom.py` reads
  by offset — **always** get the fresh-context review, even when the tests pass. A
  silent offset mistake corrupts `rom.py`'s read assumptions without failing any
  test, so a green suite is not sufficient cover for these.
- Bill drives key engine commits himself. Claude Code prepares, verifies, and
  stages those, then **stops before committing** — it does not commit engine
  struct-layout changes on Bill's behalf.
