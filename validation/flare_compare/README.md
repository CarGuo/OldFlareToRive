# 可选 Flare / Rive 对比工具

这里保留迁移所需的独立原版运行库。它不属于默认 demo 或 GSY 的依赖。

```sh
flutter pub get
flutter run -d macos --dart-define=EVIDENCE_DIR=/absolute/path/to/frames
```

选择资源和动画，再点击导出；默认不指定目录时写入系统临时目录。导出覆盖源关键帧、相邻半帧、关键帧间三分点及播放结束，既比较直接时间定位，也比较同名 State Machine 连续推进。

DebugProfile 允许写入指定目录，Release 保留 macOS sandbox。旧运行库的固定版本与两处历史格式修复见[第三方说明](../../THIRD_PARTY.md)。逐帧脚本退出码 1 表示严格像素阈值未通过，不能把“能打开”当作精确一致。
