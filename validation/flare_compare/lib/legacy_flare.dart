import 'dart:ui' as ui;

import 'package:flare_flutter/base/actor_shape.dart';
import 'package:flare_flutter/flare.dart';

// 2026-09-13: Restore the actual pre-v23 clipping semantics for the comparison
// oracle. Flare-Flutter 1.5.15 combined the shapes in each clip group into one
// non-zero path. d8cb780 (2019-10-09) changed this to successive intersections
// while adding difference clips; it makes legacy group clips disappear.
// Source: 2d-inc/Flare-Flutter bf99a765746f321937315e7ecd96aaa190a3d20b,
// flare_flutter/lib/flare.dart, FlutterActorShape.draw (MIT; see THIRD_PARTY).
// Parsing, animation, geometry, paint, and draw order still use Flare itself.
// This demo adapter rejects newer files; it does not alter the project package.
class LegacyFlareActor extends FlutterActor {
  @override
  ActorShape makeShapeNode(ActorShape? source) {
    if (version >= 23 || (source?.transformAffectsStroke ?? false)) {
      throw UnsupportedError(
        'Legacy oracle only supports pre-v23 vector shapes',
      );
    }
    return _LegacyShape();
  }
}

class _LegacyShape extends FlutterActorShape {
  @override
  void clip(ui.Canvas canvas) {
    for (final clips in clipShapes) {
      if (clips.length == 1) {
        final shape = clips.first.shape;
        if (!shape.renderCollapsed) {
          canvas.clipPath((shape as FlutterActorShape).path);
        }
      } else {
        final path = ui.Path();
        var empty = true;
        for (final clip in clips) {
          if (clip.shape.renderCollapsed) continue;
          path.addPath((clip.shape as FlutterActorShape).path, ui.Offset.zero);
          empty = false;
        }
        if (!empty) canvas.clipPath(path);
      }
    }
  }
}
