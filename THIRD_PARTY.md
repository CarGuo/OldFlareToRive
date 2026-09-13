# Sources and third-party notices

## Original assets

The three unchanged `.flr` files come from `static/file/` in [CarGuo/gsy_github_app_flutter](https://github.com/CarGuo/gsy_github_app_flutter/tree/ffd0eb87e84a370a9603c0bd27860cd5e606e816/static/file), checkout `ffd0eb87e84a370a9603c0bd27860cd5e606e816`. Source hashes and output hashes are in `evidence/artifact-hashes.json`. The GSY repository provides the Apache-2.0 license copied as `LICENSE`.

The files do not include an author/license field establishing separate artwork ownership. This migration preserves the existing artwork and its source provenance; it does not claim new authorship or grant additional rights to the Flutter mark or third-party artwork.

## Flare comparison runtime — optional only

`validation/vendor/flare_flutter` contains the library source, pubspec, README and MIT LICENSE from the GSY-pinned [CarGuo/Flare-Flutter mirror](https://gitee.com/CarGuo/Flare-Flutter), commit `d9c4ca55cbea3f283491679847ff1e9b4bc74192`, package `flare_flutter` 3.0.2. It is used only by `validation/flare_compare`; no build or runtime dependency from `demo/` or GSY points to it.

Two compatibility details are explicit:

1. `validation/vendor/flare_flutter/lib/base/actor_drawable.dart` consumes the reserved shape byte in pre-v21 files. The [official January 2019 reader](https://github.com/2d-inc/Flare-Flutter/blob/446f5c7/flare_dart/lib/actor_shape.dart) consumed this byte; a later reader change (`80d0ee9`) stopped consuming it for old versions. `Space-Demo.flr` v18 needs the former layout to decode draw order correctly.
2. `validation/flare_compare/lib/legacy_flare.dart` restores pre-v23 clip-group drawing from [Flare-Flutter 1.5.15](https://github.com/2d-inc/Flare-Flutter/blob/bf99a765746f321937315e7ecd96aaa190a3d20b/flare_flutter/lib/flare.dart): combine shapes in a group into one path, preserving single-shape fill rules. The [d8cb780 change](https://github.com/2d-inc/Flare-Flutter/commit/d8cb780a543fe9fd35d60bcfcb198b70622c524f) introduced newer clipping behavior. Using that newer behavior as the oracle would make old geometry disappear.

All other original vector parsing, geometry, paint, animation and draw-order behavior comes from Flare. The oracle does not read RML or converter-generated geometry.

## Rive

Generated `.riv` files are compiled by official Rive CLI 1.0.2. CLI binaries are not redistributed. Rive Flutter and its native package are resolved by pub with their own license notices.
