# GateANN 双模式混合 Graph Tunneling

仓库地址：<https://github.com/qingyueyouyun/HUST_CSD_Experiment>

本仓库是计算机系统设计课程实验“优化方向”的配套代码。它在
[GateANN](https://github.com/GateANN/GateANN)（commit
`71e87cbf0e25c0400c0109dd25a64a7c4dccc9dd`）的查询阶段增加了一种
**双模式混合 Graph Tunneling**：当查询标签集的选择率低于阈值时，允许不满足
过滤条件的顶点只作为多跳中继，只有满足条件的顶点才进入候选集；同时用精确的
有效节点（valid-node）位图把中继遍历中的标签判断降为一次位测试。该优化不修改
索引格式，也不需要重建索引。

> 本仓库提供的是**补丁 + 复现脚本 + 测量数据**，不是 GateANN 的全量源码。
> 使用时先克隆 GateANN 固定 commit，再应用本仓库的补丁。

## 1. 背景

原版 GateANN 的过滤查询使用一跳 FullAdj 隧道：候选如果不满足过滤条件，就不读
SSD，而是把它的 FullAdj 邻居全部插入候选池。强过滤（例如 YFCC Low 桶，
selectivity 约 0.545%）下，一个顶点平均只有约 0.17 个邻居满足条件，于是每个被
跳过的顶点又会带入约 32 个不匹配候选。`L` 个候选位置被不匹配顶点占满，按 PQ
距离排序的搜索始终在“不匹配的海洋”里做局部扩展，难以到达匹配顶点密集的区域。
结果是：逻辑 I/O 很少（4.38 次/查询），但 Recall@10 只有 34.3%。

本补丁在 Medium/High 等弱过滤场景保持原版行为；只在选择率低于 1% 时切换到
有界多跳中继。中继顶点**只作为图上的跳板**，不会被读取，也不会出现在结果中。

## 2. 仓库结构

```text
patch/0001-hybrid-tunneling.patch   基于 GateANN 71e87cb 的补丁
scripts/apply_patch.sh              应用课程 AIO 兼容补丁 + 本优化补丁
scripts/build.sh                    编译 build_disk_index / search_disk_index_yfcc
scripts/run_validation.sh           原版与混合，Low/Medium/High，3 轮
scripts/measure_cache_and_load.py   缓存 / 后台负载测量脚本
scripts/measure_cache_and_load.sh   上面的 Shell 包装
scripts/summarize_results.py        把日志汇总为 CSV
docs/                               设计与实现说明
measurements/                       冷/热缓存原始测量数据
results/                            验证日志与 summary.csv
```

相关文档：

- [设计与实测细节](docs/DESIGN.md)
- [测量数据说明](measurements/README.md)
- [验证结果说明](results/README.md)

## 3. 快速开始

```bash
git clone https://github.com/qingyueyouyun/HUST_CSD_Experiment.git
cd HUST_CSD_Experiment

git clone https://github.com/GateANN/GateANN.git /path/to/GateANN-public
git -C /path/to/GateANN-public checkout 71e87cbf0e25c0400c0109dd25a64a7c4dccc9dd

# 可选：课程 AIO 兼容补丁（使用 -DUSE_AIO=ON 时需要）
AIO_PATCH=/path/to/gateann_aio_compat.patch \
  bash scripts/apply_patch.sh /path/to/GateANN-public

bash scripts/build.sh /path/to/GateANN-public
```

如果 GateANN 工作区已经应用过课程 AIO 补丁，`apply_patch.sh` 会自动识别，
只应用本仓库的混合隧道补丁。

运行验证套件（路径通过环境变量传入；默认值与课程实验目录一致）：

```bash
REPO=/path/to/GateANN-public \
ROOT=/path/to/fvs-course-lab \
OUT=/tmp/hybrid-results \
bash scripts/run_validation.sh
```

汇总日志：

```bash
python3 scripts/summarize_results.py /tmp/hybrid-results \
  --out /tmp/hybrid-results/summary.csv
```

## 4. 预期行为

| 档位 | 估计选择率 | 模式 | 预期 |
|---|---:|---|---|
| Low | 约 0.5% | 混合中继 | Recall 明显上升，I/O 与延迟也上升 |
| Medium | 约 3% | 原版路径 | 基本不变 |
| High | 约 12% | 原版路径 | 基本不变 |

## 5. 课程 1M YFCC 索引上的实测结果

Low 桶，L=320，200 条查询，3 次独立重复取中位数，同一时段测量：

| 配置 | Recall@10 | 延迟（μs） | 平均 I/O（次/查询） |
|---|---:|---:|---:|
| 原版 GateANN | 34.30% | 771 | 4.38 |
| 混合 3-hop，budget=128 | 69.50% | 2387 | 26.43 |
| 混合 3-hop，budget=256 | 80.15% | 3745 | 39.33 |
| 混合 2-hop，budget=128 | 79.25% | 2770 | 46.51 |

固定 L 下的提升是真实的，但**直接增大 L 也是一个很强的对照**：原版
L=1280 达到 70.05%，延迟 2320 μs、I/O 13.95；L=2560 达到 83.75%，延迟
4505 μs、I/O 25.06。因此本优化**不是 Pareto 改进**：只有在“固定 L、且以
延迟为目标”的场景下（约 80% Recall 附近）才比较有吸引力，代价是约 1.6 倍
逻辑 I/O。完整讨论（包括这个负结果）见 [docs/DESIGN.md](docs/DESIGN.md)。

Medium（约 3.1%）和 High（约 12.0%）保持在原版路径，`relay_nodes=0`，
没有回归。
