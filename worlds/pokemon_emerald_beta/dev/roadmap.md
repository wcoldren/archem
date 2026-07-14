# Level scaling — roadmap / next steps

Local scratch (`dev/` is gitignored). v1 shipped = **trainers only**, rank-based curve, for
trainers that have a `TRAINER_*_REWARD` location. What's still untouched and a suggested order.

## Not yet scaled (what the trainer pass didn't touch)
- **Wild encounters** (grass / water / fishing). The ROM encounter tables DO store per-slot
  `min_level` / `max_level` (see `rom.py:_set_encounter_tables` — struct is
  `min(1) max(1) species(2)`), but extraction emits only `{address, slots}` (species). So
  scaling wilds needs: extend `EncounterTableData` to carry levels, capture them during
  extraction, and add level writes in `_set_encounter_tables`.
- **Static / misc Pokémon**. `misc_pokemon` entries have no `level` extracted (just
  `{address, species}`) → need extraction work. **`legendary_encounters` already carry
  `level`** (e.g. 30), so legendaries are the cheapest static to scale.
- **Rematches / Battle Frontier brains** — left vanilla because they have no region (no reward
  location). See `region_map_scoping.md`. Note: rematches should stay excluded by default even
  after coverage (a rematch at its gym's early sphere would mis-scale).

## Suggested priority (reorder as you like)
1. ✅ **DONE — Trainer region-map full coverage** — `data/extract_trainer_maps.py` →
   `data/trainer_map.json`, fallback in `_build_trainer_region_map`. 484 → 534 trainers scaled.
   Rematches & Frontier stay vanilla by design (they carry no decomp battle label). See the
   RESOLVED banner in `region_map_scoping.md`.
2. **Wild-encounter level scaling** — biggest gameplay gap: wild mons stay vanilla while
   trainers scale, so a scaled region's wilds feel off. Needs the extraction work above.
3. **Legendary / static scaling** — legendaries already have levels (easy); misc/static need
   extraction. Crystal scales statics flat to the sphere target.
4. **Custom-move moveset re-derivation** — 151 custom-move trainers keep fixed (often weak)
   movesets when upscaled (e.g. a lvl-50 ace with Tackle/Tail Whip). Default-move trainers
   (704) already auto-derive level-appropriate moves. Optional polish; re-derive top-4 level-up
   moves for heavily-upscaled custom-move trainers. (Crystal doesn't do this.)
5. **"Adding Pokémon"** — separate, larger track (new species / expansion content); independent
   of level scaling. Schedule on its own.

## Unrelated cleanup spotted
- The HM "No Badges Required" commit (`emerald-hm-no-badges`, `8a6e684a`) left a stray
  `print(self.hm_requirements)` in `world.py` (generate_early). Drop it before that PR.
