当前接入及持续宽战线版本为 preview.4，新增原生 MoveAndAttack 和 IsEnCombat 状态读取。最新实现、同构建回执和普通对局验收边界见 [CONTINUOUS_FRONT.md](CONTINUOUS_FRONT.md)。下文保留此前接入实验的历史证据。

# 自定义算法的游戏接入实验

2026-11-06。用户明确指出离线算法没有更新可玩 mod，要求继续解决接入。

**当前结果：自动装载 → 原生遭遇战生命周期 → 附加定时动作（不重建世界）→ Python → 玩家/AI 实时数据 → 当前地图通行数据 → 自定义空间分配 → 有期限的调度接管 → 动态移动与反馈 → 正常退出，已经接通并安装。NDF 基础仍为 test3，当前运行组件为 `spatial-runtime-preview.3`。完整战线调度和普通 4v4 实战验收仍待完成。** 最新方向展开、测试夹具 SIP 地址宽度修复及原始失败证据见 [本轮记录](DIRECTIONAL_FRONTAGE.md)。以下保留接入研究历史，不代替最新验收状态。

## 当前交付：原版数据包上的自动接入

本机新增根目录 `version.dll`，通过游戏已有的 Windows VERSION 导入自动加载，再将这些系统接口转发到 System32。DLL 只在匹配当前可执行文件版本、BattleAtmosphere 已启用、`Runtime/runtime.ini` 开启且进入支持的单人遭遇战时运行算法。没有修改原版 EXE/DAT、Steam 启动参数和启用列表，没有操控界面或注入用户现有进程。

自动入口保留 `TLaunchGDScript` 的原生 load/start/stop。`DllMain` 只做已检查类型的入口包装；完整哈希、文件访问、Python 编译和执行均在原生加载阶段进行。先前“等 VERSION 第一次调用才安装入口”的尝试错过了启动时机，已废弃；最终版本已通过自动加载测试。

零售环境的 Python 没有可用 `imp`、`compile`、`eval` 入口，不能沿用开发数据根的源码导入假设。当前把规范化换行后的源码嵌入 DLL，通过已核验的原生 Python 2.5 解析、编译、模块注册和求值函数加载 `ba_allocator`、`ba_space`、`ba_autorun`。因此不再依赖 `-rootdata`、`-uselocaldata`、覆盖 Cluster 或地图脚本。

最终候选 DLL SHA256：`90c821bd669819727045a9cbe5d74d8b545b68279b6537809eca8f24a3741a9f`。三次测试均使用这一文件：

| 回执 | 启动位置及场景 | 证据 |
|---|---|---|
| [黑森林征服](Development/runtime-auto-release-blackforest.json) | 隔离 EXE 副本；原版地图与数据 | 首次回调就分配；15 条命令接受，12 辆 AI 真实移动，6 次到位；正常退出 0 |
| [Hesse 歼灭](Development/runtime-auto-release-hesse.json) | 隔离 EXE 副本；原版地图与数据 | 首次回调就分配；13 条命令接受，12 辆 AI 真实移动，8 次到位；正常退出 0 |
| [正式目录安装后](Development/runtime-installed-root.json) | 本机真正的 WARNO.exe；仍使用独立无界面测试配置 | 自动入口、80 次回调、移动、Python 清理和原生停止均出现；53.328 秒正常退出 0 |

测试通过真实 Saved Games 模组选择与 runtime.ini 检查，没有外部注入。各次夹具含两个同阵营最高难度 AI 拥有者，另有身份 0 与 7 的单位，下令返回 -3。夹具只为无界面空大厅提供测试阵营，不是普通大厅实战。原始回执保存源文件、参数和哈希；[复核工具](Development/native_bridge/verify_runtime.py) 将两地图回执与实际构建输入逐一核对，[安装回执](Runtime/installation.json) 记录正式 DLL。

运行控制器按阵营统一在途预约，从当前导航格点创建独占阵位，用容量约束最小费用最大流求解。初版要求整批可行，黑森林测试直到第 49 次回调才开始纠偏；最终改成即时尝试更小批次，两地图均在第 1 次开始。未选中单位维持原生任务，不能用等待形成新的集结堆积。

**当前范围是局部纠偏，不是完整战线算法。** 全前线提取、掩护/射界、瓶颈时间窗、完整兵种协同未实现；4v4 规模、连续换局、真实交战与运输状态尚未验收。35 m 到位容差、归还原生 AI 和在途交叉都可能让实际间隔小于目标。启动回放的完整界面路径也仍待核验，当前仅跳过联网标记和命令行回放。使用及回退见 [运行组件说明](Runtime/README.md)。

## 当前入口与调度仲裁证据

- `TLaunchGDScript` 的 load/start/stop 通过有类型的虚表包装保留原生调用。测试空大厅只在显式 `BattleAtmosphereProbeAutoFixture` 模式填充测试阵营；该夹具不能进入正式运行。
- [原生入口回执](Development/runtime-native-fixture-autohook-v3.json)：自动识别场景类别 `Skirmish`，执行入口、原生退出与 Python 清理，退出码 0。
- [现有世界计时回执](Development/runtime-native-auto-timer-ai-v2.json)：固定 0.5 秒计时，12 次回调，真实最高难度 AI 单位枚举 6。仿真数据来自当前玩家列表，不需要人为创建枚举组。
- 不得对已运行的世界调用研究接口 `start_script`：它会重置全局世界。正式方向使用 `attach_update` 在当前 GD owner 根动作上附加计时子动作。
- 不得在世界初始化后新建未注册的 `TGDVariableUnitGroup`：曾导致退出时注册计数错误。现有计时器不依赖这类晚建组。
- 从当前 `TScenarioLoadInfo` 读取类别和数据包，从挂载的 `CurrentScenarioData:/out/LevelDesign.ndfbin` 读取部署、据点、增援点；无地图列表、坐标表或地图专用安装。
- 等时仲裁对照均为六辆 M113、最高 AI 6、35 秒、70 次位置采样：不接管的 [对照](Development/runtime-native-ai-id-orders-no-lease35.json) 末次最近邻最小距离约 714 原生单位；临时接管的 [实验](Development/runtime-native-ai-id-orders-lease.json) 约 24572。初始约 1500。这证实此受控测试中原生战略调度会覆盖单次移动，并且接管有作用；不等于整场反扎堆验收。
- 接管使用原生 ignored-by-script 集合，不改变阵营归属、玩家身份或作战属性；新增四秒续租期限，脚本异常和世界停止时归还。尚需验证持续作战、伤亡和换局后的完整恢复。
- [通行与兵种回执](Development/runtime-native-navigation-roles-ttl.json)：正确读到 M113 角色 `transport`、通行类型 3、速度 55；地图网格 85×127、原生格长 15480，六个当前坐标通过原生通行点检查。战略网格不等于精确战术路径，不能把命令返回 1 当作可达证明。
- `UnitRole` 使用独立字符串表（原生属性序列化函数链），通用 token 注册器的同名字串 ID 不可混用。

## 早期原生桥接证据（以下保留研究时的阶段状态）

- 新增 [研究桥接源码](Development/native_bridge/probe_bridge.c) 与 [受限启动器](Development/native_bridge/load_owned_probe.py)。启动器仅向自己刚创建的无界面子进程加载 DLL，核验原版 EXE 的 SHA256 和导入调用点；不修改磁盘上的原版 EXE/DAT，不接管用户已运行的游戏。桥接是私有 ABI 研究实现，不是官方 SDK 或可直接启用的第四版。
- 黑森林征服和 Hesse 歼灭均已通过脚本启动、原生动作、终止回调及退出码 0 的检查：[征服回执](Development/runtime-native-two-camp-cleanup.json)、[歼灭回执](Development/runtime-native-hesse-destruction-lifecycle.json)。测试自己创建阵营，不等于普通大厅配置已经接入。
- 每 0.5 秒运行一次原生计时动作，并在仿真线程回调 Python，4 次回调后正常退出：[定时回执](Development/runtime-native-periodic-before-load.json)。使用引擎自己的 Python 序列化锁；不是另开线程修改仿真数据。
- 生成真实 M113、读取实体代际 ID 与位置组件，给出移动命令后持续读取位置：[移动回执](Development/runtime-native-move-unit.json)。坐标变化与目标方向一致。
- 第 6 次回调使用当时位置计算新目标，原生任务验证接受，车辆转向：[动态命令回执](Development/runtime-native-dynamic-move.json)。不是预先排好的固定动作图。
- [兼容生成器](Development/dispersion/build_allocator25.py) 保持原最小费用最大流分配逻辑，转换旧解释器语法和记录类型，并显式保持键遍历顺序；12 个原版/兼容版案例一致。嵌入解释器已实际导入并求解：[解释器回执](Development/runtime-native-allocator-import.json)。
- 12 辆测试车、两个同阵营测试拥有者、4 个区段，每区 3 辆；计算约 4.2 ms，12 条动态命令接受，正常退出：[完整研究闭环](Development/runtime-native-live-allocator.json)。初始最小间距 1000 原生坐标单位，末次 3156；**并未达到计划的 6000**，部分车辆到位后偏离。候选位置与路径边是测试构造，不是地形通行与真实战线的实现。
- `TGDDescriptorAddIgnoredUnitByScript` 能执行，但在这个测试中没有改变上述偏离轨迹：[对照回执](Development/runtime-native-live-allocator-ignore.json)。不能据此声称它解决了原生 AI 抢单，也不能仅凭到位后移动认定根因一定是战略 AI。

此前用异常输出的探针、未调用原生 stop 导致的退出崩溃等属于历史失败；最新生命周期已调用 GD owner 的 stop，再释放引用。退出码 73 只用于受控诊断失败，绝不算通过。下一步继续解决普通对局身份和地图数据、命令归属与反馈，而非发布一个测试专用场景。

**通用性要求：最终方案须随任意地图的征服/歼灭遭遇战自动运行。黑森林只是测试输入，不得固化其坐标、区域或 GUID，也不能要求用户逐地图安装。**

## 本轮确定的加载链

从当前版本 `Data/PC/201602/Glad.dat` 只读解析得到：

1. `NDF/ClusterLoadGameplay.ndfbin` 的 `TLevelLauncherIA.LauncherItemMap`，键 3 指向 `TLaunchGDScript`，路径前缀为 `Scenario/GDScript`，覆盖场景名为 `Skirmish`，命名空间为 `GDScript`。
2. 实际包 `NDF/Scenario/GDScript/Skirmish.ndfbin` 导出 `$/GDScript/RootDescriptor`，原生动作依次包含加载完成、开场镜头和永久等待。
3. 原生生成配置包含 `CommonData:/Gameplay/GDScripts/EffetMapSkirmish.ndf`，但该事务没有打开 `Moddable`，并不属于普通模组源文件的常规编译范围。
4. `TLaunchGDScript` 的原生加载函数在当前可执行文件 RVA `0xc24020`，调用二进制事务读取函数 `0x1165e0`。不能仅把 Python 或同名 NDF 文件放进 mod 目录，就声称普通遭遇战会执行它。

只读格式调查参考 [moddingSuite NdfbinReader](https://github.com/kilivan4iK/moddingSuite/blob/master/moddingSuite/BL/Ndf/NdfbinReader.cs)。本地解析器 [read_cndf.py](Development/read_cndf.py) 支持当前 CNDF v2 对象表；保留尚未解码的导入索引，不猜测其对应名称。

## 真正通过的实验

隔离目录：`Mods/BAScriptProbe`，没有启用。

入口 `CommonData/BAProbeDriver.ndf` 先执行原生生成初始化，再在独立包名 `BattleAtmosphere/ScriptProbe` 下编译自定义动作图，命名空间仍为 `GDScript`。最后执行 `TClusterStartNamedCluster`，查找并启动该自定义包中的空测试 cluster `$/GDScript/BA_ENTRY_PROBE_20261106`。

最后一次调用由 Python `subprocess` 等待实际进程退出，退出码 **0**，耗时约 **47.4 秒**。详情见 [原生进程回执](Development/late-script-probe.json) 和 [复核脚本](Development/verify_native_script_probe.py)。

这是“游戏的原生对象数据库能装入并找到我们生成的对象”的证据。测试 cluster 不等于战斗动作；该项测试没有创建对局、读取实时部队或下达单位命令。

## 后续突破：共用入口执行自定义 Python

在 `Mods/BAScriptProbe/RuntimeRoot` 建立独立本地数据根，仅用于无界面研究。重建原生 `ClusterLoadGameplay`，保留其他初始化，将 `LauncherItemMap` 键 3 改为 `TPythonRootObject(Module='ba_probe')`。自定义源文件必须位于实际原生路径 `CommonData/Clusters/ClusterLoadGameplay.ndf`；只复制改名的二进制缓存不足以覆盖原生事务。

以该目录为工作目录，使用 `-rootdata . -uselocaldata -ialevel 3`；`3` 是启动器分支，不是 AI 难度。探针另外带 `-headless -nodialogbox -nocrashrpt -noautologin -ignorecloudfiles -noMod`。没有操控界面、修改原版 EXE/DAT，或启用探针模组。

原生错误回执明确给出 `CommonData:/Python/Eugen/ba_probe.py` 的 `launch()` 调用栈和预设诊断标记：

- [launch 执行及接口清单](Development/runtime-python-launch-api.json)：退出码 6，受控 `BA_LAUNCH_INVENTORY` 异常，证明入口执行。
- [回调相关绑定](Development/runtime-python-callback-api.json)：退出码 6，受控 `BA_CALLBACK_INVENTORY` 异常。
- [正常生命周期尝试](Development/runtime-python-positive-lifecycle.json)：返回空包装对象后 60 秒超时，仅终止本次创建的进程。**未通过正常加载/退出，不能把前两项诊断异常说成成功启动游戏。**

上述早期诊断当时只证明共用启动器可执行 Python。后续第二地图、歼灭、真实测试单位及动态命令的进展见本文开头；仍不等于普通遭遇战已安装新 AI。

可复用无界面调用器：[run_python_probe.py](Development/run_python_probe.py)。它只等待并管理自己创建的进程，保存参数、超时、真实退出码及输出；最新版本还保存源码与 SHA256。绝不根据退出码 6 或出现生成文件自动判定功能通过。

## 原生 Python 绑定边界与桥接补充

- 嵌入解释器是 Python 2.5.1；原分配器使用 Python 3，现已生成并执行兼容版本，不能直接复制原文件后运行。
- `TGDVariableUnitGroup` 没有暴露公开枚举方法；`TGDVariableInteger` 只看到 `SetValue`；`TGDTagPosition` 提供 `GetPosition`、`GetRotation`，未找到坐标写入绑定。
- `sip.unwrapinstance` 加 `sip.voidptr(...).asstring(...)` 能读取本次 Python 自己创建的原生对象。旧版 `voidptr` 写入尝试失败；后续 DLL 对已核验类型的测试位置标签提供有限写入，对测试组提供单位坐标读取，不能因此省略正常玩家归属校验。
- 打包的旧 `leveldesign/launcher` 引用了 `TEffetMapLauncher.RunScript`，当前程序中未找到对应可调用绑定；不能把旧制作脚本当成当前 SDK。
- 测试框架暴露 `VirtualOnStart`、`VirtualDoTerminate`、用例创建等入口；尚未证明可作为不重置对局的周期调度器，不能直接用于正式 AI。
- 原生 `TLaunchGDScript` 调用链中，RVA `0x5dafe0` 构造句柄、`0x5db0d0` 启动运行对象、`0x5db010` 停止运行 owner。已通过研究 DLL 从自定义 Python 调用并完成正常清理；DLL 只进入受控子进程。

这些地址只对应当前 `WARNO.exe` SHA256 `70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8`，不可跨版本直接使用。

## 已排除的错误接法

- 在可修改的 `ClusterDepictionResources.ndf` 中提前加载 GDScript：文件可能已经写出，但随后在 GD 对象注册器尚未初始化时崩溃。异常地址为当前程序 RVA `0x5c7718`，对应读取空注册器指针。因此“出现了 ndfbin”不能判定编译成功。
- 未等待 Windows GUI 子进程退出的 PowerShell 结果，不能当成生成程序退出码。后续原生探针全部使用 `subprocess` 等待并记录真实退出码。
- 重复使用原生脚本的事务包名会受到生成事务的缓存/去重影响；一次实验明确报告找不到自定义测试对象。使用独立包名后通过。
- 直接重新初始化整套 IA 管理器会影响全局注册器、生命周期和其他系统，没有将其作为正式补丁安装。
- 只将编译结果改名放入本地 `Gen/NDF`，不提供正确来源及缓存关联，会被原生加载器判为不可用并回退原数据。后续确实提供原生源路径后，才得到自定义 Python 执行证据。
- 通过 `TClusterMountAdditionalDatapack` 再追加同名 `Glad` 根，未使独立覆盖目录中的见证文件可见；后来复制进 `RuntimeRoot/Gen` 才被找到，不能据此宣称追加挂载覆盖成功。

## 早期未闭合环节及其后续状态

以下清单记录研究入口阶段的缺口；普通自动加载、AI 身份、当前地图导航和临时仲裁已按本文顶部接通。连续换局、完整前线、全兵种战斗状态和完整对局效果依然待验证，不能把历史清单全部判定已解决。

1. **普通遭遇战与连续对局生命周期。** 受控测试的启动、更新与释放已通过；还需保留真实大厅的玩家、卡组、规则及部署状态，并验证不重置这些状态的自动接入和再次开局。
2. **完整空间数据。** 真实测试单位 ID、位置已传给求解器。仍需普通对局 AI/玩家身份、单位兵种和当前任务、地形可达性与前线提取；测试构造的阵位和路径边不能冒充这些数据。
3. **下令与原生 AI 的仲裁。** 必须避免自定义调度与原生 AI 连续抢写命令，保留战斗、恢复、补给和伤亡处理；不能通过把单位移出原生 AI 控制后永久留在原地来假装分散。
4. **通用性及实战验收。** 新包须在不同地图、人数和征服/歼灭规则下自动工作，切换对局时清理旧状态；黑森林 4v4 最高难度征服作为回归场景之一，实际改善分布并保持持续投入、激烈争夺和高代价。尚未达到这一阶段。

另已解析黑森林场景的 AI 区域、通道、路径成本及关卡对象格式，为地图空间数据接入提供基础。不能仅凭地图静态区域得出实时部队位置，也不能据此宣称已经执行了新调度算法。

不得把本探针、生成器、空测试 cluster 或离线分配结果发布为已解决扎堆的 test4。
