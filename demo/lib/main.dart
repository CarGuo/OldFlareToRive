import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:rive/rive.dart' as rive;

import 'l10n/app_localizations.dart';

// 2026-09-13: The shipped example uses only Rive. The legacy comparison
// application lives separately in validation/flare_compare.
PlayerPageState? demoPage;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await rive.RiveNative.init();
  runApp(const MigrationApp());
}

class RivePlayer extends ChangeNotifier {
  RivePlayer(this.file, this.artboard, this.animation, this.loop) {
    _resolver.artboardChanged(artboard);
    seek(0);
  }

  final rive.File file;
  final rive.Artboard artboard;
  final rive.Animation animation;
  final bool loop;
  final _resolver = rive.BasicArtboardPainter(
    fit: rive.Fit.contain,
    alignment: Alignment.center,
  );
  late final _ticker = Ticker(_tick);
  Duration _previous = Duration.zero;
  double time = 0;
  bool playing = false;
  bool dark = true;
  double get duration => animation.duration;

  static Future<RivePlayer> load(
    Map<String, dynamic> asset,
    String name,
  ) async {
    final file = await rive.File.asset(
      'assets/${asset['output']}',
      riveFactory: rive.Factory.flutter,
    );
    if (file == null) throw StateError('Cannot decode ${asset['output']}');
    rive.Artboard? artboard;
    rive.Animation? animation;
    try {
      artboard = file.defaultArtboard();
      if (artboard == null) throw StateError('Missing artboard');
      artboard.frameOrigin = false;
      animation = artboard.animationNamed(name);
      if (animation == null) throw StateError('Missing animation: $name');
      final spec = (asset['animations'] as List).firstWhere(
        (a) => a['name'] == name,
      );
      if ((animation.duration - (spec['duration'] as num)).abs() > 1e-5) {
        throw StateError('Unexpected duration: $name');
      }
      return RivePlayer(file, artboard, animation, spec['loop'] as bool);
    } catch (_) {
      animation?.dispose();
      artboard?.dispose();
      file.dispose();
      rethrow;
    }
  }

  void seek(double seconds) {
    time = seconds.clamp(0, duration);
    animation.time = time;
    animation.apply();
    _resolver.advance(0);
    notifyListeners();
  }

  void _tick(Duration elapsed) {
    final next = time + (elapsed - _previous).inMicroseconds / 1e6;
    _previous = elapsed;
    if (!loop && next >= duration) {
      seek(duration);
      setPlaying(false);
    } else {
      seek(next % duration);
    }
  }

  void setPlaying(bool value) {
    // A completed one-shot must be playable again without scrubbing first.
    if (value && time >= duration) seek(0);
    playing = value;
    if (value && !_ticker.isActive) {
      _previous = Duration.zero;
      _ticker.start();
    } else if (!value) {
      _ticker.stop();
    }
    notifyListeners();
  }

  void setDark(bool value) {
    dark = value;
    notifyListeners();
  }

  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.clipRect(Offset.zero & size);
    final renderer = rive.Renderer.make(canvas);
    _resolver.paint(renderer, size, 1);
    renderer.dispose();
    canvas.restore();
  }

  @override
  void dispose() {
    _ticker.dispose();
    _resolver.dispose();
    animation.dispose();
    artboard.dispose();
    file.dispose();
    super.dispose();
  }
}

class MigrationApp extends StatelessWidget {
  const MigrationApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    theme: ThemeData(colorSchemeSeed: const Color(0xFF167970)),
    home: const PlayerPage(),
  );
}

class PlayerPage extends StatefulWidget {
  const PlayerPage({super.key});
  @override
  State<PlayerPage> createState() => PlayerPageState();
}

class PlayerPageState extends State<PlayerPage> {
  List<Map<String, dynamic>> assets = [];
  int selectedAsset = 0;
  String animationName = '';
  var _viewKey = GlobalKey<_PlayerViewState>();
  late final Future<void> _manifest;
  RivePlayer? get player => _viewKey.currentState?.player;

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
    final nextKey = GlobalKey<_PlayerViewState>();
    setState(() {
      selectedAsset = index;
      animationName = name;
      _viewKey = nextKey;
    });
    // Wait for the selected widget to mount before callers inspect its player.
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
      return _PlayerView(
        key: _viewKey,
        assets: assets,
        selectedAsset: selectedAsset,
        animationName: animationName,
        onSelect: select,
      );
    },
  );
}

class _PlayerView extends StatefulWidget {
  const _PlayerView({
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
  State<_PlayerView> createState() => _PlayerViewState();
}

class _PlayerViewState extends State<_PlayerView> {
  RivePlayer? player;
  late final Future<void> _load;
  List<Map<String, dynamic>> get assets => widget.assets;
  int get selectedAsset => widget.selectedAsset;
  Future<void> select(int index, String name) => widget.onSelect(index, name);

  @override
  void initState() {
    super.initState();
    _load = _initialize();
  }

  Future<void> _initialize() async {
    final result = await RivePlayer.load(
      assets[selectedAsset],
      widget.animationName,
    );
    if (mounted) {
      player = result;
    } else {
      result.dispose();
    }
  }

  @override
  void dispose() {
    // 2026-09-13: The keyed view owns the native resources consumed by its
    // subtree; replacing a selection releases them through widget disposal.
    player?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: FutureBuilder<void>(
            future: _load,
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return Center(
                  child: SelectableText(l.error('${snapshot.error}')),
                );
              }
              if (snapshot.connectionState != ConnectionState.done) {
                return Center(child: Text(l.loading));
              }
              final c = player!;
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
                    Wrap(
                      spacing: 24,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        DropdownButton<int>(
                          value: selectedAsset,
                          hint: Text(l.asset),
                          items: [
                            for (var i = 0; i < assets.length; i++)
                              DropdownMenuItem(
                                value: i,
                                child: Text(assets[i]['output'] as String),
                              ),
                          ],
                          onChanged: (i) {
                            if (i != null)
                              select(
                                i,
                                assets[i]['animations'][0]['name'] as String,
                              );
                          },
                        ),
                        DropdownButton<String>(
                          value: widget.animationName,
                          hint: Text(l.animation),
                          items: [
                            for (final a
                                in assets[selectedAsset]['animations'] as List)
                              DropdownMenuItem(
                                value: a['name'] as String,
                                child: Text(a['name'] as String),
                              ),
                          ],
                          onChanged: (name) {
                            if (name != null) select(selectedAsset, name);
                          },
                        ),
                        Text(c.loop ? l.loop : l.oneShot),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Expanded(
                      child: ColoredBox(
                        color: c.dark
                            ? const Color(0xFF202934)
                            : const Color(0xFFF2F5F7),
                        child: SizedBox.expand(
                          child: CustomPaint(painter: _RivePainter(c)),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      l.ready(
                        c.duration.toStringAsFixed(3),
                        c.time.toStringAsFixed(3),
                      ),
                    ),
                    Row(
                      children: [
                        FilledButton.icon(
                          onPressed: () => c.setPlaying(!c.playing),
                          icon: Icon(
                            c.playing ? Icons.pause : Icons.play_arrow,
                          ),
                          label: Text(c.playing ? l.pause : l.play),
                        ),
                        Expanded(
                          child: Slider(
                            value: c.time,
                            max: c.duration,
                            onChanged: (v) {
                              c.setPlaying(false);
                              c.seek(v);
                            },
                          ),
                        ),
                        Text(l.dark),
                        Switch(value: c.dark, onChanged: c.setDark),
                      ],
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _RivePainter extends CustomPainter {
  _RivePainter(this.player) : super(repaint: player);
  final RivePlayer player;
  @override
  void paint(Canvas canvas, Size size) => player.paint(canvas, size);
  @override
  bool shouldRepaint(_RivePainter oldDelegate) => oldDelegate.player != player;
}
