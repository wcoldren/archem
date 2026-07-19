---
description: Run the 181-test Pokémon Emerald suite and report counts
allowed-tools: Bash
argument-hint: [optional test pattern]
---
Run only the pokemon_emerald tests (not the full AP suite): $ARGUMENTS
Report pass/fail/skip counts. On failure, list failing tests and, per CLAUDE.md,
weigh the three causes (world bug / test bug / stale extracted_data.json).
Do NOT fix anything yet — wait for my go-ahead.
