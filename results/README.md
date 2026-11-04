# 验证结果

本目录由 `scripts/run_validation.sh` 在课程 1M YFCC 索引上生成。每个配置独立
运行 3 次，`summary.csv` 给出中位数与范围。

- `baseline-low-rN.log`：原版 GateANN，Low，一个进程依次跑 L=320/640/1280/2560；
- `baseline-medium|high-rN.log`：原版，L=320；
- `hybrid-low-h3b128-rN.log`：3-hop，relay-budget=128，每查询总预算 2048；
- `hybrid-low-h3b256-rN.log`：3-hop，relay-budget=256，每查询总预算 4096；
- `hybrid-low-h2b128-rN.log`：2-hop，relay-budget=128，每查询总预算 2048；
- `hybrid-medium|high-rN.log`：开启混合模式，但选择率 >1%，策略仍在原版路径
  （`relay_nodes=0`）。

延迟由系统 Query Phase 的 QPS 换算：`1e6 / QPS`；平均 I/O 是系统内部逻辑
I/O，不是块设备物理 I/O。

这些运行在同一 WSL2 环境完成。受宿主电源/负载状态影响，绝对延迟约为
9 月 27 日正式实验的 1.6–2 倍；本目录内所有比较都来自同一时段。

`summary.csv` 的列：3 次重复的中位数与最小/最大值，以及混合模式的
`sel_est`、`relay_expansions`、`relay_nodes`、`relay_valid` 中位数。
