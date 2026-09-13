# Rive-only demo

本工程只使用 Rive 播放三个已迁移素材，不依赖 Flare 或转换工具。

```sh
flutter pub get
flutter run -d macos
```

测试版本 Flutter 3.47.2 / Rive 0.14.11。动画选择、暂停、时间轴拖动和循环/单次播放均可在界面操作。资源来自仓库根目录的 `build.py`；完整迁移过程与证据见[主 README](../README.md)。
