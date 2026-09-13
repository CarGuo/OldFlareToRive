# Migration log — 2026-09-13

## Goal and method

先还原地球，再迁移另外两个文件，最后在 GSY 移除 Flare。没有找到可直接处理这些旧二进制的 CLI 转换命令，因此从旧运行库的实际读取格式出发，输出 RML，再交给官方 CLI 编译。原始文件以 SHA-256 固定，转换器拒绝未知块、无效数值和未支持特性，避免静默丢对象。

## 1. Earth：层级、裁剪、绘制顺序

`loading_world_now.flr` 是 v21，1024×768，698 个组件，`Earth Moving` 60 fps / 10 秒循环。地图和月亮的平移保留全部源关键时刻，包括月亮第 299 → 300 帧的跳变。不能把它平滑掉。

Flare 椭圆使用 0.55 贝塞尔控制点。直接换成 Rive Ellipse 的控制点会有几何差异，因此展开成相同三次曲线。Flare 的绘制顺序是全局的，不能仅靠 RML 父子节点顺序；静态顺序用无环 DrawRules 链表示。

旧文件的裁剪组应把多形状合并。曾直接拿较新 Flare fork 当原版，结果地球裁剪异常；查对历史开源实现后为对比工具恢复旧语义。转换器和对比工具各自从原始文件读取，未让原版依赖转换结果。

第一次 RML 仅有 Entry/Animation 状态，通过 CLI 后在实际运行库中仍失败。补齐 Any/Exit 状态，并在运行时验证默认 State Machine。因此 verify/inspect 不能替代真实播放。

## 2. Space：v18 布局与动画绘制顺序

v18 Shape 的历史保留字节必须消费，否则后续 drawOrder 读取错位。查对 2019 年官方读取实现后修复 Python 读取器和可选原版运行库。

加入静态圆角矩形、径向渐变、cubic easing 及动态 drawOrder。直接为每种排列建立移动形状间的 DrawTarget，会让原生依赖图出现环；改为每个绘制层级建立不可变的空 Shape 锚点，移动形状只指向锚点。结构测试验证每个源排序关键帧的排列和目标的无环关系，运行对比检查实际遮挡。

## 3. Logo：圆角 morph、颜色与透明度

路径从 Flutter 标志变为蜂鸟，除了点位置还有圆角半径变化。Rive 与 Flare 的角半径裁剪规则不同，不能直接映射 radius。转换器按 Flare 顺序展开每个角为两个 cubic 顶点，以原帧率的 1024 倍整数时间格自适应细分；原关键时刻仍精确落在整数格上。每段检查 1/4、1/2、3/4 点，超出 0.001 画板单位则细分。另用不同的离网格时刻单测和运行帧检查中间插值。

填充颜色 alpha 与填充 opacity 分别存储、分别动画。曾使用等色渐变承载 opacity，实测引入 shader dithering；改为原 Shape 的变换 Node 加子 Shape，让子 Shape.opacity 表达独立填充透明度，SolidColor 保留源颜色 alpha。现有 Rive 8-bit 色值与 Flare 浮点画笔仍有量化差异，严格报告保留失败。

## 4. GSY 与纯 Rive demo

GSY 下拉组件改用 `GSYRivePullAnimation`。保留原 0.6 距离因子、阈值处减一次的分支、平方进度和刷新时 2 倍速度；超长下拉保留原始时间供自动播放接续，仅渲染位置钳制到动画范围。组件明确裁剪自己的 viewport，保留 FlareActor 原默认裁剪行为。

删除旧 Flare 依赖、两个旧控制器和三个 `.flr` 资源；旧原件保存在本仓库 `sources/`。默认 `demo/` 只含 Rive 运行库及 `.riv`；Flare 对比工程独立放在 `validation/`。

纯 Rive demo 的切换验证暴露过旧播放器过早释放：旧 widget 还可能读取已释放 Animation。修复为每个选择对应一个 keyed Stateful view，由该 view 负责加载和释放 native 资源，选项元数据保持不可变。不是用延迟释放或吞异常处理。随后重新验证 8 段动画和单次结束重播。

## Supported boundary

支持此批文件出现的 Node、Shape、Path、Ellipse、Rectangle、SolidFill、Linear/RadialGradient、旧式裁剪、普通混合、变换、opacity、颜色、直线顶点 morph、闭合圆角 morph、hold/linear/cubic easing、全局绘制顺序。只有单画板、原点为零的 pre-v23（v18–v22）文件进入这条路径；这里只实测了 v18 与 v21。

骨骼/蒙皮、图片、描边、不支持的混合、椭圆径向渐变、多个 clip 引用、嵌套 drawable、独立静态圆角 Path 等会报错，不声称通用兼容。圆角 Rectangle 有独立的已实现转换。ActorAnimation 官方读取器不读取的末尾字节保存在 source.json 的 `runtime_unread_tail_hex`，未给其编造语义。

## Reproduction and evidence

根 README 给出构建、纯 Rive 运行和独立对比命令。`evidence/loading_world` 是第一阶段历史记录，旧本机路径/日志只用于追溯；当前路径和结论以根 README 与 `docs/VALIDATION.md` 为准。`evidence/diagnostics` 保留失败方案的诊断，不作为最终通过证据。
