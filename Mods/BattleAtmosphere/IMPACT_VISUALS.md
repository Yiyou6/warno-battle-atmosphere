# 弹头命中动画 · smoke-preview.20

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
