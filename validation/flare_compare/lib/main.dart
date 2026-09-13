import 'dart:io' as io;
import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flare_flutter/flare.dart' as flare;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:rive/rive.dart' as rive;

import 'l10n/app_localizations.dart';
import 'legacy_flare.dart';

// 2026-09-13: Independent migration oracle. Both production runtimes receive
// the same absolute animation time; the original asset is never reconstructed.
ComparisonController? get comparison =>
    demoPage?._viewKey.currentState?.controller;
ComparisonPageState? demoPage;

// Used by the same running demo and Dart MCP; no separate renderer/oracle.
Future<void> validateAllAnimations() async {
  final page = demoPage!;
  for (var i = 0; i < page.assets.length; i++) {
    for (final spec in page.assets[i]['animations'] as List) {
      await page.select(i, spec['name'] as String);
      await comparison!.exportEvidence();
    }
  }
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ComparisonApp());
}

class ComparisonController extends ChangeNotifier {
  final Map<String, dynamic> asset;
  final Map<String, dynamic> animationSpec;
  final flare.FlutterActor actor;
  final flare.FlutterActorArtboard original;
  final flare.ActorAnimation originalAnimation;
  final rive.File file;
  final rive.Artboard converted;
  final rive.Animation convertedAnimation;
  late final rive.BasicArtboardPainter _resolver;
  late final Ticker _ticker = Ticker(_tick);
  Duration _previous = Duration.zero;
  double time = 0;
  double pullDistance = 0;
  bool playing = false;
  bool dark = true;
  bool exporting = false;
  bool _disposed = false;
  String? lastExportPath;
  String? exportError;

  ComparisonController(
    this.asset,
    this.animationSpec,
    this.actor,
    this.original,
    this.originalAnimation,
    this.file,
    this.converted,
    this.convertedAnimation,
  ) {
    _resolver = rive.BasicArtboardPainter()..artboardChanged(converted);
    seek(0);
  }

  double get duration => originalAnimation.duration;
  Size get artboardSize => Size(original.width, original.height);

  static Future<ComparisonController> load(
    Map<String, dynamic> asset,
    String name,
  ) async {
    final actor = LegacyFlareActor();
    flare.FlutterActorArtboard? original;
    rive.File? file;
    rive.Artboard? converted;
    rive.Animation? convertedAnimation;
    try {
      if (!await actor.loadFromBundle(
        rootBundle,
        'assets/${asset['source']}',
      )) {
        throw StateError('Flare load failed');
      }
      original = actor.artboard!.makeInstance() as flare.FlutterActorArtboard;
      original.initializeGraphics();
      final originalAnimation = original.getAnimation(name);
      if (originalAnimation == null) {
        throw StateError('Missing Flare animation: $name');
      }
      file = await rive.File.asset(
        'assets/${asset['output']}',
        riveFactory: rive.Factory.flutter,
      );
      if (file == null) throw StateError('Rive decode failed');
      converted = file.defaultArtboard();
      if (converted == null) throw StateError('Missing Rive artboard');
      converted.frameOrigin = false;
      convertedAnimation = converted.animationNamed(name);
      if (convertedAnimation == null ||
          (convertedAnimation.duration - originalAnimation.duration).abs() >
              1e-5) {
        throw StateError('Animation name/duration mismatch');
      }
      return ComparisonController(
        asset,
        (asset['animations'] as List).cast<Map<String, dynamic>>().firstWhere(
          (a) => a['name'] == name,
        ),
        actor,
        original,
        originalAnimation,
        file,
        converted,
        convertedAnimation,
      );
    } catch (_) {
      convertedAnimation?.dispose();
      converted?.dispose();
      file?.dispose();
      original?.dispose();
      actor.dispose();
      rethrow;
    }
  }

  void seek(double seconds) {
    if (_disposed) throw StateError('Comparison view closed during export');
    time = seconds.clamp(0, duration);
    originalAnimation.apply(time, original, 1);
    original.advance(0);
    convertedAnimation.time = time;
    convertedAnimation.apply();
    // The public painter resolves component dirt as well as advancing time.
    // Artboard.advance alone calls native advanceInternal in version 0.1.11.
    _resolver.advance(0);
    notifyListeners();
  }

  void _tick(Duration elapsed) {
    final delta = (elapsed - _previous).inMicroseconds / 1e6;
    _previous = elapsed;
    final next = time + delta * 2;
    if (!(animationSpec['loop'] as bool) && next >= duration) {
      seek(duration);
      setPlaying(false);
    } else {
      seek(next % duration);
    }
  }

  void setPlaying(bool value) {
    if (value && time >= duration) seek(0);
    playing = value;
    if (value) {
      _previous = Duration.zero;
      if (!_ticker.isActive) _ticker.start();
    } else {
      _ticker.stop();
    }
    notifyListeners();
  }

  void setPull(double distance) {
    setPlaying(false);
    pullDistance = distance;
    // Mirrors GSYFlarePullController and the refresh widget's 0.6 factor.
    // Keep the threshold discontinuity: this demo verifies existing behavior.
    const trigger = 140.0;
    final extent = distance * 0.6;
    final adjusted = extent > trigger ? extent - trigger : extent;
    seek(duration * math.pow(adjusted / trigger, 2));
  }

  void setDark(bool value) {
    dark = value;
    notifyListeners();
  }

  void paint(Canvas canvas, Size size, bool useRive, [rive.Artboard? board]) {
    canvas.save();
    canvas.clipRect(Offset.zero & size);
    final scale = math.min(
      size.width / original.width,
      size.height / original.height,
    );
    canvas.translate(
      (size.width - original.width * scale) / 2,
      (size.height - original.height * scale) / 2,
    );
    canvas.scale(scale);
    if (useRive) {
      final renderer = rive.Renderer.make(canvas);
      (board ?? converted).draw(renderer);
      renderer.dispose();
    } else {
      original.draw(canvas);
    }
    canvas.restore();
  }

  Future<void> _saveFrame(
    io.Directory directory,
    String name,
    bool useRive, [
    rive.Artboard? board,
  ]) async {
    if (_disposed) throw StateError('Comparison view closed during export');
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    paint(canvas, artboardSize, useRive, board);
    final picture = recorder.endRecording();
    final image = await picture.toImage(
      original.width.toInt(),
      original.height.toInt(),
    );
    picture.dispose();
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    await io.File('${directory.path}/$name.png')
        .writeAsBytes(data!.buffer.asUint8List());
  }

  Future<void> exportEvidence() async {
    if (exporting) return;
    final oldTime = time;
    final wasPlaying = playing;
    setPlaying(false);
    exporting = true;
    exportError = null;
    notifyListeners();
    try {
      const configured = String.fromEnvironment('EVIDENCE_DIR');
      final base = configured.isEmpty
          ? (await io.Directory.systemTemp.createTemp('flare-rive-')).path
          : configured;
      final animationFolder = originalAnimation.name.replaceAll(
        RegExp(r'[^a-zA-Z0-9_-]'),
        '_',
      );
      final directory = await io.Directory(
        '$base/${asset['project']}/$animationFolder',
      ).create(recursive: true);
      final fps = originalAnimation.fps;
      final endFrame = (duration * fps).round();
      final keyFrames = (animationSpec['keyFrames'] as List).cast<int>();
      final frames = <double>{0, endFrame.toDouble()};
      for (final f in keyFrames) {
        frames.addAll([f.toDouble(), f - .5, f + .5]);
      }
      final boundaries = {...keyFrames, 0, endFrame}.toList()..sort();
      for (var i = 1; i < boundaries.length; i++) {
        final a = boundaries[i - 1], b = boundaries[i];
        // Thirds deliberately do not coincide with the converter's dyadic
        // morph grid, so this also checks interpolation between baked keys.
        frames.addAll([a + (b - a) / 3, a + 2 * (b - a) / 3]);
      }
      final selected = frames.where((f) => f >= 0 && f <= endFrame).toList()
        ..sort();
      final playbackBoard = file.defaultArtboard()!..frameOrigin = false;
      final machine = playbackBoard.stateMachine(originalAnimation.name);
      if (machine == null) {
        playbackBoard.dispose();
        throw StateError('Missing state machine: ${originalAnimation.name}');
      }
      var previous = 0.0;
      final samples = <Map<String, Object>>[];
      try {
        for (var index = 0; index < selected.length; index++) {
          final frame = selected[index];
          final seconds = math.min(frame / fps, duration);
          seek(seconds);
          final name = 'frame-${index.toString().padLeft(3, '0')}';
          await _saveFrame(directory, '$name-flare', false);
          await _saveFrame(directory, '$name-rive', true);
          // Independently advance the exported state machine from time zero.
          // Looping state machines wrap at their end, while direct scrub
          // intentionally exposes the last frame. Compare their loop pose.
          machine.advanceAndApply(seconds - previous);
          previous = seconds;
          final loop = animationSpec['loop'] as bool;
          final nativeDuration = convertedAnimation.duration;
          final referenceTime = loop && seconds >= nativeDuration
              ? seconds % nativeDuration
              : seconds;
          seek(referenceTime);
          await _saveFrame(directory, '$name-playback-flare', false);
          await _saveFrame(
            directory,
            '$name-playback-rive',
            true,
            playbackBoard,
          );
          samples.add({
            'index': index,
            'sourceFrame': frame,
            'seconds': seconds,
            'playbackReferenceSeconds': referenceTime,
          });
        }
        // A complete extra loop / one-shot hold exercises duration semantics.
        final seconds = convertedAnimation.duration * 1.25;
        machine.advanceAndApply(seconds - previous);
        seek(
          (animationSpec['loop'] as bool)
              ? convertedAnimation.duration * .25
              : duration,
        );
        await _saveFrame(directory, 'after-end-playback-flare', false);
        await _saveFrame(
          directory,
          'after-end-playback-rive',
          true,
          playbackBoard,
        );
      } finally {
        machine.dispose();
        playbackBoard.dispose();
      }
      await io.File('${directory.path}/samples.json').writeAsString(
        const JsonEncoder.withIndent('  ').convert({
          'source': asset['source'],
          'animation': originalAnimation.name,
          'fps': fps,
          'durationSeconds': duration,
          'riveDurationSeconds': convertedAnimation.duration,
          'loop': animationSpec['loop'],
          'samples': samples,
        }),
      );
      lastExportPath = directory.path;
    } catch (error) {
      exportError = '$error';
      rethrow;
    } finally {
      exporting = false;
      if (_disposed) {
        _releaseNativeResources();
      } else {
        seek(oldTime);
        setPlaying(wasPlaying);
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _ticker.dispose();
    // An in-flight PNG export owns the resources until its finally block.
    // It stops at the next awaited frame instead of using freed native objects.
    if (!exporting) _releaseNativeResources();
    super.dispose();
  }

  void _releaseNativeResources() {
    _resolver.dispose();
    convertedAnimation.dispose();
    converted.dispose();
    file.dispose();
    original.dispose();
    actor.dispose();
  }
}

class ComparisonApp extends StatelessWidget {
  const ComparisonApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    theme: ThemeData(colorSchemeSeed: const Color(0xFF167970)),
    home: const ComparisonPage(),
  );
}

class ComparisonPage extends StatefulWidget {
  const ComparisonPage({super.key});
  @override
  State<ComparisonPage> createState() => ComparisonPageState();
}

class ComparisonPageState extends State<ComparisonPage> {
  List<Map<String, dynamic>> assets = [];
  int selectedAsset = 0;
  String animationName = '';
  var _viewKey = GlobalKey<_ComparisonViewState>();
  late final Future<void> _manifest;
  ComparisonController? get controller => _viewKey.currentState?.controller;

  @override
  void initState() {
    super.initState();
    demoPage = this;
    _manifest = _initialize();
  }

  Future<void> _initialize() async {
    assets = (jsonDecode(
      await rootBundle.loadString('assets/manifest.json'),
    ) as List).cast<Map<String, dynamic>>();
    animationName = assets.first['animations'][0]['name'] as String;
  }

  Future<void> select(int index, String name) async {
    final nextKey = GlobalKey<_ComparisonViewState>();
    setState(() {
      selectedAsset = index;
      animationName = name;
      _viewKey = nextKey;
    });
    // Wait for the selected widget to mount before callers inspect its controller.
    await WidgetsBinding.instance.endOfFrame;
    await nextKey.currentState?._load;
  }

  @override
  void dispose() {
    demoPage = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<void>(
    future: _manifest,
    builder: (context, snapshot) {
      final l = AppLocalizations.of(context)!;
      if (snapshot.hasError) {
        return Scaffold(
          body: Center(child: Text(l.error('${snapshot.error}'))),
        );
      }
      if (snapshot.connectionState != ConnectionState.done) {
        return Scaffold(body: Center(child: Text(l.loading)));
      }
      return _ComparisonView(
        key: _viewKey,
        assets: assets,
        selectedAsset: selectedAsset,
        animationName: animationName,
        onSelect: select,
      );
    },
  );
}

class _ComparisonView extends StatefulWidget {
  const _ComparisonView({
    super.key,
    required this.assets,
    required this.selectedAsset,
    required this.animationName,
    required this.onSelect,
  });
  final List<Map<String, dynamic>> assets;
  final int selectedAsset;
  final String animationName;
  final Future<void> Function(int, String) onSelect;
  @override
  State<_ComparisonView> createState() => _ComparisonViewState();
}

class _ComparisonViewState extends State<_ComparisonView> {
  ComparisonController? controller;
  late final Future<ComparisonController> _load;
  List<Map<String, dynamic>> get assets => widget.assets;
  int get selectedAsset => widget.selectedAsset;
  Future<void> select(int index, String name) => widget.onSelect(index, name);

  @override
  void initState() {
    super.initState();
    _load = _initialize();
  }

  Future<ComparisonController> _initialize() async {
    final result = await ComparisonController.load(
      assets[selectedAsset],
      widget.animationName,
    );
    if (mounted) {
      controller = result;
    } else {
      result.dispose();
    }
    return result;
  }

  @override
  void dispose() {
    // 2026-09-13: The keyed view owns the native resources consumed by its
    // subtree; replacing a selection releases them through widget disposal.
    controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    return Scaffold(
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: FutureBuilder<ComparisonController>(
          future: _load,
          builder: (context, snapshot) {
            if (snapshot.hasError) {
              return Center(child: Text(l.error('${snapshot.error}')));
            }
            if (snapshot.connectionState != ConnectionState.done ||
                !snapshot.hasData) {
              return Center(child: Text(l.loading));
            }
            final c = snapshot.requireData;
            return ListenableBuilder(
              listenable: c,
              builder: (context, _) => Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    l.title,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  Text(l.subtitle),
                  Row(
                    children: [
                      Text(l.asset),
                      const SizedBox(width: 12),
                      DropdownButton<int>(
                        value: selectedAsset,
                        items: [
                          for (var i = 0; i < assets.length; i++)
                            DropdownMenuItem(
                              value: i,
                              child: Text(assets[i]['source'] as String),
                            ),
                        ],
                        onChanged: c.exporting
                            ? null
                            : (i) {
                                if (i != null) {
                                  select(
                                    i,
                                    assets[i]['animations'][0]['name']
                                        as String,
                                  );
                                }
                              },
                      ),
                      const SizedBox(width: 24),
                      Text(l.animation),
                      const SizedBox(width: 12),
                      DropdownButton<String>(
                        value: widget.animationName,
                        items: [
                          for (final a
                              in assets[selectedAsset]['animations'] as List)
                            DropdownMenuItem(
                              value: a['name'] as String,
                              child: Text(a['name'] as String),
                            ),
                        ],
                        onChanged: c.exporting
                            ? null
                            : (name) {
                                if (name != null) select(selectedAsset, name);
                              },
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: Row(
                      children: [
                        _panel(c, l.original, false),
                        const SizedBox(width: 20),
                        _panel(c, l.converted, true),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    l.ready(
                      c.duration.toStringAsFixed(1),
                      c.time.toStringAsFixed(3),
                    ),
                  ),
                  Row(
                    children: [
                      FilledButton.icon(
                        onPressed: c.exporting
                            ? null
                            : () => c.setPlaying(!c.playing),
                        icon: Icon(c.playing ? Icons.pause : Icons.play_arrow),
                        label: Text(c.playing ? l.pause : l.play),
                      ),
                      const SizedBox(width: 16),
                      Text(l.timeline),
                      Expanded(
                        child: Slider(
                          value: c.time,
                          max: c.duration,
                          onChanged: c.exporting
                              ? null
                              : (value) {
                                  c.setPlaying(false);
                                  c.seek(value);
                                },
                        ),
                      ),
                      Text(l.dark),
                      Switch(value: c.dark, onChanged: c.setDark),
                    ],
                  ),
                  Row(
                    children: [
                      Text(l.pull),
                      Expanded(
                        child: Slider(
                          value: c.pullDistance,
                          max: 460,
                          onChanged: c.exporting ? null : c.setPull,
                        ),
                      ),
                      OutlinedButton(
                        onPressed: c.exporting
                            ? null
                            : () async {
                                try {
                                  await c.exportEvidence();
                                } catch (_) {
                                  /* displayed below */
                                }
                              },
                        child: Text(c.exporting ? l.exporting : l.export),
                      ),
                    ],
                  ),
                  if (c.lastExportPath != null)
                    SelectableText(l.saved(c.lastExportPath!)),
                  if (c.exportError != null) Text(l.error(c.exportError!)),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _panel(ComparisonController c, String label, bool useRive) => Expanded(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Expanded(
          child: ColoredBox(
            color: c.dark ? const Color(0xFF202934) : const Color(0xFFF2F5F7),
            child: SizedBox.expand(
              child: CustomPaint(painter: _AssetPainter(c, useRive)),
            ),
          ),
        ),
      ],
    ),
  );
}

class _AssetPainter extends CustomPainter {
  final ComparisonController controller;
  final bool useRive;
  _AssetPainter(this.controller, this.useRive) : super(repaint: controller);
  @override
  void paint(Canvas canvas, Size size) =>
      controller.paint(canvas, size, useRive);
  @override
  bool shouldRepaint(_AssetPainter oldDelegate) =>
      oldDelegate.controller != controller || oldDelegate.useRive != useRive;
}
