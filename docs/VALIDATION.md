# Validation — 2026-09-13

## Measured comparison

最终对比使用 Flutter 3.47.2 / Dart 3.13.2、Rive 0.14.11 / rive_native 0.1.11，两个真实运行库在 macOS arm64 上绘制。原图和迁移图使用相同原始画板尺寸，比较原始 RGBA，不对齐、不做颜色校正。统计范围为两图非透明像素的并集。阈值固定为：任一通道差值 >2/255 的像素占比 ≤0.0002，平均绝对 RGBA 差 ≤0.002（8-bit 通道单位）。完全空白的整组输出会报错。

| 素材 | 动画 | 帧对数 | 最差平均 RGBA 差 | 最差 >2 像素比例 | 严格阈值 |
|---|---|---:|---:|---:|---|
| flutter_logo | [FlutterToHummingbird](../evidence/all-assets/flutter_logo/FlutterToHummingbird/comparison-sheet.png) | 99 | 0.400258 | 0.00379341 | 未通过 |
| flutter_logo | [Placeholder](../evidence/all-assets/flutter_logo/Placeholder/comparison-sheet.png) | 61 | 0.778035 | 0.00589702 | 未通过 |
| loading_world | [Earth_Moving](../evidence/all-assets/loading_world/Earth_Moving/comparison-sheet.png) | 31 | 0.000278 | 0.00004157 | 通过 |
| space_demo | [idle](../evidence/all-assets/space_demo/idle/comparison-sheet.png) | 43 | 0.018372 | 0.00000793 | 未通过 |
| space_demo | [idle_comet](../evidence/all-assets/space_demo/idle_comet/comparison-sheet.png) | 53 | 0.018285 | 0.00000793 | 未通过 |
| space_demo | [loading](../evidence/all-assets/space_demo/loading/comparison-sheet.png) | 33 | 0.018345 | 0.00003437 | 未通过 |
| space_demo | [pull](../evidence/all-assets/space_demo/pull/comparison-sheet.png) | 23 | 0.024980 | 0.00199051 | 未通过 |
| space_demo | [success](../evidence/all-assets/space_demo/success/comparison-sheet.png) | 63 | 0.018507 | 0.00005552 | 未通过 |

共 **406 对**。每个目录的 `samples.json` 记录抽样时刻，`pixel-comparison.json` 保留逐帧数值，`comparison-sheet.png` 是代表帧对照。包括 timeline seek、同名 State Machine 顺序推进和结束后的循环/保持；没有声称每一帧、每个平台像素完全相同。原始帧序列未提交 Git，哈希清单位于 `evidence/raw-frame-hashes.json`，可以用独立对比工程重新导出。

Space 的径向渐变与抗锯齿边缘，以及 Logo 浮点画笔与 Rive 8-bit 色值的透明度组合，仍有差异。严格失败继续保留，视觉相近不等于该阈值通过。对比图应结合逐帧原始报告一起判断。

## Build and runtime checks

- `evidence/build/converter-tests.txt`：13 项转换测试，包含 v18 布局、原关键时刻、圆角几何与非网格时间、动态排序、独立 paint opacity 和不支持输入拒绝。
- `evidence/build/rive-build.txt`：CLI 1.0.2 对三个项目 verify / inspect / build，0 errors / 0 warnings。
- `evidence/demo/`：纯 Rive demo 的 macOS Dart MCP widget tree、runtime errors、8 段时间轴、单次播放结束与重播、截图。`errors-diagnostic.json` 是修复前的生命周期缺陷；`errors-final.json` 是修复后的结果。
- `evidence/oracle/`：独立对比工具的并发选择结果与无异常报告，以及最终 8 段导出完成记录。加载中卸载、导出中切换也已实测：见 `dispose-during-load-result.json`、`dispose-during-export-result.json` 和 [导出取消日志](../evidence/oracle/export-cancellation-log.txt)。导出中的旧 native 资源在 finally 释放，最终 runtime errors 为空。
- `evidence/loading_world/`：第一阶段地球验证，包括第 299/300 帧跳变、1201 个半帧数值采样与历史渲染检查。该目录是历史快照，不代表 GSY 的最终状态。
- GSY 实际刷新组件已通过 Android CLOSED / OPENED 验证：[完整运行记录](../evidence/gsy/VALIDATION.md)、[折叠截图](../evidence/gsy/closed-armed.png)、[展开截图](../evidence/gsy/opened-armed.png)。小幅拖拽取消、释放刷新、自动推进、完成收起均有实际状态和 widget tree，Dart MCP runtime errors 为空；设备最终恢复 OPENED。入口是 GSY 的 `tool/ai/smoke/rive_refresh.dart`。
- GSY release APK 构建成功，包内无 FLR、三个 RIV 与这里的成品哈希一致；依赖树核对见 [dependencies.json](../evidence/build/dependencies.json)。全仓库 analyze 仍有既有 17 项 warning/info，0 errors，本次文件未命中；未把它表述为全仓库零问题。

## Remaining coverage boundaries

没有逐帧验证所有中间时间，也没有验证 Rive 自有 GPU Renderer、Web、iOS、Windows、Linux。macOS 对比和 GSY 均使用 Flutter Renderer。未支持的 Flare 特性明确拒绝，而非静默跳过；新增素材需要重新检查转换器覆盖范围。
