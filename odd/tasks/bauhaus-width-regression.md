# Bauhaus map width regression

The Bauhaus map example specs no longer render: 24 tests fail on `main` and the
skill sync gate (`scripts/sync_skills.sh`) refuses to sync the installed skill copies.

## Specs

- S1: `tests/skills/test_visual_builder_contract.py::test_example_specs_render_and_pass_the_print_size_check` and every test in `tools/test_bauhaus_maps.py` pass again. Observed failure, verbatim: "bauhaus_maps: layout is 1030 units wide, over the 860-unit limit; the figure is never shrunk, so split the map or shorten names and details".
- S2: The root cause is identified with evidence before any fix. Leading hypothesis, unproven: `pillow` is unpinned in `requirements.txt` (installed 12.3.0) and `_face()` in `tools/bauhaus_maps.py` (`ImageFont.truetype` + `set_variation_by_axes([weight])`) now measures text differently. Confirm or refute it by measuring the same string under the installed Pillow and an older one in a scratch virtualenv created with `mktemp -d`; never change the packages of the shared `.venv`.
- S3: The fix addresses the cause, not the symptom: do not raise `MAX_WIDTH`, do not loosen or delete tests, and do not shorten the example specs unless the evidence shows the examples themselves are what changed.
- S4: Rendered output for specs that already rendered stays the same unless the cause requires otherwise; report any difference.

## Tasks

- T1 [S1-S4] delegated worker: diagnose and fix; done, uncommitted (see L2).

## Log

- L1: Parent request (2026-11-11): the sync gate failed after merging PR #123 with the failure quoted in S1; it pre-exists on e0f258d (23 failures in tools/test_bauhaus_maps.py, 1 in tests/skills/test_visual_builder_contract.py).
- L2: T1 (2026-11-11). S2 hypothesis refuted: Pillow 12.3.0 was installed 2026-08-06, before the suite last passed, and a scratch venv with Pillow 11.3.0 measures the same advances ("Specification Driven" at 100 px: 969.8/971.8/973.4 at wght 400/500/700 in both). The repo is not the cause either: no commits to tools/bauhaus_maps.py, the examples or assets/fonts since 2026-10-11. Root cause: system Graphviz was upgraded 16.1.0-2 -> 16.1.1-1 on 2026-11-09 (pacman.log). On the same `dot` input, 16.1.0 lays the sdd map out 11.027 in (794 units, 842 with padding) and 16.1.1 13.638 in (982 units, 1030 with padding), because 16.1.1's `ordering=out` orders a node's children by node declaration order instead of edge order (minimal repro: `ordering=out; c;d;e; b->c; b->e; b->d;` gives c,e,d on 16.1.0 and c,d,e on 16.1.1), which put `clar` left of `plan` and pushed the spine off-centre. Fix in tools/bauhaus_maps.py: `_declaration_order()` declares concepts breadth-first along the tree links, in link order, so both versions agree. S4: the SVG output of both examples is byte-identical between the HEAD code on 16.1.0 and the fixed code on 16.1.0 and 16.1.1. Existing `test_sibling_order_follows_the_spec` already guards the contract (the HEAD code fails it on 16.1.1). No new test, no pin (Graphviz is a system package, not in requirements.txt).
