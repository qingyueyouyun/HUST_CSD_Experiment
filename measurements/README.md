# 测量数据

本目录记录一次代表性 GateANN 查询（`mode=8`、Low 档查询负载、L=320、threads=1、
beamwidth=8、K=10）前后的页缓存与后台负载状态。

| 标签 | 条件 |
|---|---|
| `baseline-low-cold` | WSL 刚启动，`Cached` 约 195 MiB；第一次运行 |
| `baseline-low-warm` | 紧接着重跑，`Cached` 约 488 MiB |

每个标签包含：

- `.json`：汇总结果（物理读、缓存增量、RSS、PSI、进程快照）；
- `.samples.csv`：每 20 ms 采样 `/proc/meminfo`、`/proc/diskstats`、
  `/proc/<pid>/status`、`/proc/pressure/*` 的轨迹；
- `.log`：GateANN 的结果表；
- `.time`：`/usr/bin/time -v` 输出。

说明：原始 `.json` 是在测量脚本加入“过滤自身 PID”之前生成的。
`background_processes_*` 里的 `python3 ... measure_cache_and_load.py` 是测量
脚本自身，不是后台负载；其他条目都是 systemd/journald/udevd/resolved 等系统
基础服务。

汇总：

| 指标 | 冷缓存 | 热缓存 |
|---|---:|---:|
| `sdd` 物理读 | 296.2 MiB | 3.4 MiB |
| `elapsed` | 0.753 s | 0.570 s |
| Query QPS | 1389 | 1246 |
| Recall@10 | 34.30% | 34.30% |
| 峰值 RSS | 409.7 MiB | 407.9 MiB |
| `io pressure` 增量 | 37.95 ms | 0 ms |
| load average | 0.00 | 0.00 |

复现：

```bash
python3 scripts/measure_cache_and_load.py \
  --label low-cold --device sdd --out measurements \
  -- /path/to/search_disk_index_yfcc uint8 "$INDEX" 1 8 \
     "$WORKLOAD/query.u8bin" "$DATASET/base.metadata.spmat" \
     "$WORKLOAD/query.metadata.spmat" "$WORKLOAD/ground_truth.ids.ibin" \
     10 l2 pq 8 0 0 32 320
```

冷缓存需要在 Windows 侧先执行 `wsl --shutdown` 再运行第一次；第二次运行就是
热缓存。
