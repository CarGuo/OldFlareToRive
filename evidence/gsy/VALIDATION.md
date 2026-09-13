# GSY Rive refresh — 2026-09-13

## 看代码

GSY 的三个 FLR 已替换成同名 RIV；实际刷新入口由 `GSYRivePullAnimation` / `GSYRivePullPainter` 播放 `Earth Moving`，保留原进度映射、刷新时 2 倍速、cover / topCenter 和裁剪。两个旧控制器与 Flare 依赖删除；另外两个原本未使用的素材保留为 RIV，没有新增业务入口。

最终验证运行于 `/private/tmp/gsy-rive-tools/gsy-verification`，基于 GSY `ffd0eb87e84a370a9603c0bd27860cd5e606e816`。主工作区同时存在 IDE 的另一 SDK 构建，为避免生成配置相互覆盖，使用独立 checkout 验证。`source-hashes.json` 核对了主工作区与验证 checkout 的 9 个代码、锁文件、资源文件逐字节相同。锁文件差异仅删除 Flare 的 9 行。

## 看编译

- Flutter **3.47.2** / Dart **3.13.2**；Rive **0.14.11** / rive_native **0.1.11**。
- `flutter pub get --offline --enforce-lockfile` 成功。
- `flutter test --no-pub test/widget/pull/gsy_rive_pull_animation_test.dart` 通过，见 [pull-test.txt](pull-test.txt)。
- `flutter analyze --no-pub` 报告既有 **17 项 warning/info，0 errors**；没有命中本次改动文件，见 [flutter-analyze.txt](flutter-analyze.txt)。未把分析退出码 1 写成全仓库零问题。
- release APK 构建成功（22,672,764 bytes），见 [release-build.txt](release-build.txt) 与 [release-assets.json](release-assets.json)。ZIP 内无 `.flr`，三个 `.riv` 与转换成品哈希一致。APK 的 Flutter ELF build ID 与 pinned SDK 的 arm64 release engine 一致。
- 无模型或 ARB 输入变更，不需要 build_runner / gen-l10n。

## 看运行

设备：**emulator-5554**，Android API 35 arm64，AVD `GSY_Rive_Pixel_Fold_API35`。

- DTD：`ws://127.0.0.1:57677/rt256IS7ZeY=`
- VM Service：`ws://127.0.0.1:57678/L9T4mQFoJs4=/ws`
- 入口：`tool/ai/smoke/rive_refresh.dart`，真实生产刷新组件与 adaptive shell，本地 24 行 fixture，不依赖登录或网络。
- 通过官方 Dart MCP `dtd connect`、`vm_service`、`widget_inspector get_widget_tree`、`get_runtime_errors` 获取证据。手势由入口的 `ScrollPosition.drag` API 驱动，没有 adb 坐标输入脚本。
- [dtd.json](dtd.json) 是成功连接记录；[errors-before.json](errors-before.json)、[opened-errors.json](opened-errors.json)、[closed-refresh-errors.json](closed-refresh-errors.json)、[closed-errors.json](closed-errors.json)、[errors-final.json](errors-final.json) 均为 **No runtime errors found**。

| 姿态 / 步骤 | 实测结果 | 证据 |
|---|---|---|
| OPENED 初始 | 2 个 Navigator；无刷新、无指示器 | `opened-idle-tree.json`, `opened-idle-state.json` |
| OPENED 拖拽 100 logical px | pulledExtent=100，playAuto=false | `opened-pull-state.json`, `opened-pull-tree.json` |
| OPENED 继续拖拽并越过阈值 | pulledExtent≈163.112，阈值 140 | [opened-armed.png](opened-armed.png), `opened-armed-state.json` |
| OPENED 松手刷新 | refreshCount=1，pending=true，playAuto=true；RiveArtboardWidget 挂载 | [opened-refresh.png](opened-refresh.png), `opened-refresh-tree.json`, `opened-refresh-state.json` |
| OPENED 动画推进 | 原生时间两次读数约 9.15982、0.25982，均为自动播放 | `opened-native-time-a.json`, `opened-native-time-b.json`, [opened-refresh-next.png](opened-refresh-next.png) |
| OPENED 完成 | pending=false，offset=0，指示器移除 | `opened-finished-state.json` |
| CLOSED 硬件折叠 | identifier=0；1 个 Navigator | `closed-hardware.txt`, `closed-idle-tree.json`, `closed-idle-state.json` |
| CLOSED 小幅下拉后取消 | pulledExtent=80；松手后 count 仍为 1，未触发刷新 | [closed-small-pull.png](closed-small-pull.png), `closed-small-pull-state.json`, `closed-cancelled-state.json` |
| CLOSED 越过阈值 | pulledExtent≈185.585，playAuto=false | [closed-armed.png](closed-armed.png), `closed-armed-tree.json`, `closed-armed-state.json` |
| CLOSED 松手刷新 | count=2，pending=true，playAuto=true；RiveArtboardWidget 挂载 | [closed-refresh.png](closed-refresh.png), `closed-refresh-tree.json`, `closed-refresh-state.json` |
| CLOSED 完成 | pending=false，offset=0，指示器移除 | `closed-finished-state.json` |
| 恢复 OPENED | `emu unfold` 后 identifier=2，2 个 Navigator | `restored-opened-hardware.txt`, `restored-opened-tree.json`, `restored-opened-state.json` |

截图原始绝对目录：`/Users/guoshuyu/workspace/flutter-work/gsy_github_app_flutter/tool/ai/smoke/evidence/20260913-rive-refresh/`。展开使用屏幕 ID `4619827259835644672`，折叠使用 `4619827551948147201`；截图只是补充，业务状态由 Dart MCP 观测。

第一次 Android 调试会话遭遇模拟器 `system_server` SIGSEGV，连接断开，之后重新运行上述成功会话。初始截图中的系统 ANR 弹窗保留为 `diagnostic-system-ui-anr.png`；通过关闭系统弹窗广播清除后重新抓取通过截图，未用该诊断图充当最终视觉证据。它不是 Dart 业务异常。

## 已知缺口

- 此次验证经过 adaptive shell，已覆盖真实 CLOSED / OPENED 两档硬件姿态；不豁免双姿态。
- iOS、Web、Windows、Linux、Rive 自有 GPU Renderer 未验证。Android 这里使用 Rive 的 Flutter Renderer。
- 本地 fixture 验证真实刷新组件的正常完成与取消；网络错误业务分支不在本次修改范围内，未新增网络验证。
- Space、Logo 原本无 GSY 运行入口；8 段动画在独立 macOS demo / 原版对照工具中验证。地球通过严格像素阈值，Space、Logo 的颜色量化、透明边缘差异仍保留，详见独立仓库 `docs/VALIDATION.md`。
