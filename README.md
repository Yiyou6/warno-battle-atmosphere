# WARNO BattleAtmosphere

面向最高难度遭遇战的战场氛围与作战 AI 模组源码。目标是有氛围、有章法、双方付出巨大代价才决出胜者的战斗：大多数可用部队持续向前，在推进中展开宽战线，允许有用途的局部主攻集中，不允许大批部队长期闲置后方。

当前快照：**combined-arms-preview.6 + smoke-preview.6**。根据用户反馈，将烟粒发射率翻倍、加大初始尺寸，保持慢膨胀；采用连续平方淡出，在寿命 97% 时变为透明。官方构建、五层编译曲线和安装核验通过；本轮未重复原生遭遇战回归，突然消失是否还受引擎裁剪影响仍待实测。详见 [烟雾设计](Mods/BattleAtmosphere/SMOKE_ATMOSPHERE.md) 和 [安装验证摘要](docs/validation-smoke-preview6.json)。

支持范围是征服与歼灭遭遇战，算法从当前场景提取部署区和导航，不依赖黑森林专用坐标。运行组件目前严格绑定 WARNO **revision 201602**；其他游戏版本需要重新核验原生接口。

## 当前实现

- 按实际出生位置校准阵营方向，避免地图侧编号与运行阵营不同导致后退。
- 同阵营前线区段分配、阵位预约、据点核心限额和两翼连续推进。
- 载员车辆运输、分散卸载位置、绕路进度识别及接敌/停滞应急处理。
- 原生坦克采购机会与混合兵种任务调整，保留炮兵、防空、航空、侦察及补给需求；不增加收入。
- 原生 AI 短租约与自动归还；玩家单位不接受脚本下令。

用户常用最高难度、双倍资金（其提供的基准为 AI 每分钟 1000+）。这不是源码额外发放资金的设置。

## 代码结构

| 目录 | 内容 |
|---|---|
| `Mods/BattleAtmosphere/Runtime/Python/` | 实际嵌入游戏的调度、战线、运输及战术代码，兼容游戏内 Python 2.5 |
| `Mods/BattleAtmosphere/Development/native_bridge/` | C 原生桥接、自动加载器、构建与核验工具 |
| `Mods/BattleAtmosphere/Development/dispersion/` | Python 3 离线模型与 57 项回归测试 |
| `Mods/BattleAtmosphere/GameData/` | 8 个 AI 配置、25 个燃烧特效源文件、残骸燃烧时长配置及模组资源/本地化描述 |
| `Mods/BAScriptProbe/.../ba_fixture.py` | 显式启用的受控测试夹具，普通对局不启用 |
| `Mods/BattleAtmosphere/*.md` | 设计取舍、耦合分析和历次验收记录 |
| `docs/validation-preview6.json` | 本次源码导出前的原生回归摘要，非下载后重新执行的结果 |

仓库是源码快照，不包含游戏 EXE/DLL、原版资源包、官方完整 NDF 基线、编译器、生成产物、个人存档或原始对局日志。保留原目录结构是为了让现有相对路径能够工作。历史设计文档指向的本地日志、旧版归档和安装回执没有随源码发布。

## 离线测试

无需安装 WARNO，使用 Python 3.10+ 在仓库根目录运行：

```powershell
python -m unittest discover -s Mods/BattleAtmosphere/Development/dispersion -p 'test_*.py'
```

测试通过只证明离线行为约束，不等于完整对局验收。

## 构建与游戏接入

1. 准备自己的合法 WARNO 安装及相同 revision。保留官方模组工具生成的 `BattleAtmosphere` 完整基础目录，再将本仓库的 `Mods/` 叠加到游戏根目录；仓库内 8 个配置不能单独替代官方基础目录。
2. 开发脚本使用 Python 3。原生构建使用 Windows x64 Tiny C Compiler，现有脚本约定其位于 `%TEMP%\codex-warno-compiler\tcc\tcc.exe`。这项本地工具路径尚未改为通用安装器。
3. 在游戏根目录运行 `python Mods/BattleAtmosphere/Development/native_bridge/build_runtime.py`。它嵌入运行模块及测试夹具，输出候选 `version.dll` 和源码哈希清单；不会安装或启动游戏。单独复制 `.py` 不会改变游戏执行版本。
4. NDF 使用游戏自带模组生成工具编译。`Development` 中的 profile 重建、原生回归和安装工具保留开发时逻辑，部分依赖未发布的 `base.zip`、历史源码归档、测试环境和核验回执；不能把它们当成从空目录一键安装的发布器。完整原生回归入口为 `run_combined_validation.py`，运行前必须准备隔离的 `BAScriptProbe/AutoloadBoot`（自己的游戏副本和资源路径）并正常退出游戏。
5. 通过本机构建与原生验证后再安装候选。不要用别人的旧验证回执绕过检查；不要覆盖来源不明的 `version.dll`。启用模组 `BattleAtmosphere` 与 `Runtime/runtime.ini` 后，运行组件随新的遭遇战自动进入，无需启用研究用 BAScriptProbe。

当前原生目标 EXE SHA-256：`70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8`。

燃烧特效的复现入口为 `Development/apply_smoke_profile.py`、`build_smoke_profile.py`、`verify_smoke_profile.py` 和 `install_smoke_profile.py`。在完整的同版本游戏模组工作目录中依次执行；它们依赖官方生成的 `base.zip` 、开发环境中的 `zstandard`，以及 `archive/smoke-preview2-before.zip`、`smoke-preview4-before.zip` 中真实的 preview.1/preview.3 安装包与回执（用于逐表达式核验倍率，未随仓库分发）。安装前核验 AI、玩法描述和 DLL 哈希未变，保留当前模组选中状态。单独克隆源码仓库只能运行上面的离线算法测试，不能替代游戏资源及原生验证环境。

## 验证状态与边界

- preview.4 普通对局中，用户已确认较宽战线、两翼前推，以及据点短暂聚集后自行散开。
- preview.5 出现真实阵营方向错误，preview.6 已修复，并通过 57 项离线测试、换边推进、运输、冷启动和持续增援/交战的原生回归。
- preview.6 的普通新对局仍待用户确认；不宣称所有地图、卡组和完整战术体系已经验收。
- 实时资金/库存驱动的完整采购器、直接炮兵烟幕控制、基于已见敌军的真正合围尚未接入。历史 1000 单位瞬时密集纵队仍有解堵边界。

配置与原生接口源于针对 WARNO 的模组开发。游戏名称、官方资源和原有配置内容的权利属于相应权利人；此仓库未另行授予开源许可，也不分发游戏本体。
