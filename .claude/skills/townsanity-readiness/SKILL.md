---
name: townsanity-readiness
description: Merge gate for emerald-townsanity -> local-test. Use before merging the Townsanity feature branch into local-test, or when the user asks "is townsanity ready to merge", "can I merge townsanity", or finishes townsanity work. Merge is blocked until all four checks pass — a green edit is not enough.
---

# Townsanity readiness

The `emerald-townsanity` branch adds town-arrival location checks
(`FLAG_VISITED_*`, location IDs 2159–2174) whose rewards are delivered over the
network. Merging it into `local-test` is **blocked** until all four gates below
pass. No merge on momentum.

Paths: pytest runs from the archem repo root
(`worlds/pokemon_emerald_beta/...`); seed generation runs from the AP workspace
root (`~/repos/AP`, `games/emerald/gen.sh`).

## Gate 1 — Full test suite

```sh
python -m pytest worlds/pokemon_emerald_beta/test
```

All green. `test/test_townsanity.py` must pass, including
`TestTownsanityRequiresRemoteItems` (the guard test at lines 59–69).

## Gate 2 — Option-matrix seed generation

Generate across the matrix **townsanity {on, off} × remote_items {on, off}** and
confirm each cell behaves:

| townsanity | remote_items | expected |
| --- | --- | --- |
| off | off | generates |
| off | on  | generates |
| on  | on  | generates, town checks present |
| on  | off | **generation refused** — the guard fires |

The `remote_items` guard already landed in `world.py:249-255` (`generate_early`
raises `OptionError` because town rewards are network-delivered and would be
unreachable without remote items; race mode satisfies it via the force-enable
just above). **Verify the guard actually fires** on the town-on / remote-off
cell — a silent pass here means the guard regressed.

## Gate 3 — In-game smoke test

Play a townsanity-on seed and confirm the `FLAG_VISITED_*` town-arrival checks
actually send on arrival. Walk into towns and watch the checks register (flag
IDs 2159–2174, built in `data.py:562-570`). This is the gate the test suite
cannot cover.

## Gate 4 — Sootopolis & Ever Grande reachable in logic

Confirm both special-case town-arrival regions are reachable in logic with their
HM requirements respected:

- **Sootopolis** (arrival region `/WATER`) — behind Dive.
- **Ever Grande** (arrival region `/SEA`) — behind Waterfall.

Check via `python -m pytest worlds/pokemon_emerald_beta/test/test_accessibility.py`
and by inspecting `rules.py` for the Dive/Waterfall access rules on those town
checks. A town check that is placed but unreachable is a logic failure, not a
pass.

## Merge is blocked until all four pass

If any gate fails, fix and rerun from Gate 1. Then run `/code-review` on the diff
in a fresh-context session per the repo's merge-and-milestone review gate before
merging into `local-test`.
