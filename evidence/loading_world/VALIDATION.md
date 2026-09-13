# loading_world_now migration validation — 2026-09-13

## 看代码

All implementation is isolated under `tool/flare_to_rive/`, plus the linked
runbook in `docs/03-runbooks/flare-rive-migration.md`. Production widgets and
dependencies were not edited. `convert_flare.py` translates source vector paths,
hierarchical transforms, clipping, global draw order and six timeline keys to
RML; `build.py` verifies/inspects/builds through official Rive CLI 1.0.2.

Generated runtime asset: `demo/assets/loading_world_now.riv`, **110,241 bytes**.
SHA-256: `50724194da34668dc943f40d63334a4efb71a3bba068a98a5ce47584982680a3`.
The original `.flr` is unchanged; source/output hashes are in `artifact-hashes.json`.

The reference loads the original binary through Flare, with official historical
1.5.15 clipping semantics restored by `legacy_flare.dart`. This adapter is
independent of the converter. The Rive side uses the project's Rive 0.14.11 /
rive_native 0.1.11 with `Factory.flutter` and its public painter API.

## 看编译

- `rive --verify`, `inspect`, `--once`: successful, no errors or warnings;
  `rive-build.txt`, `../loading_world/build/inspect.json`.
- `flutter pub get`, `flutter gen-l10n`, `flutter analyze`: successful,
  analyzer **No issues found**; corresponding `flutter-*.txt` files.
- 7 Python structural/failure regression tests: passed (`converter-tests.txt`).
- macOS debug build: successful (`flutter-run.txt`).
- Independent clean-context reviewer completed two passes. Initial SDK finding
  was corrected to Dart `>=3.13.0 <4.0.0`; latest review found no blocking defects.

Actual test SDK: Flutter from `/Users/guoshuyu/workspace/flutter`,
Dart 3.14.0-53.0.dev. The declared Dart 3.13 minimum was reviewed for compatibility
but was not separately run with a 3.13 SDK in this experiment.

## 看运行

Device **macos**, macOS 26.5.2 arm64, Apple M1 Pro, Flutter Impeller/MetalSDF.
Official `dart mcp-server` 1.1.1 was connected via its stdio JSON-RPC API.

- DTD: `ws://127.0.0.1:51877/agA6jUTNNnE=`
- VM Service: `ws://127.0.0.1:51878/jUAlY38YHMQ=/ws`
- `runtime-clean-baseline.json` and `runtime-final.json`: no runtime errors.
- `widget-final.json`: two actual `CustomPaint` nodes, both pane labels,
  `Ready · 10.0 s · 2.500 s`, playback and pull controls.
- Native window screenshot:
  `/Users/guoshuyu/workspace/flutter-work/gsy_github_app_flutter/tool/flare_to_rive/evidence/macos-comparison.png`.
- Side-by-side exported frames:
  `/Users/guoshuyu/workspace/flutter-work/gsy_github_app_flutter/tool/flare_to_rive/evidence/comparison-sheet.png`.

`pixel-comparison.json` measures 10 full-resolution frame pairs, including frames
299/300 and loop endpoints. The 192,434-pixel foreground union has **at most four
pixels per frame** with any RGBA channel differing by more than 2/255. No image
alignment, color correction or raster replacement is used.

`timeline.json` checks 1,201 half-frame samples. Maximum local X difference is
**0.00518798828125** at the moon's rapid transition. The original strict 0.0001
diagnostic remains **false**. Rive's float32 time/interpolation explains this
difference: the reviewer independently reproduced the exact value from native
`keyframe.cpp` / `keyframe_double.cpp`. The source-key-derived conservative bound
is 0.02120737928383833; observed error is within it. This is visual restoration,
not bit-for-bit identity.

The generated **default state machine** was separately instantiated and advanced
through 0–11 seconds, including a loop. Its maximum local X error against Flare
is 0.000030517578125. `pull-progress.json` covers zero, normal progress, both sides
of the existing threshold discontinuity, and near-full progress. The demo's
actual Play/Pause controls were also exercised; MCP state is in `widget-playing.json`
and `playback-*.json`.

## Diagnostic history and limits

An earlier direct VM evaluation that changed playback produced a Flutter debug
stack-parser assertion. Its raw response is retained as
`diagnostic-eval-failure.json`; it is not counted as a passing run. After a full
process restart, export work was queued with a Dart Future, Play/Pause was driven
through the native UI, and final MCP/runtime/window evidence was collected.
No framework or application fallback was added for this diagnostic failure.

The initial RML omitted required Any/Exit states; it passed CLI compilation but
failed native import. Both states are now emitted and covered by a regression
test plus the real default-state-machine run. This is why CLI-only validation
was insufficient.

Not covered: production GSY refresh integration, Android/iOS, Rive's alternate
renderer, other `.flr` assets, signed publishing/editor `.rev` export. This
standalone path does not enter adaptive shell; fold/unfold testing is exempt.
