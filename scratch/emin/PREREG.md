# E-min — 预登记（PREREG）

**冻结日期：** 2026-09-05　**repo：** EnvJudge `scratch/emin/`（pre-M0，临时）　**预算上限：** USD 20（软闸 12）

本文件 = 设计文档 §1–§4，在任何 rollout 之前提交；提交后只能追加结果（见 `results/emin/`、`LOG.md`），不能改定义。

## 0. 冻结的外部输入（哈希）

| 输入 | 路径（切换到 switchHarness 仓库） | sha256 前 16 位 |
|---|---|---|
| pool 76 任务 id（split v2，split_seed 20260903） | `results/frozen/spreadsheetbench_ids_train_pool.txt` | `b8755fd1da11919c` |
| H_sub 答案条件缓存（accepted 37 / verifier_pass_any 44 / 76） | `rethinkskill/runs/pilot/nothink/spreadsheetbench/references/references.json` | `269009426ef422bc` |
| 完整 parent skill（冻结） | `results/frozen/spreadsheetbench_parent.md` | `227d788864a7d97b` |
| 数据 | `datasets/spreadsheetbench_assets`（verified_400 修正版，任务 42930 golden 文件名修复） | — |
| 官方评分器 vendored 源 | google-research/envharness @ `fab7d57441f06b75c73a900e04561d4d7600f361` `envharness/bridges/spreadsheetbench/online_judge_eval.py`（Apache-2.0） | — |
| 模型 | Pro = `deepseek-v4-pro`；Flash = `deepseek-v4-flash`；非思考模式（`thinking.type=disabled`），temperature 0.7 | — |

H_sub 标签由缓存推导：`accepted` → pass；`verifier_pass` 出现过但从未 accepted → restate；从未 verifier_pass → fail（预期 37 / 7 / 32）。

---

## 1. 假设与预登记预测

**单元：** 任务 t ∈ pool 76（冻结 split v2）。零成本 witness 探针另跑全部 verified_400（396 可评 + 4 不可解析）。

**探针（标签在看到干预结果之前计算）**
- W（witness，$0）：(a) 官方路径 golden-vs-golden：golden 复制一份经 LibreOffice 重算后用官方 `compare_workbooks` 比较——应通过；记重算失败/解析失败；(b) 隐藏 None 单元：golden 在 `data_only=True` 且**不重算**时，answer_position 内读为 None 的单元数 h(t)；(c) answer_position 可解析。**L0 := (a) 失败 ∨ (c) 失败**。h(t)>0 单独标记（substrate 路径的隐蔽黑洞候选）。
- H_sub（答案条件，已有缓存）：参考构造在 substrate 路径下的结果：pass 37 / fail 32 / restate 7。
- p̂₀（自身，本实验测）：parent⁻ 在 E_sub 下 K=8 的成功率。

**regime 标签（只在 p̂₀=0 的任务上）：** L0 缺陷；**L1** := W 通过 ∧ H_sub fail（预测为接口洞）；**L2** := W 通过 ∧ H_sub pass（预测为策略洞）；L? := restate 或无参考。

**干预（环境侧，验证器代码不动）：** Contract 栈 c1 围栏解包（取首个 ```python 块）；c2 异常也保存（程序抛异常时把命名空间里的 openpyxl Workbook 存到 output_path）；c3 官方重算路径（agent 输出与 golden 都经 LibreOffice 重算后再比较 = 官方协议）。环境：E_sub（原样，无 c）、E_c12（c1+c2）、E_off（c3）、E_all（c1+c2+c3）。

**预测（全部在 parent⁻ 上，Pro 为主，Flash 复核方向）**
- P1 混合物：p̂₀=0 的任务中，L1 与 L2 各占 ≥ 15%。
- P2 交互（核心）：E_all 下的解锁率（p̂₀=0 → p̂>0）满足 unlock(L1) − unlock(L2) ≥ 0.25，且 unlock(L1) ≥ 0.40。
- P3 剂量：unlock(L1) 在 E_off 与 E_c12 上都 > 0，E_all ≥ max(E_off, E_c12)；报告 c3 单独能收回的份额。
- P4 无害：E_sub 下 p̂₀ ≥ 0.875 的任务在 E_all 下 p̂ ≥ 0.75 的比例 ≥ 0.9。
- P5 consumer：Flash 上 P2 方向成立；Flash 的 unlock(L1) ≥ Pro 的 unlock(L1)（Contract 不需要 harness-benefit 能力）。
- P6 φ 微缩版：完整 parent 在 E_sub 下相对 parent⁻ 的增益 G；parent⁻ 在 E_all 下相对 E_sub 的增益 G′；报告 φ = G′/G（预测 φ ≥ 0.6）。
- P7 基线错路由（$0）：按 envharness `corpus.yaml` 的 designer 规则（sr==0 → SKIP），p̂₀=0 的任务全部被跳过；报告被跳过的 L1 份额 = |L1| / |p̂₀=0|。
- P8 witness 偏差（$0）：h(t)>0 的任务在 pool 76 中 ≥ 10%（substrate 验证器路径的偏差不是个例）。

**对照 A/A：** parent⁻ 在 E_sub 下用 seed 0–7 与 8–15 各跑一遍；报告每任务 |Δp̂| 分布与 regime 标签翻转率 f_AA。所有"解锁率"必须减去 f_AA 后仍满足阈值。

---

## 2. 臂表

| 臂 | agent | 环境 | consumer | rollouts | 用途 |
|---|---|---|---|---|---|
| A1 | parent⁻ | E_sub | Pro | 76×8 | p̂₀、regime 标签、P7 |
| A1′ | parent⁻ | E_sub | Pro（seed 8–15） | 76×8 | A/A |
| A2 | parent⁻ | E_c12 | Pro | 76×8 | P3 |
| A3 | parent⁻ | E_off | Pro | 76×8 | P3 |
| A4 | parent⁻ | E_all | Pro | 76×8 | P2、P4 |
| A5 | parent | E_sub | Pro | 76×8 | P6 的 G |
| A6 | parent | E_all | Pro | 76×8 | P6 补充（Contract 之上 skill 增量） |
| A7 | parent⁻ | E_sub | Flash | 76×8 | P5 |
| A8 | parent⁻ | E_all | Flash | 76×8 | P5 |
| R1 | 答案条件重生成 | E_all | Pro | L1 集 × ≤5 次 | H_off：接口修复后多少 L1 变为 hint 可解 |

parent⁻ = 冻结的 parent skill 去掉第 4 条（写纯值）与第 5 条（只返回一段围栏程序）——即去掉 agent 侧的接口补丁，让环境侧摩擦暴露。温度 0.7（与之前 temp 0 的协议不同，预登记为本实验的固定选择；seed = rollout 序号）。

**成本估计：** Pro 单 rollout ≈ $0.0024（来自 281 题 test ≈ $0.67），Flash ≈ $0.002；A1–A6 ≈ 3,650 rollouts ≈ $9；A7–A8 ≈ 1,216 ≈ $2.5；R1 ≈ $0.5；合计 ≈ $12–13。

---

## 3. 判决规则（冻结）

- **GO**：P1 ∧ P2（Pro）∧ P5 方向成立。
- **CONDITIONAL**：P1 成立但 P2 不成立（两种 regime 存在、但 Contract 对它们效果无差）→ Repair 段降级为 Study，Reshape 段照旧，先做 ALFWorld 可行性。
- **NO-GO**：P1 不成立（L1 或 L2 < 15%）且 P2 不成立 → 这个 substrate 上没有可分离的环境侧 regime；回到 v2 §7 的 ALFWorld-only 线重新评估。
- P4 失败（Contract 伤害已会任务）→ 无论 GO 与否，Contract 实现回炉，结果标 "implementation-suspect"。
- 任何"≥/≤"都以 10,000 次任务级 bootstrap 的 95% CI 报告；n 小的 cell 只报点估计与 CI，不加粗。

---

## 4. 预算闸门
- 硬上限 $20；累计 $12 时暂停、出中期报告、等 owner 批准再继续。
- 每臂跑前先用 3 个任务 × 2 rollouts 做 smoke（含 LibreOffice 重算），成本计入。
- rollouts 不开缓存（缓存 key 含 seed 也不开）；参考构造 R1 可开。
