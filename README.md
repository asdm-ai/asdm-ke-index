# asdm-ke-index

KE Index 开源基准库冷启动仓库——开源仓库扫描清单、扫描管线脚本、指标报告与 census 聚合产物。

> 本仓库由 AOS / KE 平台的批量扫描管线（GitHub Actions）自动维护。
> 数据落点：[kengine.ai](https://kengine.ai)；指标口径：AOS Index Metrics Schema。

## 目录结构（随管线建设填充）

| 路径 | 内容 |
|---|---|
| `repos.yaml` | 扫描清单（owner/repo/branch/skip） |
| `scripts/` | `install-cli.sh` / `scan-one.sh` / `compute-metrics.py` / `census.py` |
| `.github/workflows/scan.yml` | 批量扫描 workflow（matrix，max-parallel 4） |
| `reports/{owner}/{repo}.json` | 单仓 L1 指标报告（含分子分母与指令溯源，可复算） |
| `census/summary.json` | 聚合分位（N<30 守门——accumulating 不出分位） |
