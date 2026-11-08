# 直升机火箭尺寸调整 · smoke-preview.22

用户取消冰雹替换，保留 preview.21 的 L10D3 高爆视觉。仅直升机使用十个独立效果副本（九种地面变体和一种水面变体），尺寸与扩散/外扩初速/局部偏移均为原版 1.5 倍。弹药、音效、伤害与飞行不动。地面与固定翼以及所有既有爆炸继续沿用 3 倍尺寸、3.3 倍扩散。独立副本避免修改地面共用效果。

编译对象图已对照全部旧导出和十个新副本；官方构建、安装与原生加载通过。实际画面仍需对局确认。

# 弹头命中动画 · smoke-preview.21

## 本轮修正

用户实测指出直升机和 BMP 的机炮也变成了 122mm 命中特效。原因是 preview.20 只检查碎片烟尾，没有检查实际弹药口径。本轮要求：小于 80mm 不采用该 122mm 替换；直升机无制导火箭改用游戏内最大口径普通高爆火箭炮命中效果。

仅从命中注册名称过滤不可行：75/76mm 与 90mm、73mm 与 100mm 共用同一注册。恢复 28 个全为小口径的原生表；混合表则新增 12 个原生副本，68 个小口径弹药只改 ImpactHappening 引用。按源标识、明确数值 Caliber 和无歧义的口径 token 对照分类，不能把共用表名当口径。367 个小口径源条目逐项核验；原版 ZiS-3 76mm 榴弹自身就借用 122mm，因此另将它的 5 个相关表面换成原生 PT-76 76mm 视觉，保留原音效。以编译后的 DescriptorId 检查实际弹药，确保活动的小口径弹药没有 122mm 引用；不能仅检查公开导出，因为部分弹药以内嵌对象存在。

最大口径普通高爆 MLRS 为 `Ammo_RocketArt_D3_300mm_x10`，实际由 `WeaponDescriptor_L10D3_300mm_ESP` 使用，Traits 为 HE、伤害族为 howz。BM-30 的 300mm 为集束弹，未选用。L10D3 的原生视觉与 M270 共用 `FxImpactSolHEM270227Mm_`，资源名含 227mm 不代表选择了更小口径弹药。按各表面复用 L10D3 的原始视觉，保留当前全局 3 倍尺寸/3.3 倍扩散，不再套 122mm 代理。

沿单位 Helo 标签 → 武器组 → 弹药引用找到 19 种直升机火箭弹、88 个武器组。为每种火箭弹建立唯一 GUID 的视觉副本，只让这些直升机引用；7 个独立命中表覆盖 42 个视觉表面。共用 S-5、S-8、S-24、SNEB、Zuni 等的固定翼与地面武器引用不动。原弹药参数完整保留，唯有副本身份与 ImpactHappening 不同；火箭伤害、射速、弹道、补给消耗、点火概率和音效不变。反坦克导弹没有进入该分支。

## 本轮验证

- 官方生成与打包、39 个安装文件哈希通过；实际启用模组的原生无界面启动/地图加载/退出通过（兼容状态 0，正常退出，无脚本错误）。该检查不使用 -noMod，不作渲染验收；未重跑完整 AI 回归。
- 2741 个原武器导出的完整对象图逐项对照；新增火箭弹仅允许身份/视觉引用变化。
- 367 个小口径源条目、全部命中表面和 80 条单位毁伤分支核验通过。
- GameFx、VFX_Bank、Unit、Skirmish 字节不变；运行 DLL/资金/AI 不变。
- 实际渲染大小、密度与帧率仍待新对局验证。

证据：`Development/impact-visual-source.json`、`impact-visual-verification.json`、`smoke-release.json`。恢复点：`Development/archive/smoke-preview21-before.zip`。新增实现/核验：`impact_caliber.py`、`verify_impact_caliber.py`。

## 历史 preview.20（小口径覆盖过宽，已修正）

用户要求：坦克炮命中步兵时，四散粒子拖烟尾的爆炸动画改为 122mm 榴弹炮动画；其他使用同类弹头爆炸的武器一并替换。坦克被击毁时的碎片烟尾保留。

## 证据与边界

调用链为弹药 `ImpactHappening` → `MimeticImpactMapping.ndf` 的弹药/命中表面注册 → GameFx → Rubble 粒子 bank。例如坦克榴弹 `CanonGrosHEM1Abrams`、`CanonGrosHET80` 的 Ground/Air 命中调用 HEGros/HETresGros。`BANK_Rubble2` 的烟碎片与燃烧碎片均具有 `trailEvolverSmoke`，由两类非零数量参数启用。这不是炮弹飞行尾迹，也不是烟团自身运动。

122mm 基准为 `Artillerie2A18122Mm` 使用的 `FxImpactSolHE122Mm_`，包含 `fx_impact_sol_HE_122mm_1` 至 `_5` 五种原生随机变体；三类 Rubble 调用的带烟/带火碎片数量均为 0。保留当前已安装的尺寸 3 倍、散布 3.3 倍，直接复用现有随机动画组，不再额外放大。

筛选依据为实际命中动画中启用的烟尾发射器：Rubble 烟/火碎片数量大于 0 且可见，或显式烟尾发射器。扫描五种 122mm 基准确认没有这些烟尾；另检查 ClusterFragment 的 trail_flare 属光迹，地面扬尘贴片不当作碎片尾烟。只改有弹药描述引用的弹头命中注册；未引用旧注册保留并记录。步枪/机枪子弹、跳弹、拦截纯音效表面和战术烟幕不扩大为榴弹爆炸。单位毁伤注册以 `DestructionUnite` 前缀明确保护。

## 实施

只修改一个 NDF：`GameData/Generated/Gameplay/Gfx/MimeticImpactMapping.ndf`，只替换注册表内的视觉引用，保留命中挂点、原音效和所有弹药数据。发现 62 个含烟尾的动画别名、223 个有关 FX，涉及 109 组命中注册、869 个弹药描述；重定向 447 条有该视觉的命中表面分支。并非每种武器的所有表面都替换，也不将本来没有烟尾的动画统一覆盖。

不修改共享 Rubble bank，避免同时删除坦克毁伤尾烟。所有 GameFx 和 VFX_Bank 编译包与 preview.19 字节相同，含坦克毁伤爆炸、持续燃烧和水平顺风烟；AI、Unit 与预算 DLL 不变。命中动画现统一采用 122mm 视觉强度，不表示武器伤害或口径改为 122mm。

## 验证

官方构建与打包通过；独立核对编译后的三份 Mimetic 注册：447 个目标分支等于 122mm 五变体，其他 801 个分支保持，其中 80 个单位毁伤分支逐项保持。命中音效未变；GameFx/VFX_Bank/Unit/Skirmish 哈希保持。完整历史火烟与爆炸倍率检查、安装哈希核验均已通过，release 记录已安装；预算 DLL 与 vfx-budget.3 哈希相同，未重跑 AI/原生预算探针。无 GUI/渲染验证，实际视觉仍待新对局。

脚本：`Development/impact_visuals.py`、`verify_impact_visuals.py`。
证据：`impact-visual-source.json`、`impact-visual-verification.json`、`smoke-release.json`。
备份：`Development/archive/smoke-preview20-before.zip`。
