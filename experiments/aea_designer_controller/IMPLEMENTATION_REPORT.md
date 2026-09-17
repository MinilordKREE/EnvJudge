# AEA Designer–Controller：实现与离线验收报告

本报告对应新 selector `llm_v3_designer_controller`。本次只进行实现、合成回归和本地
ALFWorld 离线验证；新增付费 API 调用为 **0**，新增付费 policy episode 为 **0**。

完整方法定义见 [AEA_DESIGNER_CONTROLLER.md](../../docs/design/AEA_DESIGNER_CONTROLLER.md)。
历史回放的机器可读元数据见 [historical_replay_metadata.json](historical_replay_metadata.json)。

## 1. 起始 HEAD 与工作树安全

| 项目 | 起始记录 |
|---|---|
| 研究工作树 | `/home/kree/work/EnvJudge-aea-llm` |
| 分支 | `aea-llm-vnext` |
| HEAD | `247ab479ff9f703db0acbb7beff11b8d73893798` |
| main 工作树 | `/home/kree/work/EnvJudge`，`f972605` |
| 研究树原有未跟踪文件 | `experiments/alfworld_e3/NEW_AEA_IMPLEMENTATION_REPORT.md` |
| main 原有状态 | ` ? third_party/envharness` |

原有未跟踪报告不混入本次实现提交。历史实现 `969e339`、结果提交 `247ab479`、冻结
清单和正式 E3 结果未被重写。起始命令输出的结构化副本保存在本地 ignored 验收目录。

## 2. 新方法版本

新增 `AEAConfig(method_version="llm_v3_designer_controller")`。旧 selector 继续走原路径，
没有把新算法隐藏在 `llm_v2_integrated` 名字下面。新参数独立为 `V3Config`，避免改变旧
配置的默认序列化内容。

## 3. 架构摘要

```text
MEASURE -> MID -> original
        -> LOW/HIGH -> DESIGN -> gates -> effective-level CONTROL
                              ^                    |
                              |--- typed feedback --|
                                    bounded

accepted level -> exact final solvability -> FINAL FREEZE -> fresh K16
```

Designer 是唯一负责开放机制搜索的 LLM 组件；Controller 是确定性算法。judge、validator、
identity 和 solvability 是准入检查。LOW/HIGH 共享 `DesignSession` 和 `EnvironmentController`。

## 4. Designer 精确接口

`build_design_context(...) -> DesignContext` 构造任务、regime、测量和有界历史证据。
`InterventionDesigner(...).propose(DesignRequest) -> DesignProposal` 每轮只调用一次、只返回一个 family。

请求字段：`context`、`design_round`、`operation`、`remaining_design_rounds`、
`remaining_policy_rollouts`、`parent_family`、`feedback`。剩余设计轮数包含当前调用。
每轮携带原始证据和最新反馈，不累积无界聊天历史。模型不能自行指定可信 lineage。
Prompt 保持共同合同、方向合同与必要 API 说明的结构，没有加入全部历史案例或固定机制库。

## 5. InterventionFamily schema

```text
family_id, direction(easier|harder), mechanism_summary, source,
axis(O|T|A), hooks, control, expected_effect,
parent_family_id, design_round, operation, semantic_mechanism_id
```

`control.kind` 支持 `BINARY / SCALAR / DISCRETE`；settings 是带可选私有名称的 numeric
operating points。当前 Rules adapter 用 `[0,1]` 与 `__DOSE__` 表示它们，不要求连续性。
身份、轮次、父关系和 operation 由宿主绑定。

## 6. Controller 精确接口

`EnvironmentController(AEAConfig, V3Config).calibrate(family, characterization,
run=policy_batch_callback, remaining=budget_reader) -> ControllerDecision`。

`ControllerDecision` 包含 typed feedback、可选 accepted effective level 和实际 `Eval`。
Controller 不调用 LLM。搜索顺序为建议最强、建议最弱，再选择最大未测 ordinal gap
的中点；不沿浮点 dose 做旧 bracket，也不假定成功率数学单调。

## 7. Effective level 表示

每级记录 `level_id`、`surface_signature`、等价 settings、代表 setting、建议顺序、
`is_off`、实际渲染源码 hash、coverage。代表取该类最后一个名义设置，排序取最后出现位置。
包括正 dose 在内、与 OFF 等价的设置均属于 OFF 类。

## 8. Characterization 算法

在冻结的 original episode/step 前缀上运行全部声明设置的 hooks，对 learner-facing
delta 做保留 JSON 类型与动作顺序的 canonical hash。相同 delta signature 合并为一类。
签名不使用名义 dose、源码 hash 或隐藏 simulator state 定义强度。

覆盖观察、格式化观察、可见 history、admissible 内容/顺序、动作/阻断反馈及可见停止标志。
审计用 reward/info 另供 preservation 检查。缺失、重复、冲突、错误 capture 不会默认通过。
`A -> B -> A` 记录结构复现诊断，不把随机 policy 成绩当作环境强度变化。

这是**捕获集合上的等价**，不是全局行为等价。`.as_record()` 仍是审计对象；公开必须经过
`public_task_metadata()` 白名单投影。

## 9. LOW 流程

保持 Beta measurement；LOW 取最多三条失败轨迹和 verified rich reference，逐轮 DESIGN。
通过 schema/API/OFF、lexical、characterization、R5 privilege PASS、strongest solvability
后才能进行 policy probe。没有独立 privilege PASS 的新控制行为不能接触 learner API。

## 10. HIGH 流程

使用基线成功/失败证据，不获取 reference，不调用 LOW judge。通过共享 identity/task
preservation、characterization 和 solvability 后进入同一个 Controller，也允许有界 redesign。
HIGH 保留合法的 truncation 型挑战，但不能伪造 reward、success 或任务语义。

## 11. MID 流程

返回原始环境。无 Designer、无 ControlSession、无 reference、无 judge。新的 K16 仍独立执行，
不会根据结果重新路由到 LOW/HIGH。

## 12. Feedback 状态机

| 原因 | 下一轮操作 |
|---|---|
| `MECHANICAL_FAILURE` | `REPAIR_CODE` |
| `PRIVILEGE_REJECTION` | `REPLACE_MECHANISM`，仅 LOW |
| `SOLVABILITY_FAILURE`、`NO_LEVERAGE` | `REPLACE_MECHANISM` |
| `OVERPOWERED_BINARY` | `REFINE_CONTROL` |
| `INSUFFICIENT_ATTENUATION`、`INSUFFICIENT_RESOLUTION` | `REFINE_CONTROL` |
| `CONTROL_EXHAUSTED` | 有轮数和预算则 `REFINE_CONTROL`，否则结束 |
| `NON_MONOTONE_CONTROL_SURFACE` | 保留结构诊断；作为反馈时对应 refinement |
| `ACCEPTED` | 最终认证通过后 freeze，不再 DESIGN |

二元 ON 直接 in-band 就接受。二元 overshoot 才请求 refinement；标量/离散设置坍缩后
只剩一个过强正级别，对应 attenuation feedback。全部不同级别测完、跨过目标却没有命中，
对应 resolution feedback。自然语言只解释这些类型，不替代枚举。

## 13. REFINE_CONTROL 语义

保留 `semantic_mechanism_id` 和父机制声明，改变源码中控制的 scope/frequency/coverage/
delay/strength/levels。`REPLACE_MECHANISM` 创建新机制 ID，并保留父 family 关系。
Refinement/repair 必须保留声明的 mechanism summary；被拒绝的新声明不会覆盖原语义锚点。
这是可审计的声明 lineage，不是任意程序语义等价证明。

## 14. Freeze 边界变更

通过端点检查的 family 只是 **PROVISIONAL**。Controller 找到 in-band level 后，还需最终
exact-environment solvability；随后才冻结 family、control、characterization、chosen level、
最终源码、准入和证据。此前 CONTROL 失败可返回下一轮 DESIGN。

## 15. Privilege 集成

R5 主 judge、witness、模型/标签/schema/prompt 未调整。FAIL/UNCERTAIN 都拒绝候选并给 typed
feedback。准入绑定 task/family/source/control/config/characterization 与每个实际渲染代表。
新 child、改过的 control、未审查设置和额外注入动作不能复用旧 PASS。保存的 judge witness
在 K16 前离线重验。历史 Phase A 继续为 `NOT_READY`，不宣称本次改善 judge accuracy。

## 16. Solvability 集成

LOW 用既有 oracle-only guard；HIGH 优先 policy-success replay，再 oracle。最多三次
expert attempts、每次五十步。先认证 strongest representative；最终选中不同渲染环境时
重新认证。只有精确相同 source/actions 才复用成功证书，不以 surface equivalence 代替认证。

## 17. Target 配置

搜索仍是 `4→8`，`3–5/8` 接受。`AEAConfig.probe/accept` 显式配置 Controller 目标；
K16 保留 `B_L=4–12/16`、`B_T=7–9/16`。没有在实现中改变科学目标带。

## 18. Budget、K16 和记账

默认 baseline≤16、adaptation≤30；每轮最多五个不同 positive effective levels，最多三轮
DESIGN。新一轮前至少留八个 adaptation episodes。每批先扣预算；不够四次补测就记录
incomplete probe，不能接受 `2/4`。离线 characterization 和专家 replay 不计 learner episodes。

新增 audited substrate 复用已有 logical ledger、AuditedPolicyClient 和 AuditedTransport，
分别记录测量、DESIGN/judge、adaptation、K16 和物理尝试。无收费记录时 artifact 明确标记
unavailable，不把缺失费用当成零。

执行完整性回归补充了三条约束：部分 task 在再次测量前拒绝重启；派发 candidate 按调用前
深拷贝核验；final freeze 绑定实际搜索文件和每次 probe 的 episode IDs、源码、计数。
K16 严格使用 fresh IDs，核验搜索证据和最终环境，禁止重复尝试、修改历史或回流。

## 19. 完整测试结果

| 检查 | 最终结果 |
|---|---|
| 全量 unit suite | **1,278 passed**，131.74 秒 |
| 完整 integration suite | **12 passed, 1 skipped**，1,372.63 秒 |
| Real ALFWorld 新方法 smoke | **2 passed**，包含在 integration 中；两个方向均通过 |
| strict mypy | **PASS**，138 个 source/test 文件 |
| Ruff | **PASS** |
| format check | **PASS**，138 个文件已符合格式 |
| pre-commit | **PASS**，适用 hooks 全通过 |
| git diff / staged diff whitespace | **PASS** |

唯一 integration skip 是旧 `test_rl_corpus_loader_roundtrip` 缺少可选 `ray`，不是新方法
失败。YAML 和 `.env` pre-commit hooks 因没有适用文件跳过。新测试覆盖 LOW/HIGH 共享
协议、MID no-op 与非默认配置、去重与 binary、typed feedback/lineage、privilege binding、
最终证书/freeze、搜索记录完整性、fresh K16 和 accounting。旧 task110 实机回归也通过。
所有调用均为本地 replay、synthetic/mock 或 scripted policy；没有外部模型请求。

这些测试验证实现合同和记录一致性，不代表已完成新方法的付费 efficacy evaluation。

## 20. Real ALFWorld offline smoke

两方向的真实 ALFWorld original-prefix capture 通过：每方向三个 prefix states、十七个
名义设置、五十一个 capture。合成通用 observation hook 得到两个有效类，十六个正 dose
合并为一个正级别。无模型调用、无 privileged reference fixture、无 efficacy 声称。

## 21. 历史 E3 离线回放：8/9/10/17/23

| Task | 名义设置数 | 有效类含 OFF | 旧重复 probe 数 | 原始 prefix states |
|---|---:|---:|---:|---:|
| LOW 8 | 17 | 4 | 2/5 | 153 |
| LOW 9 | 17 | 4 | 1/5 | 153 |
| LOW 10 | 17 | 3 | 3/5 | 153 |
| LOW 17 | 17 | 3 | 3/5 | 153 |
| HIGH 23 | 17 | 11 | 1/5 | 41 |

总计 25 次旧 probe 中 10 次是已出现表面类的其他名义设置。LOW 使用已有完整 capture；
HIGH 23 在 runtime fingerprint 匹配后，以已保存基线动作本地重放。

以网格索引 `i` 表示 `d=i/16`，分组为：

```text
8:  OFF{0}; {1..5}; {6..10}; {11..16}
9:  OFF{0..4}; {5..7}; {8..11}; {12..16}
10: OFF{0}; {1..7}; {8..16}
17: OFF{0}; {1..7}; {8..16}
23: OFF{0..1}; {2..3}; {4}; {5..6}; {7}; {8..9};
    {10..11}; {12}; {13..14}; {15}; {16}
```

新的 representative 未必是旧实际采样设置，因此**精确的新 Controller 终态无法由旧数据
识别**，不继承旧成功率、不虚构新接受结果。可报告的条件性诊断是：如果四个 LOW 任务的
新代表测量仍保持其类中已记录的 too_easy verdict，则在测完 3/3/2/2 个正级别后得到
`INSUFFICIENT_ATTENUATION → REFINE_CONTROL`。HIGH 23 有十个正级别，默认最多测五个；
若没有提前接受或 no-leverage，则到达 `CONTROL_EXHAUSTED`。

HIGH 23 的 `.5` 和 `.5625` 同类，却记录 `4/4` 与 `0/4`；这不能当作 actuator 方向证据。
LOW 9 的 `.25` 属于 OFF，不能算作正级别的有效缓和。旧 scores 全部保留。

私有 replay summary SHA256：
`f7c1adc11e17522157f7c1e4ec4eedb0b2795e835c63382f82fd4aa00f1a200f`。

## 22. Legacy preservation audit

新模块与新 selector 分开。未修改旧 bracket、LOW optimizer、semantic/LLM judge/witness、
measurement 或历史实验 runner。共享 Controller 的新增行为只在新 selector 条件成立时启用；
原 integrated 的独立 baseline 语义继续保持。完整 unit suite 包含旧方法回归。

已核验九个旧 selector 的默认序列化配置及 hash 完全一致；八个核心旧模块与起始提交
逐字节一致，旧 scripts 和已跟踪 E3 目录的 diff 为空。四份历史结果和两份冻结清单
保持原字节；main HEAD/status、原有未跟踪报告也保持不变。新 checkout 的共享入口
有显式版本分流，因此不声称全部当前源码仍匹配旧 source-freeze；复现旧源码可 checkout
历史 commit。私有 legacy audit SHA256：
`1c339876f17492eba4007d3f735b85c1d6512006a201dca6ea5f731cbb715de0`。

## 23. Privacy / publication audit

提交内容限于实现、合成测试、设计/验收文档和 hash/count/enum 元数据。原始 reference、
GT 观察/动作、生成候选源码、运行表面、raw prompts 和 judge prose 保留本地 ignored。
公开 task artifact 使用字段重建，任意模型字符串不直接透传。

待提交的 25 个文件、diff 和新增行已接受完整内容 fingerprint 检查：42,960 个受保护
文本模式，来自 60,109 个本地 E3 私有文件及 20 份旧受保护输入；发现数为零。检查
包含既有泄漏扫描器自测，私有输入的 hash 未变且保持 gitignored。最后四个改动文件另做受保护锚点补扫，最终 25 个暂存文件与审查版本逐字节绑定。
完整扫描和刷新记录保留在本地 ignored `publication_audit.json`。

该检查针对本次新增提交内容，不扩张为对全部继承历史的清洁证明。本次不 push。

## 24. 实现提交

本报告随新实现提交保存；交付回复给出完整实现 commit SHA。起点是 `247ab479`，不会 amend
或重写它和 `969e339`。本次未跟踪的旧实现说明文件不混入提交。

## 25. 未决事项

没有留待运行时临场选择的设计策略：三轮、五级上限、有限网格、代表选择、搜索顺序、
feedback 映射、预算门槛和最终 freeze 均已明确。

保留的研究/覆盖限制包括：捕获等价不保证未见状态等价；R5 仍有已知误判；有限网格可能
漏过有用设置；reference 获取依赖现有 provider 的可用性和范围；改变路径、重映射或阻断
动作的 hook 可能超出当前 replay adapter。Reference prefixes 不进入 characterization。
新方法是否提升 efficacy 需以后做匹配实验。宽 learnable 带与约 50% 搜索目标的比较没有在这里决定。

本次到实现和离线验收为止，不自动启动 E3、E3-SL、筛选新任务或付费 smoke。
