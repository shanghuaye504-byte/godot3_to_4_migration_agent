# A-layer build report

Built at: 2026-08-26T17:12:06.680729+00:00
Total rows in rules.db: **8260**
YAML archive entries skipped (not inserted): **2**
ID collisions (later source won): **0**

## By source

| source | rows |
| --- | ---: |
| `api_diff` | 6612 |
| `official_renames` | 1101 |
| `official_prose` | 444 |
| `official_renames_skipped` | 84 |
| `manual_rewrite` | 10 |
| `manual_trap` | 5 |
| `official_prose_3to4_shader` | 4 |

## By detection_method

| detection_method | rows |
| --- | ---: |
| `agent_retrieval` | 8255 |
| `static_scan_post_l0` | 2 |
| `verify_error_filter` | 2 |
| `agent_retrieval_or_escalate` | 1 |

## By symbol_kind (top)

| symbol_kind | rows |
| --- | ---: |
| `method` | 5634 |
| `property` | 1246 |
| `class` | 423 |
| `enum` | 413 |
| `signal` | 188 |
| `color` | 146 |
| `project_setting` | 83 |
| `constant` | 45 |
| `theme` | 26 |
| `shader` | 18 |
| `builtin` | 10 |
| `rewrite` | 10 |
| `utility` | 7 |
| `singleton` | 6 |
| `trap` | 5 |

## Adapter notes

- cpp unrecognized lines: **0**
- rst unclassified (kept as `behavior`/`needs_review`): **7**

## Prose intermediate files (`vault/tier_b_prose/`)

- `upgrading_to_godot_4.1.rst.prose.jsonl` — 4 blocks
- `upgrading_to_godot_4.2.rst.prose.jsonl` — 3 blocks
- `upgrading_to_godot_4.3.rst.prose.jsonl` — 14 blocks
- `upgrading_to_godot_4.4.rst.prose.jsonl` — 9 blocks
- `upgrading_to_godot_4.5.rst.prose.jsonl` — 12 blocks
- `upgrading_to_godot_4.6.rst.prose.jsonl` — 9 blocks
- `upgrading_to_godot_4.7.rst.prose.jsonl` — 9 blocks
- `upgrading_to_godot_4.rst.updating_shaders.prose.jsonl` — 1 block

## Version filter sanity

- `since_version_code <= 4.4` (40400): **8076** rows
- `since_version_code <= 4.7.1` (40701): **8260** rows
- rows that appear only for targets after 4.4: **184**

## Pytest (`eval/test_build_artifacts.py`)

14 passed (schema_version=2, TRAP-004/007 absent, TRAP-001 static_scan, Area→Area3D, instance skipped, hint_albedo, yield rewrite, get_meta_list 4.1, 4 shader carve-out rows, 4.4 vs 4.7 filter, agent_context full copy, prose jsonl present, no csharp cpp arrays).

## Agent context

- `artifacts/agent_context/upgrading_to_godot_4.rst` — full copy of the 3→4 guide.

## Unclassified rst rows (first 30)

- `upgrading_to_godot_4.1.rst` / `SubViewportContainer`: When input events should reach SubViewports and their children, SubViewportContainer.mouse_filter now needs to be MOUSE_FILTER_STOP or MOUSE_FILTER_PASS. See...
- `upgrading_to_godot_4.1.rst` / `Viewport`: Viewport nodes, that have Physics Picking enabled, now automatically set InputEvents as handled. See GH-79897 for workarounds.
- `upgrading_to_godot_4.5.rst` / `RichTextLabel`: Method add_image replaced size_in_percent parameter by width_in_percent and height_in_percent
- `upgrading_to_godot_4.5.rst` / `RichTextLabel`: Method update_image replaced size_in_percent parameter by width_in_percent and height_in_percent
- `upgrading_to_godot_4.5.rst` / `OpenXRBindingModifierEditor`: Type OpenXRBindingModifierEditor changed API type from Core to Editor
- `upgrading_to_godot_4.5.rst` / `OpenXRInteractionProfileEditor`: Type OpenXRInteractionProfileEditor changed API type from Core to Editor
- `upgrading_to_godot_4.5.rst` / `OpenXRInteractionProfileEditorBase`: Type OpenXRInteractionProfileEditorBase changed API type from Core to Editor
