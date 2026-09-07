# AEA 实现核对稿 v2（合并 2026-09-09 评审）
变更相对 v1：估计批次 4→2、c=0.9；接受规则统一；旋钮由 few-shot proposer 产生（手工库降为范例）；三类预算分离且 K16 不改输出；Stage 认证编译后的 Setup；候选 ID 用前缀哈希；HorizonSqueeze 语义；FooterMask sha256 嵌套；移交与 4/4 Stage 移出主方法；每任务硬上限 30、无总量约束；B_T / B_L 显式。

---

## 0. 三类预算（各臂相同，PREREG 原文）
- **B_search = 30 策略 rollout / 任务 / 轮**：估计、杠杆、剂量、探针、R_hint。designer 调用、专家会话、逐字重放不计入但记录。
- **B_confirm = 16 / 被接受环境**：纯评测。**K16 confirmation never changes controller output**；只报告控制器精度（接受的环境中落在 B_L 的比例）与可学环境率。
- **B_train**：SL 的训练轨迹 = 搜索阶段在被接受环境上的轨迹（released 归纳器每环境只用最短成功），额外为 0，两臂按构造匹配；RL 由 trainer 批量固定。任何超出搜索轨迹的训练采样必须显式记为 B_train 并各臂相等。
- 每任务硬上限 30，所有臂遵守；不做总量约束、不做再分配；报告总量、均值/任务、每千 rollout 的下游增益；匹配总量曲线（固定随机任务序、预算截断）作为独立分析。

## 1. 两个带
- **B_T = [0.4, 0.6]**：控制器接受带，K=8 时 3–5/8。
- **B_L = [0.2, 0.8]**：下游"非退化学习信号"评测带，K=16 时 4–12/16。

## 2. `estimate.py`
- Beta(1+s,1+f)；第一批 4，之后每批 2；任一区间后验 ≥ 0.9 即停，K_max=16；极端任务 10 次停（0.8¹¹≈0.086）；regime = 后验质量最大区间；输出所有轨迹。
- 单元测试：p∈{0,.1,.5,.9,1} 各 200 次模拟，停止步数分布与误判率；band→saturated 误判 < 5%。

## 3. `knobs.py` — 剂量合同与 few-shot proposer
- **合同**：`make(d) → rules_code | in_env_actions`，d∈[0,1]，`axis`，`direction=harder_with_d`，推荐**嵌套性**：d₁<d₂ ⇒ 扰动集合 M(d₁)⊆M(d₂)。
- **范例（few-shot，也是可直接使用的旋钮）**：
  1. `FooterMask`：`bucket = int(sha256(f"{task_id}:{step}").hexdigest()[:8],16) % 10000`，`mask = bucket < int(d·10000)`；嵌套；确定性；O 轴，按构造有解。
  2. `HorizonSqueeze`：`m(d)` = 估计阶段成功轨迹长度的 (1−d) 分位数（d=0 最长、d=1 最短）；`modify_transition`：先检查 raw.success，成功则原样返回；否则 step_count ≥ m 时返回 `truncated=True`（不是 terminated）；按构造有解（m ≥ 最短成功）。Phase A 必测边界：第 m 步恰好完成的轨迹必须判成功。
  3. `Displacement`：d∈{1/3,2/3,1}→k；专家发现目标、动作列表验证；S0 轴，专家 ×3 证书。
- **proposer**：designer 收到任务描述、策略成功轨迹摘要、合同、三个范例；返回 ≤2 个带 `DOSE` 类属性的 Rules 子类（或 Setup 列表生成器）+ 方向声明 + 是否嵌套。校验：released `code_loader` 可加载；源码引用 `DOSE`；d=1 上 LLM-free smoke 不报错；O 轴按构造有解，其他轴 d=1 专家 ×3 证书，无证书丢弃。designer 可对族排序；控制器杠杆测试兜底。
- Chain / Link 不在合同内（v1）。
- 集成测试：FooterMask d=1 时快照**发给模型的最终 prompt**，断言无 "Admissible commands"（runner 可能从 `obs.data` 重拼）。

## 4. `dose.py` — 统一接受规则
- 任何剂量、任何来源：先 4 次；4/4 → NOEFFECT；0/4 → ZERO；1–3/4 → 补到 8；**接受 iff 3–5/8**；1–2/8 → 降剂量；6–7/8 → 升剂量。
- 杠杆测试 = d=1 上应用同一规则：4/4 换族；0/4 从 d=0.5 向下搜；1–3/4 补到 8，3–5/8 直接接受 d=1。
- 步长 0.25 后减半；≤4 个剂量评估或预算耗尽；非单调记录。
- 预算：估计 10 + 杠杆 4（+4 补齐）+ 剂量 8 (+8) = 26–30。
- 单元测试：悬崖 / 线性 / 非单调三种假曲线。

## 5. `stage.py` / `probe.py` — 零侧
- 候选：3 条失败轨迹（seeded）× t∈{T,3T/4,T/2,T/4}；**候选 ID = task_id + 编译前缀的 sha256**（若 proxy 能拿到 TextWorld facts，再加状态序列化）；≤6，从晚到早。
- **编译顺序**：取前缀 → 去无效动作（bridge `effective`）→ 加 `look` → 建 Setup（100 步配置）→ 实际重放 → **对重放后的环境**做专家 ×3 证书 → 通过才进探针。每任务一次保真检查（重放观察 == 存档观察）。
- 探针：每候选 4 次，从晚到早：1–3/4 → 接受该 Stage（最晚可学）并停；0/4 → 更早；4/4 → 记 `too_easy_stage`，继续更早。全部非可学 → **unresolved**（主 AEA 不产出；`too_easy_stage` 与移交只进消融/第二臂）。
- 预算：估计 10–16 + 探针 ≤5×4 = 20；≤30。

## 6. `certs.py`
- R_pol（最短策略成功逐字重放；O 轴与 m≥最短成功的 HorizonSqueeze 按构造）→ R_exp（专家 ×3，100 配置）→ R_hint（≤3 次策略 rollout，**计入 B_search**）；任一通过即 certified，否则 unresolved 跳过。
- 会话 done 读 stack 级 terminated/truncated。

## 7. `handoff.py`（不在主 AEA 内）
- 主 AEA：零任务无可学 Stage → unresolved，进 accounting。
- 第二臂 **AEA+Handoff**：unresolved 任务用专家最短成功轨迹作演示（released trace 格式），归纳为 single_succ item。主表两行分别报告。

## 8. `policy_skills.py`
- 第 r 轮策略 = backbone + bank_{r−1}，注入与评测同（查询嵌入 → mmr top-5 → skills 块）；各臂相同；Phase A 核实 released 钩子，无则包装器。

## 9. `controller.py`
```
regime ← estimate(π, E_t)                      # ≤16, 10 for extremes
band      → corpus: E_t unchanged
saturated → families ← designer.propose(≤2) ∪ exemplars, ordered by designer, exemplars first if designer silent
            for fam: leverage/accept rule at d=1; if leverage: dose_search; accept iff 3–5/8; break
            none → frozen_no_leverage | budget_exhausted
zero      → candidates ← compile+certify prefixes; probe latest-first; accept latest learnable; else unresolved
every rollout charged to B_search; hard cap 30 → stop task with status budget_cap_hit
```
- 输出 corpus 条目：band `{game_file, rules_code:"", in_env_actions:[], aea:{regime}}`；旋钮 `{rules_code(剂量烘入), aea:{family, source∈{exemplar,llm}, d, p8}}`；Stage `{in_env_actions, stage_budget:100, aea:{t, prefix_sha, profile}}`。
- 可恢复、任务级并发、任务内 4 或 2 一批。

## 10. `confirm.sh`（评测，各臂相同）
- 每个被接受环境与 band 任务 K=16 → p̂₁₆；可学 = B_L；次要 B_T；解锁 = p̂₀=0 的任务有可学环境；**结果不回写 corpus**。

## 11. 臂表（主表 + 最小消融）
| 臂 | 规则生成器 | 控制 | 备注 |
|---|---|---|---|
| R | released EnvRigger（fail-targeted prompt） | 文本 | 论文原配置 |
| G | EnvRigger App-G prompt + band | 文本 | 双侧基线 |
| G+ | G + 同样三个范例进 prompt | 文本 | 知识 vs 控制（round 1） |
| A | 同一 designer 在合同下 + 范例 | 测量 | **主方法** |
| A-ex | 只用范例旋钮 | 测量 | 控制器单独（round 1） |
| A+H | A + 移交 | 测量 | 第二臂 |
| O / N | 无自适应 / 无 bank | — | — |

## 12. LLM-free 正确性验证（付费前）
1. 单元测试：§2 §4 §5 假策略模拟；FooterMask 哈希嵌套性与跨进程一致性；HorizonSqueeze 第 m 步成功边界；计费恒等式。
2. 集成：专家当策略跑 saturated 全路径；"重放存档失败前缀后随机行动"假策略跑 zero 全路径；两者产出 released 归纳脚本可读的 corpus。
3. 保真：Stage 重放观察相等（3 任务）；100 配置 12 vs 62；FooterMask 最终 prompt 快照。
4. 付费 smoke：三个已知 regime 的任务各一。
