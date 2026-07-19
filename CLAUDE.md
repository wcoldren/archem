# archem — Pokémon Emerald AP world (Python) + AP tooling

Descends from Zunawe's emerald-dev fork of ArchipelagoMW/Archipelago.
`trunk` is the integration trunk (GitHub default). Keeper branches: main,
emerald-hm-no-badges, 3 level-spheres variants. Do NOT force-push keepers.

## Working style (IMPORTANT)
- Learning-first + piecemeal: explain before editing, one step at a time,
  wait for results before the next step. Use prediction-then-verify.

## Test & verify
- Full Emerald suite: 181 tests must stay green. Run the emerald tests only
  (not the whole AP suite) for speed. Report pass/fail counts explicitly.
- If a test fails, weigh equally: bug in world code, bug in test, or a stale
  `extracted_data.json` from an engine rebuild.

## Footguns
- rom.py depends on byte offsets from `extracted_data.json`, which is generated
  from the emerald-archipelago engine (source + linker map + binary via
  tools/extractor). If engine structs change, offsets must be regenerated or
  rom.py patches the wrong bytes. Treat extracted_data.json as generated, not hand-edited.
- Data heavyweights (ROMs, decomp clones) are gitignored and excluded from the
  Claude.ai project sync. Do not add them.
- townsanity requires the remote_items guard; keep it.

## Repo etiquette
- Small, logically-scoped commits with descriptive messages. Explain the WHY.
