# Trainer → region coverage: scoping notes

> **✅ RESOLVED (1a, option C).** Implemented via `data/extract_trainer_maps.py` →
> `data/trainer_map.json`, consumed as a fallback in `scaling.py:_build_trainer_region_map`.
> Coverage went **484 → 534 trainers** (+50). Findings that refined the plan below:
> - 515 `Archipelago_Target_TRAINER_*` labels exist (96 maps); `<MapDir>/map.json` `"id"` gives
>   the `MAP_` constant; the apworld resolves map → representative region (prefer `/MAIN`).
> - **0 labeled trainers are rematches** — true Match Call rematches (`_2..5`) have no label, so
>   they never enter the table and stay vanilla by omission (verified in ROM). Frontier brains use
>   the label-less generic `trainerbattle TRAINER_BATTLE_*` form and are likewise excluded.
> - The `_N` suffix is **overloaded** (`GRUNT_AQUA_HIDEOUT_1..8` are distinct grunts), so rematch
>   detection keys on the `trainerbattle_rematch*` macro only. A `rematch` flag + single guard
>   leaves a future `LevelScalingIncludeRematches` opt-in (mirrors Crystal's hidden `Rematchsanity`).
>
> Original scoping notes preserved below.

Local scratch (this `dev/` dir is gitignored). Context for the future "scale *every*
trainer" step. Today the level-scaling feature only covers trainers that have a
`TRAINER_<NAME>_REWARD` location (~the ~484 with locations); rematches, Battle Frontier
brains, and non-canonical rival variants have no region data and stay vanilla.

## Why coverage is limited today
`scaling.py:_build_trainer_region_map` is the only coverage gate. It reads
`data.locations` and maps a trainer to `loc_data.parent_region` via its
`TRAINER_*_REWARD` location. Emerald's `RegionData` (data.py) has **no `trainers` list**
(only `exits/warps/locations/events`), and `extracted_data.json` trainer entries carry no
map/region. So a trainer with no reward location has no region → not ranked → vanilla.

We already special-case the merged Route-103-style rival locations: when
`TRAINER_BRENDAN_<locale>_MUDKIP` maps, we also map the 5 sibling variants
(`MAY_*`, `*_TORCHIC`, `*_TREECKO`) to the same region, so the rival the player actually
fights is scaled.

## Where the real data lives (base patch decomp: vendor/emerald-archipelago)
Trainer → map is fully defined in the decomp, three layers:

1. `data/maps/<Map>/map.json` — object events with a `script` field
   (e.g. Route103 woman → `Route103_EventScript_Daisy`).
2. `data/maps/<Map>/scripts.inc` — the script calls a `trainerbattle*` macro with the
   trainer constant, e.g.:
   ```
   Route103_EventScript_Daisy::
   Archipelago_Target_TRAINER_DAISY::
       trainerbattle_single TRAINER_DAISY, ...
   ```
   ```
   MauvilleCity_Gym_EventScript_Wattson::
   Archipelago_Target_TRAINER_WATTSON_1::
       trainerbattle_single TRAINER_WATTSON_1, ...
   ```
3. `include/constants/opponents.h` — numeric constants.

**Key hook:** the `Archipelago_Target_TRAINER_<NAME>::` labels live in each map's
`scripts.inc`, and the extractor already keys on them. So trainer→map = "which map's
scripts.inc contains the label", trivially derivable.

## Extractor
`vendor/emerald-archipelago/tools/extractor/extractor.cpp` already scans symbols named
`Archipelago_Target_TRAINER*` to record each trainer's battle-script address (~line 92-100),
but does **not** record the source map. It writes `extracted_data.json`; map entries there
hold only encounter tables, not trainer placements.

## Granularity gap
AP regions are **sub-map** (e.g. `MAP_ROUTE103` → `REGION_ROUTE103/{WEST,WATER,EAST,
EAST_TREE_MAZE}` in `data/regions/routes.json`). Region JSONs associate trainers to a
sub-region only via the `locations` array (the `_REWARD` keys); there are no coordinates.
So trainer→map gives the *map*, but choosing the exact sub-region needs either object-event
coords vs region boundaries, or a manual pick. For scaling purposes a *representative*
sub-region (e.g. the map's main region) is good enough — sphere differences between
sub-regions of one map are usually 0–1.

## Location-less trainers (~150)
- Rematches (~78): gym-leader/route `_N` rematch ladders (`trainerbattle_rematch*`).
- Rival variants (~16): mostly handled by our sibling-merge expansion already.
- Battle Frontier brains (~8): generated at runtime by the Frontier AI, not in map scripts
  → would be hardcoded to a Frontier region.
- Grunts / multi-map / scripted specials: assign to first/representative map.

## Implementation options (future)
- **A — extend extractor.cpp** (auto, ~full): when emitting each
  `Archipelago_Target_TRAINER_*`, also record its source map; emit `trainer -> map` in
  `extracted_data.json`; map→representative region in the world. Needs C++ change + rebuild
  + regenerate `extracted_data.json` + bump base-patch/data version.
- **B — hand-author** `data/trainer_regions.json` (~150 rows for the location-less trainers).
  Fast (hours) but manual and drifts from the decomp.
- **C — hybrid (recommended)**: a small Python/regex pass over
  `vendor/emerald-archipelago/data/maps/*/scripts.inc` (match `Archipelago_Target_TRAINER_`
  / `trainerbattle*`) → `trainer -> map` table checked into data; manual overrides for
  Frontier. Feed the result into `_build_trainer_region_map`. No C++/extractor rebuild.

**Caveat (applies to all options):** even with full coverage, *exclude rematches by default*.
A rematch mapped to its gym's region inherits that gym's early sphere → it would scale to a
low level, wrong for post-game content. Crystal excludes rematches by default for this exact
reason. So fuller coverage mainly buys correct scaling for Frontier/special battles and any
non-rematch trainers we currently miss.

## Moveset limitation (orthogonal, worth noting)
Trainer-mon move type counts (from `extracted_data.json`):
- `NO_ITEM_DEFAULT_MOVES` 673 + `ITEM_DEFAULT_MOVES` 31 = **704 default-moves**
- `NO_ITEM_CUSTOM_MOVES` 87 + `ITEM_CUSTOM_MOVES` 64 = **151 custom-moves**

For **default-moves** trainers the game derives the moveset from the species' level-up
learnset at the mon's level inside `CreateMon` (base patch
`battle_main.c:CreateNPCTrainerParty`). So scaling a mon's level UP automatically gives it
level-appropriate moves — no extra work.

For **custom-moves** trainers (many gym leaders / E4 / important battles) the moves are fixed
in trainer data and are *not* re-derived. A custom-moves ace scaled from ~15 up to ~50 keeps
its hand-picked low-level moveset (e.g. a level-50 mon still throwing Tackle / Tail Whip).
Crystal has the same behavior (level-only `replace`, no move re-derivation).

Possible future enhancement: for heavily-upscaled custom-moves trainers, re-derive the top-4
level-up moves at the new level (or top up empty slots). Out of scope for v1; would change
designed movesets and needs care for signature/coverage moves.
